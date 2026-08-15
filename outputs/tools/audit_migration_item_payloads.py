"""Read-only, broad item-payload migration audit.

This is intentionally a forensic audit, not a repair tool.  It compares
semantic ItemStack payloads in block entities (and playerdata) across the
authoritative source, converted staging, and a local live/test snapshot.  It
does not rewrite NBT, chunks, regions, or configs.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import io
import json
import math
import time
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

import nbtlib


WORLD_REGION_ROOTS = (
    ("minecraft:overworld", Path("world") / "region"),
    ("minecraft:the_nether", Path("world_nether") / "DIM-1" / "region"),
    ("minecraft:the_end", Path("world_the_end") / "DIM1" / "region"),
)
ITEM_ID_KEYS = ("id", "Id", "item", "Item", "item_id", "ItemId")
COUNT_KEYS = ("count", "Count", "amount", "Amount", "size", "Size")
FILTER_TOKENS = ("filter", "whitelist", "blacklist", "allowlist", "denylist")
INVENTORY_TOKENS = ("inventory", "items", "contents", "slots", "item", "filter")


def plain(value: Any) -> Any:
    if hasattr(value, "unpack"):
        try:
            return plain(value.unpack())
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return plain(value.tolist())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def decompress(payload: bytes, compression: int) -> bytes:
    compression &= 0x7F
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"unsupported compression {compression}")


def root_value(root: Any, *names: str) -> Any:
    for name in names:
        if name in root:
            return root[name]
    level = root.get("Level") if isinstance(root, dict) else None
    if isinstance(level, dict):
        for name in names:
            if name in level:
                return level[name]
    return None


def block_entities(root: Any) -> list[Any]:
    value = root_value(root, "block_entities", "BlockEntities", "blockEntities")
    if isinstance(value, list):
        return value
    return []


def item_id(value: dict[str, Any]) -> str | None:
    for key in ITEM_ID_KEYS:
        raw = value.get(key)
        if isinstance(raw, str) and ":" in raw:
            return raw
    return None


def item_count(value: dict[str, Any]) -> int | None:
    for key in COUNT_KEYS:
        raw = value.get(key)
        if isinstance(raw, (int, float)):
            return int(raw)
    # A few legacy ItemStacks omit Count for a single item.
    if item_id(value) is not None and any(k in value for k in ("tag", "components", "componentsPatch")):
        return 1
    return None


def is_item_stack(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    ident = item_id(value)
    count = item_count(value)
    return ident is not None and count is not None


def stack_signature(value: dict[str, Any], path: str, inherited_slot: int | None = None) -> dict[str, Any]:
    ident = item_id(value) or "<missing>"
    count = item_count(value) or 0
    slot = inherited_slot
    for key in ("Slot", "slot", "Index", "index"):
        if isinstance(value.get(key), (int, float)):
            slot = int(value[key])
            break
    # Keep item identity/components but remove structural/volatile slot keys.
    payload = dict(value)
    for key in ("Slot", "slot", "Index", "index", "Count", "count", "Amount", "amount", "Size", "size"):
        payload.pop(key, None)
    return {"path": path, "slot": slot, "id": ident, "count": count,
            "payload_sha256": digest(payload), "payload": payload}


def collect_items(value: Any, path: str = "", out: list[dict[str, Any]] | None = None,
                  filter_fields: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    out = out if out is not None else []
    filter_fields = filter_fields if filter_fields is not None else []
    if isinstance(value, dict):
        if is_item_stack(value):
            out.append(stack_signature(value, path))
            return out, filter_fields
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            low = str(key).lower()
            if any(token in low for token in FILTER_TOKENS):
                filter_fields.append({"path": child_path, "value": plain(child), "sha256": digest(plain(child))})
            collect_items(child, child_path, out, filter_fields)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            collect_items(child, f"{path}[{index}]", out, filter_fields)
    return out, filter_fields


def semantic(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Ignore NBT path differences introduced by wrapper conversions; retain
    # slot/id/count/payload identity for comparison.
    rows = [{k: row[k] for k in ("slot", "id", "count", "payload_sha256")} for row in items]
    rows.sort(key=lambda row: (row["slot"] is None, row["slot"] if row["slot"] is not None else -1,
                               row["id"], row["count"], row["payload_sha256"]))
    return rows


def read_region(path: Path, dimension: str, relative: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    with path.open("rb") as fh:
        header = fh.read(4096)
        if len(header) != 4096:
            return {"records": [], "errors": ["short_header"], "relative": relative}
        for slot in range(1024):
            offset = int.from_bytes(header[slot * 4:slot * 4 + 3], "big")
            if not offset:
                continue
            try:
                fh.seek(offset * 4096)
                length_raw = fh.read(4)
                if len(length_raw) != 4:
                    raise ValueError("short_chunk_length")
                length = int.from_bytes(length_raw, "big")
                kind_raw = fh.read(1)
                if not kind_raw:
                    raise ValueError("missing_compression")
                payload = fh.read(length - 1)
                root = nbtlib.File.parse(io.BytesIO(decompress(payload, kind_raw[0])), byteorder="big")
                for index, raw in enumerate(block_entities(root)):
                    value = plain(raw)
                    if not isinstance(value, dict):
                        continue
                    try:
                        pos = [int(value[a]) for a in ("x", "y", "z")]
                    except Exception:
                        continue
                    ident = str(value.get("id", "<missing-id>"))
                    items, filters = collect_items(value)
                    # Keep only BEs that have item-like data or filter data;
                    # this makes the report compact while covering all storage.
                    if not items and not filters:
                        continue
                    records.append({
                        "key": f"{dimension}|{pos[0]},{pos[1]},{pos[2]}",
                        "dimension": dimension, "pos": pos, "id": ident,
                        "region_path": relative, "mca_slot": slot, "index": index,
                        "item_count": len(items), "total_count": sum(max(0, int(x["count"])) for x in items),
                        "items": semantic(items),
                        "filter_fields": filters,
                        "filter_sha256": digest(filters),
                        "keys": sorted(value),
                    })
            except Exception as exc:
                errors.append(f"slot={slot}:{type(exc).__name__}:{exc}")
    return {"records": records, "errors": errors, "relative": relative}


def discover(world: Path) -> list[tuple[str, Path, str]]:
    jobs: list[tuple[str, Path, str]] = []
    for dimension, relative_root in WORLD_REGION_ROOTS:
        root = world / relative_root
        if not root.exists():
            continue
        for path in root.glob("r.*.*.mca"):
            jobs.append((dimension, path, path.relative_to(world).as_posix()))
    return jobs


def scan_world(world: Path, workers: int) -> dict[str, Any]:
    jobs = discover(world)
    records: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(read_region, path, dim, rel): rel for dim, path, rel in jobs}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            errors.extend(result["errors"])
            for record in result["records"]:
                records[record["key"]] = record
    return {"root": str(world), "regions": len(jobs), "records": records, "errors": errors}


def compare(scans: dict[str, dict[str, Any]]) -> dict[str, Any]:
    keys = sorted(set().union(*(set(scan["records"]) for scan in scans.values())))
    rows: list[dict[str, Any]] = []
    for key in keys:
        row: dict[str, Any] = {"key": key}
        for name, scan in scans.items():
            record = scan["records"].get(key)
            row[name] = None if record is None else {
                "id": record["id"], "pos": record["pos"], "items": record["items"],
                "item_count": record["item_count"], "total_count": record["total_count"],
                "filter_fields": record["filter_fields"], "filter_sha256": record["filter_sha256"],
                "keys": record["keys"], "region_path": record["region_path"],
            }
        source = row.get("source")
        staging = row.get("staging")
        live = row.get("live")
        row["classification"] = classify_difference(source, staging, live)
        rows.append(row)
    counts = Counter(row["classification"] for row in rows)
    return {"keys": len(keys), "classification_counts": dict(sorted(counts.items())), "rows": rows}


def classify_difference(source: dict[str, Any] | None, staging: dict[str, Any] | None,
                        live: dict[str, Any] | None) -> str:
    def items(record: dict[str, Any] | None) -> list[dict[str, Any]]:
        return [] if record is None else record.get("items", [])
    def filters(record: dict[str, Any] | None) -> list[dict[str, Any]]:
        return [] if record is None else record.get("filter_fields", [])
    s, t, l = items(source), items(staging), items(live)
    if s and not t:
        return "SOURCE_ITEM_PAYLOAD_MISSING_IN_STAGING"
    if s and t and s != t:
        if {x["id"] for x in s} == {x["id"] for x in t}:
            return "ITEM_COUNTS_OR_COMPONENTS_DIFFER"
        return "ITEM_IDS_DIFFER"
    if t and not l:
        return "STAGING_ITEM_PAYLOAD_MISSING_IN_LIVE"
    if t and l and t != l:
        return "LIVE_ITEM_COUNTS_OR_COMPONENTS_DIFFER"
    if filters(source) != filters(staging):
        return "FILTER_FIELDS_DIFFER_SOURCE_TO_STAGING"
    if filters(staging) != filters(live):
        return "FILTER_FIELDS_DIFFER_STAGING_TO_LIVE"
    return "MATCH_OR_STRUCTURAL_ONLY"


def playerdata(world: Path) -> dict[str, Any]:
    root = world / "world" / "playerdata"
    result: dict[str, Any] = {}
    errors: list[str] = []
    if not root.is_dir():
        return {"root": str(root), "records": result, "errors": errors}
    for path in root.glob("*.dat"):
        try:
            raw = nbtlib.load(path)
            value = plain(raw)
            items, filters = collect_items(value)
            result[path.name] = {"items": semantic(items), "item_count": len(items),
                                 "total_count": sum(max(0, int(x["count"])) for x in items),
                                 "filter_fields": filters, "filter_sha256": digest(filters)}
        except Exception as exc:
            errors.append(f"{path.name}:{type(exc).__name__}:{exc}")
    return {"root": str(root), "records": result, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--live", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    roots = {"source": args.source.resolve(), "staging": args.staging.resolve()}
    if args.live:
        roots["live"] = args.live.resolve()
    scans = {name: scan_world(root, args.workers) for name, root in roots.items()}
    comparison = compare(scans)
    players = {name: playerdata(root) for name, root in roots.items()}
    result = {
        "schema": "migration-item-payload-audit/v1",
        "generated_at_epoch": time.time(),
        "roots": {name: str(root) for name, root in roots.items()},
        "policy": {"read_only": True, "chunk_overwrite": False, "writes": False, "java_started": False},
        "scans": scans,
        "comparison": comparison,
        "playerdata": players,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS_READ_ONLY", "records": comparison["keys"],
                      "classification_counts": comparison["classification_counts"], "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
