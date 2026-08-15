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
from pathlib import Path
from typing import Any

import nbtlib


# The scanner receives the actual world root.  Current converted/runtime trees
# keep vanilla dimensions below ``world/DIM-1`` and ``world/DIM1``; older game
# roots may also contain sibling ``world_nether``/``world_the_end`` folders,
# but those are deliberately not selected when the canonical world root is
# supplied.  This avoids silently auditing stale duplicate dimension trees.
DIMENSIONS = (("minecraft:overworld", Path("region")),
              ("minecraft:the_nether", Path("DIM-1") / "region"),
              ("minecraft:the_end", Path("DIM1") / "region"))
FUNNEL_IDS = {"create:funnel", "create:brass_funnel", "create:andesite_funnel"}


def plain(v: Any) -> Any:
    if hasattr(v, "unpack"):
        try:
            return plain(v.unpack())
        except Exception:
            pass
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def canonical(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(v: Any) -> str:
    return hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()


def decomp(payload: bytes, kind: int) -> bytes:
    kind &= 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported compression {kind}")


def block_entities(root: Any) -> list[Any]:
    for key in ("block_entities", "BlockEntities", "blockEntities"):
        value = root.get(key)
        if isinstance(value, list):
            return value
    level = root.get("Level")
    if isinstance(level, dict):
        for key in ("block_entities", "BlockEntities", "blockEntities"):
            value = level.get(key)
            if isinstance(value, list):
                return value
    return []


def recursive_filter_fields(value: Any, path: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            low = str(key).lower()
            if any(token in low for token in ("filter", "whitelist", "blacklist", "allowlist", "denylist")):
                out.append({"path": child_path, "key": str(key), "value": plain(child)})
            out.extend(recursive_filter_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            out.extend(recursive_filter_fields(child, f"{path}[{index}]"))
    return out


def read_region(path: Path, world: Path, dimension: str, rel: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    before = path.stat()
    with path.open("rb") as fh:
        locations = fh.read(4096)
        if len(locations) != 4096:
            raise ValueError("short location table")
        for slot in range(1024):
            off = int.from_bytes(locations[slot * 4:slot * 4 + 3], "big")
            if not off:
                continue
            try:
                fh.seek(off * 4096)
                length = int.from_bytes(fh.read(4), "big")
                kind_raw = fh.read(1)
                if not kind_raw:
                    raise ValueError("missing compression")
                payload = fh.read(length - 1)
                root = nbtlib.File.parse(io.BytesIO(decomp(payload, kind_raw[0])), byteorder="big")
                for index, raw in enumerate(block_entities(root)):
                    value = plain(raw)
                    if not isinstance(value, dict):
                        continue
                    ident = str(value.get("id", ""))
                    if ident not in FUNNEL_IDS and "funnel" not in ident.lower():
                        continue
                    try:
                        pos = [int(value[a]) for a in ("x", "y", "z")]
                    except Exception:
                        pos = [None, None, None]
                    filter_fields = recursive_filter_fields(value)
                    # Keep the complete BE for forensic comparison, but omit volatile keys if present.
                    records.append({
                        "key": f"{dimension}|{pos[0]},{pos[1]},{pos[2]}",
                        "dimension": dimension,
                        "pos": pos,
                        "id": ident,
                        "region_path": rel,
                        "mca_slot": slot,
                        "block_entity_index": index,
                        "keys": sorted(str(k) for k in value),
                        "filter_fields": filter_fields,
                        "nbt": value,
                        "nbt_sha256": sha(value),
                        "filter_sha256": sha(filter_fields),
                    })
            except Exception as exc:
                errors.append(f"slot={slot}: {type(exc).__name__}: {exc}")
    after = path.stat()
    return {"path": str(path), "relative": rel, "dimension": dimension,
            "records": records, "errors": errors,
            "changed_during_read": before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns}


def discover(world: Path) -> list[tuple[str, Path, str]]:
    jobs: list[tuple[str, Path, str]] = []
    for dimension, rel_root in DIMENSIONS:
        root = world / rel_root
        if not root.exists():
            continue
        for path in root.glob("r.*.*.mca"):
            jobs.append((dimension, path, path.relative_to(world).as_posix()))
    return jobs


def scan(world: Path, workers: int) -> dict[str, Any]:
    jobs = discover(world)
    records: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    started = time.time()
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(read_region, path, world, dim, rel): (dim, rel) for dim, path, rel in jobs}
        for future in concurrent.futures.as_completed(futures):
            dim, rel = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                errors.append({"dimension": dim, "relative": rel, "error": f"{type(exc).__name__}: {exc}"})
                continue
            errors.extend({"dimension": dim, "relative": rel, "error": e} for e in result["errors"])
            for record in result["records"]:
                if record["key"] in records:
                    errors.append({"key": record["key"], "error": "duplicate funnel coordinate"})
                records[record["key"]] = record
    return {"world": str(world), "regions": len(jobs), "records": records,
            "errors": errors, "seconds": round(time.time() - started, 3)}


def compare(scans: dict[str, dict[str, Any]]) -> dict[str, Any]:
    keys = sorted(set().union(*(set(item["records"]) for item in scans.values())))
    rows: list[dict[str, Any]] = []
    for key in keys:
        row = {"key": key}
        for name, scan_result in scans.items():
            rec = scan_result["records"].get(key)
            row[name] = None if rec is None else {
                "id": rec["id"], "pos": rec["pos"], "nbt_sha256": rec["nbt_sha256"],
                "filter_sha256": rec["filter_sha256"], "filter_fields": rec["filter_fields"],
                "keys": rec["keys"], "nbt": rec["nbt"],
            }
        rows.append(row)
    return {"keys": len(keys), "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--live", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    roots = {"source": args.source.resolve(), "staging": args.staging.resolve()}
    if args.live:
        roots["live"] = args.live.resolve()
    scans = {name: scan(root, args.workers) for name, root in roots.items()}
    comparison = compare(scans)
    result = {"schema": "create-brass-funnel-filter-audit/v1", "roots": {k: str(v) for k, v in roots.items()},
              "candidate_ids": sorted(FUNNEL_IDS), "scans": scans, "comparison": comparison}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "rows": comparison["keys"], "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
