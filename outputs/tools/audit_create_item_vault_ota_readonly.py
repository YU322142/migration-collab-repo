from __future__ import annotations

import argparse
import collections
import concurrent.futures
import gzip
import hashlib
import io
import json
import math
import os
import time
import zlib
from pathlib import Path
from typing import Any

import nbtlib


DIMENSIONS = (
    ("minecraft:overworld", Path("region")),
    ("minecraft:the_nether", Path("DIM-1") / "region"),
    ("minecraft:the_end", Path("DIM1") / "region"),
)
VAULT_ID = "create:item_vault"


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
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def sequence(value: Any) -> list[Any]:
    unwrapped = plain(value)
    return list(unwrapped) if isinstance(unwrapped, (list, tuple)) else []


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


def block_state_at(sections: dict[int, Any], x: int, y: int, z: int) -> dict[str, Any]:
    section = sections.get(math.floor(y / 16))
    if not isinstance(section, dict):
        return {"name": "minecraft:air", "properties": {}, "decode": "missing_section"}
    container = section.get("block_states", section.get("BlockStates"))
    if not isinstance(container, dict):
        return {"name": "minecraft:air", "properties": {}, "decode": "missing_container"}
    palette_raw = container.get("palette", container.get("Palette", []))
    palette = list(palette_raw) if isinstance(palette_raw, list) else []
    if not palette:
        return {"name": "<missing-palette>", "properties": {}, "decode": "missing_palette"}
    local_x, local_y, local_z = x & 15, y & 15, z & 15
    linear_index = (local_y * 16 + local_z) * 16 + local_x
    palette_index = 0
    if len(palette) > 1:
        data_raw = container.get("data", container.get("Data", []))
        data = sequence(data_raw)
        if not data:
            return {"name": "<missing-packed-data>", "properties": {}, "decode": "missing_data"}
        bits = max(4, (len(palette) - 1).bit_length())
        values_per_long = 64 // bits
        long_index = linear_index // values_per_long
        if long_index >= len(data):
            return {"name": "<packed-data-overrun>", "properties": {}, "decode": "data_overrun"}
        raw = int(data[long_index]) & 0xFFFFFFFFFFFFFFFF
        palette_index = (raw >> ((linear_index % values_per_long) * bits)) & ((1 << bits) - 1)
    if palette_index >= len(palette):
        return {"name": "<invalid-palette-index>", "properties": {}, "decode": "invalid_index"}
    entry = palette[palette_index]
    if not isinstance(entry, dict):
        return {"name": "<invalid-palette-entry>", "properties": {}, "decode": "invalid_entry"}
    name = str(plain(entry.get("Name", entry.get("name", "minecraft:air"))))
    properties = plain(entry.get("Properties", entry.get("properties", {})))
    return {
        "name": name,
        "properties": properties if isinstance(properties, dict) else {},
        "decode": "ok",
    }


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
    raise ValueError(f"unsupported region compression {compression}")


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


def stack_count(stack: dict[str, Any]) -> int:
    raw = stack.get("count", stack.get("Count", 0))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def semantic_slots(inventory: Any) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    if isinstance(inventory, list):
        values = inventory
        for index, raw in enumerate(values):
            if not isinstance(raw, dict):
                continue
            stack = plain(raw)
            identifier = stack.get("id", stack.get("Id"))
            if not identifier or stack_count(stack) <= 0:
                continue
            stack.pop("Slot", None)
            stack.pop("slot", None)
            slots.append({"slot": index, "stack": stack})
        return slots
    if isinstance(inventory, dict):
        values = inventory.get("Items", inventory.get("items", []))
        if not isinstance(values, list):
            return slots
        for index, raw in enumerate(values):
            if not isinstance(raw, dict):
                continue
            stack = plain(raw)
            identifier = stack.get("id", stack.get("Id"))
            if not identifier or stack_count(stack) <= 0:
                continue
            raw_slot = stack.pop("Slot", stack.pop("slot", index))
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError):
                slot = index
            slots.append({"slot": slot, "stack": stack})
        slots.sort(key=lambda item: (item["slot"], canonical(item["stack"])))
    return slots


def inventory_summary(inventory: Any) -> dict[str, Any]:
    slots = semantic_slots(inventory)
    total_items = sum(stack_count(item["stack"]) for item in slots)
    id_counts: collections.Counter[str] = collections.Counter()
    for item in slots:
        stack = item["stack"]
        identifier = str(stack.get("id", stack.get("Id", "<missing>")))
        id_counts[identifier] += stack_count(stack)
    if isinstance(inventory, list):
        fmt = "dense_list"
        declared_size = None
        raw_entry_count = len(inventory)
    elif isinstance(inventory, dict):
        fmt = "neoforge_handler"
        declared_size = inventory.get("Size", inventory.get("size"))
        values = inventory.get("Items", inventory.get("items", []))
        raw_entry_count = len(values) if isinstance(values, list) else None
    elif inventory is None:
        fmt = "missing"
        declared_size = None
        raw_entry_count = None
    else:
        fmt = type(inventory).__name__
        declared_size = None
        raw_entry_count = None
    identity_counts = [
        {
            "slot": item["slot"],
            "id": item["stack"].get("id", item["stack"].get("Id")),
            "count": stack_count(item["stack"]),
        }
        for item in slots
    ]
    return {
        "format": fmt,
        "declared_size": plain(declared_size),
        "raw_entry_count": raw_entry_count,
        "nonempty_slots": len(slots),
        "total_item_count": total_items,
        "is_nonempty": bool(slots),
        "content_sha256": digest(slots),
        "identity_count_sha256": digest(identity_counts),
        "item_id_totals": dict(sorted(id_counts.items())),
        "slots": slots,
    }


def vault_record(
    raw: Any,
    dimension: str,
    relative: str,
    slot: int,
    index: int,
    block_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    value = plain(raw)
    if not isinstance(value, dict) or str(value.get("id")) != VAULT_ID:
        return None
    pos = [value.get(axis) for axis in ("x", "y", "z")]
    try:
        pos = [int(axis) for axis in pos]
    except (TypeError, ValueError):
        return None
    controller = value.get("Controller")
    if not isinstance(controller, list) or len(controller) != 3:
        controller = pos
    else:
        try:
            controller = [int(axis) for axis in controller]
        except (TypeError, ValueError):
            controller = pos
    chunk = [math.floor(pos[0] / 16), math.floor(pos[2] / 16)]
    region = [math.floor(chunk[0] / 32), math.floor(chunk[1] / 32)]
    inventory = value.get("Inventory")
    inv = inventory_summary(inventory)
    return {
        "key": f"{dimension}|{pos[0]},{pos[1]},{pos[2]}",
        "dimension": dimension,
        "pos": pos,
        "controller": controller,
        "group_key": f"{dimension}|{controller[0]},{controller[1]},{controller[2]}",
        "chunk": chunk,
        "region_coords": region,
        "region_path": relative,
        "mca_slot": slot,
        "block_entity_index": index,
        "block_state": block_state or {"name": "<not-decoded>", "properties": {}, "decode": "not_decoded"},
        "last_known_pos": value.get("LastKnownPos"),
        "radius": value.get("Size"),
        "length": value.get("Length"),
        "storage_type": value.get("StorageType"),
        "keep_packed": value.get("keepPacked"),
        "inventory": inv,
    }


def read_region(path: Path, dimension: str, relative: str) -> dict[str, Any]:
    before = path.stat()
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    occupied = 0
    with path.open("rb") as handle:
        locations = handle.read(4096)
        if len(locations) != 4096:
            raise ValueError("short region location table")
        for slot in range(1024):
            entry = locations[slot * 4 : (slot + 1) * 4]
            offset = int.from_bytes(entry[:3], "big")
            if offset == 0:
                continue
            occupied += 1
            try:
                handle.seek(offset * 4096)
                length_raw = handle.read(4)
                if len(length_raw) != 4:
                    raise ValueError("short chunk length")
                length = int.from_bytes(length_raw, "big")
                compression_raw = handle.read(1)
                if not compression_raw:
                    raise ValueError("missing compression byte")
                compression = compression_raw[0]
                if compression & 0x80:
                    raise ValueError("external chunk payload unsupported")
                payload = handle.read(length - 1)
                root = nbtlib.File.parse(io.BytesIO(decompress(payload, compression)), byteorder="big")
                sections: dict[int, Any] = {}
                for section in sequence(root_value(root, "sections", "Sections")):
                    if not isinstance(section, dict):
                        continue
                    raw_y = plain(section.get("Y", section.get("y")))
                    try:
                        sections[int(raw_y)] = section
                    except (TypeError, ValueError):
                        continue
                for index, raw in enumerate(block_entities(root)):
                    state = None
                    if str(raw.get("id")) == VAULT_ID:
                        try:
                            x, y, z = (int(raw.get(axis)) for axis in ("x", "y", "z"))
                            state = block_state_at(sections, x, y, z)
                        except (TypeError, ValueError):
                            state = {"name": "<unknown-position>", "properties": {}, "decode": "invalid_position"}
                    record = vault_record(raw, dimension, relative, slot, index, state)
                    if record is not None:
                        records.append(record)
            except Exception as exc:
                errors.append({"slot": slot, "error": f"{type(exc).__name__}: {exc}"})
    after = path.stat()
    changed_during_read = before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns
    return {
        "path": str(path),
        "relative": relative,
        "dimension": dimension,
        "bytes": before.st_size,
        "mtime_ns_before": before.st_mtime_ns,
        "mtime_ns_after": after.st_mtime_ns,
        "changed_during_read": changed_during_read,
        "occupied_chunks": occupied,
        "records": records,
        "errors": errors,
    }


def discover(world: Path) -> dict[str, tuple[str, Path]]:
    output: dict[str, tuple[str, Path]] = {}
    for dimension, relative_root in DIMENSIONS:
        root = world / relative_root
        if not root.exists():
            continue
        for path in root.glob("r.*.*.mca"):
            relative = path.relative_to(world).as_posix()
            output[relative] = (dimension, path)
    return output


def scan_world(world: Path, workers: int, only_relatives: set[str] | None = None) -> dict[str, Any]:
    discovered = discover(world)
    jobs = discovered if only_relatives is None else {
        relative: value for relative, value in discovered.items() if relative in only_relatives
    }
    records: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    unstable: list[dict[str, Any]] = []
    occupied = 0
    bytes_read = 0
    completed = 0
    started = time.time()
    print(json.dumps({"phase": "discover", "world": str(world), "regions": len(jobs)}), flush=True)
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
        pending = {
            executor.submit(read_region, path, dimension, relative): relative
            for relative, (dimension, path) in jobs.items()
        }
        for future in concurrent.futures.as_completed(pending):
            relative = pending[future]
            try:
                result = future.result()
            except Exception as exc:
                errors.append({"region_path": relative, "error": f"{type(exc).__name__}: {exc}"})
            else:
                occupied += result["occupied_chunks"]
                bytes_read += result["bytes"]
                errors.extend({"region_path": relative, **item} for item in result["errors"])
                if result["changed_during_read"]:
                    unstable.append({key: result[key] for key in ("path", "mtime_ns_before", "mtime_ns_after")})
                for record in result["records"]:
                    key = record["key"]
                    if key in records:
                        errors.append({"region_path": relative, "key": key, "error": "duplicate vault coordinate"})
                    records[key] = record
            completed += 1
            if completed == len(jobs) or completed % 100 == 0:
                print(json.dumps({
                    "phase": "scan",
                    "world": str(world),
                    "completed": completed,
                    "total": len(jobs),
                    "vaults": len(records),
                    "elapsed_seconds": round(time.time() - started, 2),
                }), flush=True)
    format_counts = collections.Counter(record["inventory"]["format"] for record in records.values())
    nonempty = [record for record in records.values() if record["inventory"]["is_nonempty"]]
    return {
        "world": str(world.resolve()),
        "discovered_region_files": len(discovered),
        "region_files": len(jobs),
        "bytes_read": bytes_read,
        "occupied_chunks": occupied,
        "vault_count": len(records),
        "nonempty_vault_count": len(nonempty),
        "nonempty_slot_count": sum(record["inventory"]["nonempty_slots"] for record in nonempty),
        "total_item_count": sum(record["inventory"]["total_item_count"] for record in nonempty),
        "inventory_format_counts": dict(sorted(format_counts.items())),
        "errors": errors,
        "unstable_regions": unstable,
        "records": records,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def compact_record(record: dict[str, Any] | None, include_slots: bool = False) -> dict[str, Any] | None:
    if record is None:
        return None
    result = {key: value for key, value in record.items() if key != "inventory"}
    inventory = dict(record["inventory"])
    if not include_slots:
        inventory.pop("slots", None)
        inventory.pop("item_id_totals", None)
    result["inventory"] = inventory
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Create item-vault OTA forensics")
    parser.add_argument("--source-world", type=Path, required=True)
    parser.add_argument("--staging-world", type=Path, required=True)
    parser.add_argument("--live-world", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--workers", type=int, default=max(1, min(12, os.cpu_count() or 1)))
    args = parser.parse_args()

    source_snapshot = scan_world(args.source_world.resolve(), args.workers)
    source_vault_regions = {
        record["region_path"] for record in source_snapshot["records"].values()
    }
    snapshots = {
        "source": source_snapshot,
        "staging": scan_world(args.staging_world.resolve(), args.workers, source_vault_regions),
        "live": scan_world(args.live_world.resolve(), args.workers, source_vault_regions),
    }
    source_records = snapshots["source"]["records"]
    staging_records = snapshots["staging"]["records"]
    live_records = snapshots["live"]["records"]

    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in source_records.values():
        groups[record["group_key"]].append(record)
    affected_group_keys = {
        group_key
        for group_key, members in groups.items()
        if any(member["inventory"]["is_nonempty"] for member in members)
    }

    classifications = collections.Counter()
    restoration_ledger: list[dict[str, Any]] = []
    live_conflicts: list[dict[str, Any]] = []
    schema_blockers: list[dict[str, Any]] = []
    source_nonempty_keys = {
        key for key, record in source_records.items() if record["inventory"]["is_nonempty"]
    }
    for key in sorted(source_nonempty_keys):
        source = source_records[key]
        staging = staging_records.get(key)
        live = live_records.get(key)
        if staging is None:
            classification = "missing_staging"
        elif staging["inventory"]["format"] != "dense_list":
            classification = "staging_unexpected_schema"
        elif staging["inventory"]["nonempty_slots"] > 20:
            classification = "staging_over_capacity"
        elif live is None:
            classification = "missing_live"
        elif live["inventory"]["format"] == "neoforge_handler" and live["inventory"]["is_nonempty"]:
            classification = "live_nonempty_conflict"
        elif live["inventory"]["format"] == "neoforge_handler":
            classification = "live_emptied_after_load"
        elif live["inventory"]["format"] == "dense_list":
            classification = "live_not_loaded_legacy_schema"
        else:
            classification = "live_unexpected_schema"
        classifications[classification] += 1

        if staging is not None:
            target_items = []
            for item in staging["inventory"]["slots"]:
                stack = dict(item["stack"])
                stack["Slot"] = item["slot"]
                target_items.append(stack)
            target_inventory = {"Size": 20, "Items": target_items}
        else:
            target_inventory = None
        entry = {
            "key": key,
            "classification": classification,
            "dimension": source["dimension"],
            "pos": source["pos"],
            "controller": source["controller"],
            "group_key": source["group_key"],
            "chunk": source["chunk"],
            "region_path": source["region_path"],
            "mca_slot": source["mca_slot"],
            "source": compact_record(source, include_slots=True),
            "staging": compact_record(staging, include_slots=True),
            "live": compact_record(live, include_slots=True),
            "ota_target_inventory": target_inventory,
        }
        restoration_ledger.append(entry)
        if classification == "live_nonempty_conflict":
            live_conflicts.append(entry)
        if classification in {
            "missing_staging",
            "staging_unexpected_schema",
            "staging_over_capacity",
            "missing_live",
            "live_unexpected_schema",
        }:
            schema_blockers.append(entry)

    affected_groups: list[dict[str, Any]] = []
    affected_chunks: set[tuple[str, int, int]] = set()
    affected_regions: set[tuple[str, str]] = set()
    for group_key in sorted(affected_group_keys):
        members = sorted(groups[group_key], key=lambda item: tuple(item["pos"]))
        group_chunks = sorted({tuple(member["chunk"]) for member in members})
        group_regions = sorted({member["region_path"] for member in members})
        for chunk_x, chunk_z in group_chunks:
            affected_chunks.add((members[0]["dimension"], chunk_x, chunk_z))
        for region_path in group_regions:
            affected_regions.add((members[0]["dimension"], region_path))
        affected_groups.append({
            "group_key": group_key,
            "dimension": members[0]["dimension"],
            "controller": members[0]["controller"],
            "member_count": len(members),
            "nonempty_member_count": sum(member["inventory"]["is_nonempty"] for member in members),
            "nonempty_slot_count": sum(member["inventory"]["nonempty_slots"] for member in members),
            "total_item_count": sum(member["inventory"]["total_item_count"] for member in members),
            "chunks": [list(chunk) for chunk in group_chunks],
            "region_paths": group_regions,
            "members": [compact_record(member, include_slots=False) for member in members],
        })

    report = {
        "schema": 1,
        "read_only": True,
        "generated_at_unix": time.time(),
        "root_cause": {
            "source_schema": "Create Fly 1.21.11 ItemVaultHandler writes Inventory as a dense list of nonempty ItemStack values and reads them sequentially.",
            "target_schema": "Create 6.0.10 NeoForge calls ItemStackHandler.deserializeNBT(compound.getCompound(\"Inventory\")); it requires Inventory={Size,Items:[...Slot...]}.",
            "failure": "A list tag queried through getCompound becomes an empty compound; target Create therefore initializes all 20 slots empty and later saves the empty NeoForge handler.",
            "converter_gap": "convert_world_nbt.py converts schematicannon Inventory but has no create:item_vault Inventory converter.",
        },
        "snapshots": {
            name: {key: value for key, value in snapshot.items() if key != "records"}
            for name, snapshot in snapshots.items()
        },
        "summary": {
            "source_nonempty_vault_members": len(source_nonempty_keys),
            "affected_multiblock_groups": len(affected_groups),
            "affected_chunks": len(affected_chunks),
            "affected_regions": len(affected_regions),
            "classifications": dict(sorted(classifications.items())),
            "live_nonempty_conflicts": len(live_conflicts),
            "schema_blockers": len(schema_blockers),
        },
        "affected_chunk_set": [
            {"dimension": dimension, "chunk": [chunk_x, chunk_z]}
            for dimension, chunk_x, chunk_z in sorted(affected_chunks)
        ],
        "affected_region_set": [
            {"dimension": dimension, "region_path": region_path}
            for dimension, region_path in sorted(affected_regions)
        ],
        "affected_groups": affected_groups,
        "restoration_ledger": restoration_ledger,
        "live_nonempty_conflicts": live_conflicts,
        "schema_blockers": schema_blockers,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        summary = report["summary"]
        lines = [
            "# Create Item Vault OTA Forensics",
            "",
            "Read-only. No world file was changed and no Java process was started or stopped.",
            "",
            "## Root cause",
            "",
            "- Create Fly 1.21.11 writes each vault member's `Inventory` as a dense list of nonempty stacks.",
            "- Create 6.0.10 NeoForge requires `Inventory={Size:20,Items:[...Slot...]}`.",
            "- The migration converter did not translate `create:item_vault`; first target load read an empty compound and then persisted an empty handler.",
            "",
            "## Scope",
            "",
            f"- Source vault block entities: `{snapshots['source']['vault_count']}`; nonempty members: `{summary['source_nonempty_vault_members']}`.",
            f"- Affected multiblock groups: `{summary['affected_multiblock_groups']}`.",
            f"- Full multiblock chunk set: `{summary['affected_chunks']}` chunks in `{summary['affected_regions']}` region files.",
            f"- Live nonempty conflicts observed: `{summary['live_nonempty_conflicts']}`.",
            f"- Schema/missing blockers: `{summary['schema_blockers']}`.",
            "",
            "## OTA rule",
            "",
            "The ledger uses the already component-converted staging stacks. Each dense-list entry at index `i` becomes the same stack with `Slot=i` inside `Inventory={Size:20,Items:[...]}`. The affected chunk set includes every member of every multiblock group that had at least one nonempty source member.",
            "",
            "## Classification",
            "",
        ]
        for key, value in sorted(classifications.items()):
            lines.append(f"- `{key}`: `{value}`")
        lines.extend([
            "",
            "## Evidence files",
            "",
            f"- Full coordinate/item/chunk ledger: `{args.output.resolve()}`",
        ])
        args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "PASS" if not schema_blockers else "BLOCKED",
        **report["summary"],
        "output": str(args.output.resolve()),
        "markdown": str(args.markdown.resolve()) if args.markdown else None,
    }, ensure_ascii=False, indent=2), flush=True)
    return 0 if not schema_blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
