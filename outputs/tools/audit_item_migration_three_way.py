"""Read-only three-way item-content audit for Minecraft world trees.

This scanner deliberately works below the Minecraft runtime.  It reads Anvil
``region``/``entities`` files, playerdata, and saved-data NBT files from three
snapshots (original, converted staging, and local runtime), then compares item
stacks by owner/container/path, item id, component hash, count, and slot.

It never opens Java, acquires a world lock, or writes to any scanned tree.  The
only writes are the report and optional NDJSON paths supplied on the command
line.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import gzip
import hashlib
import io
import json
import re
import time
import zlib
from pathlib import Path
from typing import Any, Iterable, Mapping

import nbtlib


REGION_NAME = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
UUID_STRING = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
UUID_HEX = re.compile(r"^[0-9a-fA-F]{32}$")
DIMENSION_DIRS = {"DIM-1": "minecraft:the_nether", "DIM1": "minecraft:the_end"}
CONTAINER_WORDS = {
    "inventory", "inventories", "items", "item", "filter", "filters", "handler",
    "handlers", "storage", "contents", "content", "curios", "slots", "slot",
    "equipment", "armor", "offhand", "mainhand", "input", "inputs", "output",
    "outputs", "fuel", "result", "results", "pattern", "patterns", "template",
    "templates", "package", "packages", "displayitem", "display_item", "helditem",
    "held_item", "itemstack", "item_stack", "catalyst", "ingredient", "ingredients",
    "filteritem", "filter_item", "filterstack", "filter_stack", "upgrades", "tools",
    "backpack", "backpacks", "container", "chest", "tankcontent", "tanks",
}
HIGH_RISK_WORDS = {
    "inventory", "items", "filter", "handler", "storage", "curios", "equipment",
    "armor", "slots", "slot", "input", "output", "fuel", "result", "pattern",
    "template", "package", "itemstack", "item_stack", "tankcontent", "tanks",
}
SKIP_NBT_DIRS = {"region", "entities", "poi", "playerdata", "advancements", "stats"}
MAX_DIFF_DETAILS = 4000


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
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest().upper()


def int_value(value: Any) -> int | None:
    return value if type(value) is int else None


def item_id(value: Mapping[str, Any]) -> str | None:
    raw = value.get("id")
    if isinstance(raw, str) and ":" in raw:
        return raw
    raw = value.get("Id")
    if isinstance(raw, str) and ":" in raw:
        return raw
    raw = value.get("Item")
    if isinstance(raw, str) and ":" in raw:
        return raw
    return None


def item_count(value: Mapping[str, Any]) -> int | None:
    for key in ("count", "Count", "amount", "Amount"):
        raw = int_value(value.get(key))
        if raw is not None:
            return raw
    return None


def is_item_stack(value: Mapping[str, Any]) -> bool:
    identifier = item_id(value)
    count = item_count(value)
    return identifier is not None and count is not None and count >= 0


def slot_value(value: Mapping[str, Any], path: str) -> int | None:
    for key in ("Slot", "slot", "Index", "index"):
        raw = int_value(value.get(key))
        if raw is not None:
            return raw
    match = re.search(r"\[(\d+)\]$", path)
    return int(match.group(1)) if match else None


def shape_of(value: Any) -> str:
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "compound"
    return type(value).__name__


def path_parts(path: str) -> list[str]:
    return [part for part in re.split(r"\.|\[\d+\]", path) if part]


def container_path(path: str) -> str:
    parts = path_parts(path)
    selected: list[str] = []
    for part in parts:
        selected.append(part)
        if part.lower() in CONTAINER_WORDS or any(word in part.lower() for word in HIGH_RISK_WORDS):
            return ".".join(selected)
    if len(parts) > 1:
        return ".".join(parts[:-1])
    return "<root>"


def components_hash(value: Mapping[str, Any]) -> str:
    excluded = {"id", "Id", "Item", "count", "Count", "amount", "Amount", "Slot", "slot", "Index", "index"}
    return digest({str(k): plain(v) for k, v in value.items() if str(k) not in excluded})


def is_container_key(key: str) -> bool:
    low = key.lower()
    return low in CONTAINER_WORDS or any(word in low for word in HIGH_RISK_WORDS)


def decode_nbt_bytes(raw: bytes, label: str) -> dict[str, Any]:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    parsed = nbtlib.File.parse(io.BytesIO(raw), byteorder="big")
    value = plain(parsed)
    if not isinstance(value, dict):
        raise ValueError(f"NBT root is not a compound: {label}")
    return value


def decompress_chunk(payload: bytes, compression: int) -> bytes:
    compression &= 0x7F
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"unsupported compression {compression}")


def dimension_for_relative(relative: str) -> str:
    parts = relative.replace("\\", "/").split("/")
    return DIMENSION_DIRS.get(parts[0], "minecraft:overworld")


def mca_kind(relative: str) -> str | None:
    parts = relative.replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[-1].endswith(".mca") and parts[-2] in {"region", "entities"}:
        return parts[-2]
    return None


def chunk_position(root: Mapping[str, Any]) -> tuple[int | None, int | None]:
    level = root.get("Level") if isinstance(root.get("Level"), dict) else root
    return int_value(level.get("xPos")), int_value(level.get("zPos"))


def list_value(root: Mapping[str, Any], *names: str) -> list[Any]:
    level = root.get("Level") if isinstance(root.get("Level"), dict) else root
    for name in names:
        value = level.get(name)
        if isinstance(value, list):
            return value
    return []


def entity_uuid(value: Mapping[str, Any]) -> str | None:
    raw = value.get("UUID")
    if isinstance(raw, str):
        if UUID_STRING.fullmatch(raw) or UUID_HEX.fullmatch(raw):
            return raw.lower()
        return raw.lower()
    if isinstance(raw, list) and len(raw) == 4 and all(type(v) is int for v in raw):
        number = 0
        for part in raw:
            number = (number << 32) | (part & 0xFFFFFFFF)
        return f"{number:032x}"
    if "UUIDMost" in value and "UUIDLeast" in value:
        try:
            return f"{int(value['UUIDMost']) & 0xFFFFFFFFFFFFFFFF:016x}{int(value['UUIDLeast']) & 0xFFFFFFFFFFFFFFFF:016x}"
        except Exception:
            return None
    return None


def position_text(value: Mapping[str, Any]) -> str:
    for key in ("Pos", "pos", "BlockPos", "block_pos"):
        raw = value.get(key)
        if isinstance(raw, list) and len(raw) == 3:
            return canonical(raw)
    xyz = [value.get(k) for k in ("x", "y", "z")]
    if all(type(v) is int for v in xyz):
        return canonical(xyz)
    return "?"


def owner_scan(owner_kind: str, owner_key: str, identifier: str, value: Mapping[str, Any], location: Mapping[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    container_shapes: dict[str, dict[str, Any]] = {}

    def walk(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            if path:
                last = path_parts(path)[-1] if path_parts(path) else ""
                if last and is_container_key(last):
                    container_shapes.setdefault(
                        path,
                        {
                            "shape": shape_of(node),
                            "keys": sorted(str(k) for k in node.keys()),
                            "item_like": is_item_stack(node),
                        },
                    )
            if is_item_stack(node):
                identifier_value = item_id(node) or "<missing>"
                count_value = item_count(node) or 0
                items.append(
                    {
                        "id": identifier_value,
                        "count": count_value,
                        "slot": slot_value(node, path),
                        "path": path or "<root>",
                        "container": container_path(path),
                        "components_sha256": components_hash(node),
                        "schema_keys": sorted(str(k) for k in node.keys()),
                    }
                )
            for key, child in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                walk(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{path}[{index}]" if path else f"[{index}]")

    walk(value)
    containers: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for item in items:
        grouped[item["container"]].append(item)
    for name, entries in grouped.items():
        counts: collections.Counter[tuple[str, str]] = collections.Counter()
        slots: list[dict[str, Any]] = []
        for entry in entries:
            counts[(entry["id"], entry["components_sha256"])] += int(entry["count"])
            slots.append(
                {
                    "slot": entry["slot"],
                    "id": entry["id"],
                    "count": entry["count"],
                    "components_sha256": entry["components_sha256"],
                    "path": entry["path"],
                }
            )
        multiset = [
            {"id": key[0], "components_sha256": key[1], "units": units}
            for key, units in sorted(counts.items())
            if units > 0
        ]
        shape = container_shapes.get(name, {})
        containers[name] = {
            "item_units": sum(int(entry["count"]) for entry in entries),
            "stack_count": len(entries),
            "item_multiset": multiset,
            "item_multiset_sha256": digest(multiset),
            "slot_map": sorted(slots, key=lambda row: (row["slot"] is None, row["slot"] if row["slot"] is not None else 0, row["path"])),
            "schema_sha256": digest({"shape": shape, "item_paths": sorted(entry["path"] for entry in entries), "schema_keys": sorted({key for entry in entries for key in entry["schema_keys"]})}),
            "shape": shape,
        }
    return {
        "owner_kind": owner_kind,
        "owner_key": owner_key,
        "identifier": identifier,
        "location": dict(location),
        "containers": containers,
        "container_count": len(containers),
        "item_units": sum(int(entry["count"]) for entry in items),
        "stack_count": len(items),
        "item_count": len(items),
        "raw_item_paths": items[:256],
    }


def unique_key(seen: collections.Counter[str], base: str) -> str:
    n = seen[base]
    seen[base] += 1
    return base if n == 0 else f"{base}|dup{n}"


def parse_mca(path: Path, world: Path, stage: str, errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    relative = path.relative_to(world).as_posix()
    kind = mca_kind(relative)
    if kind is None:
        return []
    dimension = dimension_for_relative(relative)
    region_match = REGION_NAME.fullmatch(path.name)
    if region_match is None:
        return []
    region_coords = (int(region_match.group(1)), int(region_match.group(2)))
    try:
        data = path.read_bytes()
    except Exception as exc:
        errors.append({"stage": stage, "path": str(path), "reason": f"read:{exc}"})
        return []
    if len(data) < 8192:
        errors.append({"stage": stage, "path": str(path), "reason": "short_mca"})
        return []
    out: list[dict[str, Any]] = []
    seen_be: collections.Counter[str] = collections.Counter()
    seen_entity: collections.Counter[str] = collections.Counter()
    locations = data[:4096]
    for slot in range(1024):
        entry = locations[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if offset == 0 or sectors == 0:
            continue
        start = offset * 4096
        if start + 5 > len(data):
            errors.append({"stage": stage, "path": str(path), "slot": slot, "reason": "missing_chunk_header"})
            continue
        length = int.from_bytes(data[start : start + 4], "big")
        compression = data[start + 4]
        payload = data[start + 5 : start + 4 + length]
        try:
            root = decode_nbt_bytes(decompress_chunk(payload, compression), f"{path}:{slot}")
        except Exception as exc:
            errors.append({"stage": stage, "path": str(path), "slot": slot, "reason": f"decode:{type(exc).__name__}:{exc}"})
            continue
        chunk_x, chunk_z = chunk_position(root)
        if kind == "region":
            values = list_value(root, "block_entities", "BlockEntities", "blockEntities")
            for index, block_entity in enumerate(values):
                if not isinstance(block_entity, dict):
                    continue
                identifier = str(block_entity.get("id", "<missing>"))
                pos = [block_entity.get(axis) for axis in ("x", "y", "z")]
                if all(type(v) is int for v in pos):
                    base = f"be|{dimension}|{pos[0]},{pos[1]},{pos[2]}"
                else:
                    base = f"be|{dimension}|{relative}|{slot}|{index}|{identifier}"
                owner_key = unique_key(seen_be, base)
                out.append(
                    owner_scan(
                        "block_entity",
                        owner_key,
                        identifier,
                        block_entity,
                        {
                            "dimension": dimension,
                            "path": relative,
                            "slot": slot,
                            "chunk": [chunk_x, chunk_z],
                            "index": index,
                            "pos": pos,
                        },
                    )
                )
        else:
            values = list_value(root, "Entities", "entities")
            for index, entity in enumerate(values):
                if not isinstance(entity, dict):
                    continue
                identifier = str(entity.get("id", "<missing>"))
                uid = entity_uuid(entity)
                base = f"entity|{dimension}|uuid:{uid}" if uid else f"entity|{dimension}|{identifier}|{position_text(entity)}"
                owner_key = unique_key(seen_entity, base)
                out.append(
                    owner_scan(
                        "entity",
                        owner_key,
                        identifier,
                        entity,
                        {
                            "dimension": dimension,
                            "path": relative,
                            "slot": slot,
                            "chunk": [chunk_x, chunk_z],
                            "index": index,
                            "uuid": uid,
                            "pos": plain(entity.get("Pos", entity.get("pos"))),
                        },
                    )
                )
    return out


def parse_mca_job(job: tuple[Path, Path, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Process-pool wrapper; keeps all world inputs read-only."""
    path, world, stage = job
    errors: list[dict[str, Any]] = []
    records = parse_mca(path, world, stage, errors)
    return records, errors


def parse_file_owner(path: Path, world: Path, stage: str, errors: list[dict[str, Any]], kind: str, key_prefix: str) -> dict[str, Any] | None:
    relative = path.relative_to(world).as_posix()
    try:
        root = decode_nbt_bytes(path.read_bytes(), str(path))
    except Exception as exc:
        errors.append({"stage": stage, "path": str(path), "reason": f"decode:{type(exc).__name__}:{exc}"})
        return None
    identifier = path.stem
    if kind == "player":
        uid = path.stem
        owner_key = f"player|{uid.lower()}"
        identifier = uid
    else:
        owner_key = f"data|{relative}"
        identifier = relative
    return owner_scan(kind, owner_key, identifier, root, {"path": relative, "file": relative})


def scan_world(world: Path, stage: str, workers: int = 4) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    started = time.time()
    world = world.resolve()
    errors: list[dict[str, Any]] = []
    records: dict[str, dict[str, Any]] = {}
    mca_paths = sorted(
        path
        for path in world.rglob("*.mca")
        if mca_kind(path.relative_to(world).as_posix()) in {"region", "entities"}
    )
    jobs = [(path, world, stage) for path in mca_paths]
    if workers > 1 and jobs:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            iterator = pool.map(parse_mca_job, jobs, chunksize=1)
            for index, (parsed_records, parsed_errors) in enumerate(iterator, 1):
                errors.extend(parsed_errors)
                for record in parsed_records:
                    # Empty owners are retained only when a container shape exists or
                    # when an item stack was found; this keeps the report bounded.
                    if record["container_count"] or record["item_count"]:
                        records[record["owner_key"]] = record
                if index % 250 == 0:
                    print(json.dumps({"stage": stage, "phase": "mca", "completed": index, "total": len(mca_paths)}), flush=True)
    else:
        for index, path in enumerate(mca_paths, 1):
            parsed_errors: list[dict[str, Any]] = []
            for record in parse_mca(path, world, stage, parsed_errors):
                if record["container_count"] or record["item_count"]:
                    records[record["owner_key"]] = record
            errors.extend(parsed_errors)
            if index % 250 == 0:
                print(json.dumps({"stage": stage, "phase": "mca", "completed": index, "total": len(mca_paths)}), flush=True)

    player_paths = sorted((world / "playerdata").glob("*.dat")) if (world / "playerdata").is_dir() else []
    for path in player_paths:
        record = parse_file_owner(path, world, stage, errors, "player", "player")
        if record and (record["container_count"] or record["item_count"]):
            records[record["owner_key"]] = record

    # SavedData and mod-owned NBT files are common places for package/item
    # stacks.  Do not descend into region/entity/playerdata trees a second time.
    data_paths = sorted(
        path
        for path in world.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".dat", ".nbt"}
        and not any(part in SKIP_NBT_DIRS for part in path.relative_to(world).parts)
    )
    for path in data_paths:
        record = parse_file_owner(path, world, stage, errors, "saved_data", "data")
        if record and (record["container_count"] or record["item_count"]):
            records[record["owner_key"]] = record

    totals = collections.Counter()
    by_kind: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    item_counter: collections.Counter[str] = collections.Counter()
    for record in records.values():
        kind = str(record["owner_kind"])
        by_kind[kind]["owners"] += 1
        by_kind[kind]["containers"] += int(record["container_count"])
        by_kind[kind]["item_units"] += int(record["item_units"])
        by_kind[kind]["stacks"] += int(record["stack_count"])
        totals["owners"] += 1
        totals["containers"] += int(record["container_count"])
        totals["item_units"] += int(record["item_units"])
        totals["stacks"] += int(record["stack_count"])
        for container in record["containers"].values():
            for item in container["item_multiset"]:
                item_counter[item["id"]] += int(item["units"])
    return records, {
        "stage": stage,
        "world": str(world),
        "mca_files": len(mca_paths),
        "player_files": len(player_paths),
        "saved_data_files": len(data_paths),
        "owners": dict(totals),
        "by_kind": {kind: dict(values) for kind, values in sorted(by_kind.items())},
        "top_item_ids": [{"id": key, "units": units} for key, units in item_counter.most_common(100)],
        "parse_error_count": len(errors),
        "parse_errors": errors[:500],
        "elapsed_seconds": round(time.time() - started, 3),
    }


def multiset_counter(container: Mapping[str, Any]) -> collections.Counter[tuple[str, str]]:
    result: collections.Counter[tuple[str, str]] = collections.Counter()
    for item in container.get("item_multiset", []):
        result[(str(item["id"]), str(item["components_sha256"]))] += int(item["units"])
    return result


def compare_pair(label: str, left: dict[str, dict[str, Any]], right: dict[str, dict[str, Any]]) -> dict[str, Any]:
    started = time.time()
    missing_owners = sorted(set(left) - set(right))
    extra_owners = sorted(set(right) - set(left))
    diffs: list[dict[str, Any]] = []
    severity_counts: collections.Counter[str] = collections.Counter()
    lost_units_total = 0
    added_units_total = 0
    format_drift_count = 0
    slot_diff_count = 0
    for owner_key in sorted(set(left) & set(right)):
        a, b = left[owner_key], right[owner_key]
        if a.get("identifier") != b.get("identifier"):
            diffs.append({"kind": "owner_id_drift", "severity": "medium", "owner_key": owner_key, "left": a.get("identifier"), "right": b.get("identifier")})
            severity_counts["medium"] += 1
        names = sorted(set(a.get("containers", {})) | set(b.get("containers", {})))
        for name in names:
            ca = a.get("containers", {}).get(name)
            cb = b.get("containers", {}).get(name)
            if ca is None:
                severity = "low" if not cb.get("item_units") else "medium"
                diffs.append({"kind": "container_added", "severity": severity, "owner_key": owner_key, "container": name, "right": cb})
                severity_counts[severity] += 1
                added_units_total += int(cb.get("item_units", 0))
                continue
            if cb is None:
                severity = "high" if int(ca.get("item_units", 0)) > 0 else "medium"
                diffs.append({"kind": "container_missing", "severity": severity, "owner_key": owner_key, "container": name, "left": ca})
                severity_counts[severity] += 1
                lost_units_total += int(ca.get("item_units", 0))
                continue
            left_counter = multiset_counter(ca)
            right_counter = multiset_counter(cb)
            lost = left_counter - right_counter
            added = right_counter - left_counter
            lost_units = sum(lost.values())
            added_units = sum(added.values())
            slot_changed = ca.get("slot_map") != cb.get("slot_map")
            shape_changed = ca.get("schema_sha256") != cb.get("schema_sha256")
            if lost_units or added_units:
                severity = "high" if lost_units else "medium"
                diffs.append(
                    {
                        "kind": "item_multiset_delta",
                        "severity": severity,
                        "owner_key": owner_key,
                        "container": name,
                        "lost_units": lost_units,
                        "added_units": added_units,
                        "left_units": ca.get("item_units", 0),
                        "right_units": cb.get("item_units", 0),
                        "lost": [{"id": key[0], "components_sha256": key[1], "units": units} for key, units in lost.items()],
                        "added": [{"id": key[0], "components_sha256": key[1], "units": units} for key, units in added.items()],
                        "left_slot_map": ca.get("slot_map", [])[:128],
                        "right_slot_map": cb.get("slot_map", [])[:128],
                    }
                )
                severity_counts[severity] += 1
                lost_units_total += lost_units
                added_units_total += added_units
            elif shape_changed:
                format_drift_count += 1
                diffs.append(
                    {
                        "kind": "format_drift_equal_items",
                        "severity": "medium",
                        "owner_key": owner_key,
                        "container": name,
                        "left_schema_sha256": ca.get("schema_sha256"),
                        "right_schema_sha256": cb.get("schema_sha256"),
                        "left_shape": ca.get("shape"),
                        "right_shape": cb.get("shape"),
                    }
                )
                severity_counts["medium"] += 1
            if slot_changed:
                slot_diff_count += 1
                if not lost_units and not added_units:
                    diffs.append(
                        {
                            "kind": "slot_or_path_drift_equal_items",
                            "severity": "medium",
                            "owner_key": owner_key,
                            "container": name,
                            "left_slot_map": ca.get("slot_map", [])[:128],
                            "right_slot_map": cb.get("slot_map", [])[:128],
                        }
                    )
                    severity_counts["medium"] += 1
    for owner_key in missing_owners:
        record = left[owner_key]
        if int(record.get("item_units", 0)) > 0:
            severity = "high"
            lost_units_total += int(record.get("item_units", 0))
        else:
            severity = "low"
        diffs.append({"kind": "owner_missing", "severity": severity, "owner_key": owner_key, "left": record})
        severity_counts[severity] += 1
    for owner_key in extra_owners:
        record = right[owner_key]
        severity = "medium" if int(record.get("item_units", 0)) > 0 else "low"
        added_units_total += int(record.get("item_units", 0))
        diffs.append({"kind": "owner_added", "severity": severity, "owner_key": owner_key, "right": record})
        severity_counts[severity] += 1
    high_risk = sorted(
        (row for row in diffs if row.get("severity") == "high"),
        key=lambda row: (int(row.get("lost_units", 0)), str(row.get("owner_key")), str(row.get("container", ""))),
        reverse=True,
    )
    return {
        "label": label,
        "left_owner_count": len(left),
        "right_owner_count": len(right),
        "missing_owner_count": len(missing_owners),
        "added_owner_count": len(extra_owners),
        "missing_owner_sample": missing_owners[:200],
        "added_owner_sample": extra_owners[:200],
        "diff_count": len(diffs),
        "severity_counts": dict(sorted(severity_counts.items())),
        "lost_item_units": lost_units_total,
        "added_item_units": added_units_total,
        "format_drift_equal_item_count": format_drift_count,
        "slot_or_path_drift_count": slot_diff_count,
        "high_risk_count": len(high_risk),
        "high_risk": high_risk[:1000],
        "diffs": diffs[:MAX_DIFF_DETAILS],
        "diffs_truncated": len(diffs) > MAX_DIFF_DETAILS,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def markdown(report: Mapping[str, Any], json_path: Path, ndjson_path: Path | None) -> str:
    lines = [
        "# 三阶段物品迁移审计",
        "",
        f"- 状态：`{report['status']}`",
        f"- 生成时间：`{report['generated_at_utc']}`",
        f"- 机器报告：`{json_path.resolve()}`",
        f"- 详细 NDJSON：`{ndjson_path.resolve() if ndjson_path else '未输出'}`",
        "- 只读：未启动 Java/Minecraft，未修改任何输入世界；仅写报告文件。",
        "",
        "## 输入",
        "",
    ]
    for name, stage in report["stages"].items():
        lines.append(f"- **{name}**：`{stage['world']}`")
        lines.append(f"  - owners={stage['owners'].get('owners', 0)}, containers={stage['owners'].get('containers', 0)}, stacks={stage['owners'].get('stacks', 0)}, units={stage['owners'].get('item_units', 0)}")
        lines.append(f"  - parse errors={stage['parse_error_count']}")
    lines.extend(["", "## 两段比较", ""])
    for label, row in report["pairwise"].items():
        lines.extend(
            [
                f"### {label}",
                "",
                f"- owner 缺失/新增：`{row['missing_owner_count']}` / `{row['added_owner_count']}`",
                f"- 物品单位减少/增加：`{row['lost_item_units']}` / `{row['added_item_units']}`",
                f"- 高风险差异：`{row['high_risk_count']}`",
                f"- 等价物品但格式漂移：`{row['format_drift_equal_item_count']}`；槽位/路径漂移：`{row['slot_or_path_drift_count']}`",
                f"- 严重度计数：`{row['severity_counts']}`",
                "",
            ]
        )
    lines.extend(["## 审核结论", ""])
    for item in report["high_risk_summary"]:
        lines.append(f"- `{item}`")
    if not report["high_risk_summary"]:
        lines.append("- 未发现高风险物品单位减少或非空 owner 缺失。")
    lines.extend(["", "完整差异样本和路径见 JSON/NDJSON；runtime 阶段的减少可能是本地启动后玩家/机器运行造成的，需要结合时间线复核。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only three-way item migration audit")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--ndjson", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        raise SystemExit("--workers must be between 1 and 16")
    for path in (args.source, args.staging, args.runtime):
        if not path.is_dir():
            raise SystemExit(f"world directory does not exist: {path}")
    started = time.time()
    stage_paths = {"source": args.source, "staging": args.staging, "runtime": args.runtime}
    all_records: dict[str, dict[str, dict[str, Any]]] = {}
    stage_stats: dict[str, Any] = {}
    for name, path in stage_paths.items():
        records, stats = scan_world(path, name, args.workers)
        all_records[name] = records
        stage_stats[name] = stats
    pairwise = {
        "source_to_staging": compare_pair("source_to_staging", all_records["source"], all_records["staging"]),
        "staging_to_runtime": compare_pair("staging_to_runtime", all_records["staging"], all_records["runtime"]),
    }
    high_risk_summary: list[str] = []
    for label, row in pairwise.items():
        if row["lost_item_units"]:
            high_risk_summary.append(f"{label}: item units lost={row['lost_item_units']}, high-risk records={row['high_risk_count']}")
        if row["format_drift_equal_item_count"]:
            high_risk_summary.append(f"{label}: equal item multisets with format drift={row['format_drift_equal_item_count']}")
    report = {
        "schema": 1,
        "status": "PASS_READ_ONLY" if not any(stats["parse_error_count"] for stats in stage_stats.values()) else "BLOCKED_PARSE_ERRORS",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "policy": {"writes_to_worlds": False, "deletions": False, "java_started": False, "world_lock_acquired": False},
        "stages": stage_stats,
        "pairwise": pairwise,
        "high_risk_summary": high_risk_summary,
        "elapsed_seconds": round(time.time() - started, 3),
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.ndjson:
        args.ndjson.parent.mkdir(parents=True, exist_ok=True)
        with args.ndjson.open("w", encoding="utf-8") as handle:
            for stage, records in all_records.items():
                for record in records.values():
                    handle.write(json.dumps({"type": "owner", "stage": stage, "record": record}, ensure_ascii=False, separators=(",", ":")) + "\n")
            for label, row in pairwise.items():
                for diff in row["diffs"]:
                    handle.write(json.dumps({"type": "diff", "pair": label, "diff": diff}, ensure_ascii=False, separators=(",", ":")) + "\n")
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown(report, args.json, args.ndjson), encoding="utf-8")
    print(json.dumps({"status": report["status"], "json": str(args.json.resolve()), "markdown": str(args.markdown.resolve()), "ndjson": str(args.ndjson.resolve()) if args.ndjson else None, "elapsed_seconds": report["elapsed_seconds"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
