from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import nbtlib


DIMENSION_ROOTS = {
    "source": {
        "minecraft:overworld": "world",
        "minecraft:the_nether": "world_nether",
        "minecraft:the_end": "world_the_end",
    },
    "target": {
        "minecraft:overworld": "world",
        "minecraft:the_nether": "world/DIM-1",
        "minecraft:the_end": "world/DIM1",
    },
}


def plain(value: Any) -> Any:
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    return value


def decompress(payload: bytes, kind: int) -> bytes:
    kind &= 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported compression type {kind}")


def floor_div(value: int, divisor: int) -> int:
    return math.floor(value / divisor)


def region_address(x: int, z: int) -> tuple[int, int, int]:
    chunk_x = floor_div(x, 16)
    chunk_z = floor_div(z, 16)
    region_x = floor_div(chunk_x, 32)
    region_z = floor_div(chunk_z, 32)
    slot = (chunk_x & 31) + (chunk_z & 31) * 32
    return region_x, region_z, slot


def chunk_descriptor(dimension: str, x: int, z: int) -> dict[str, Any]:
    chunk_x = floor_div(x, 16)
    chunk_z = floor_div(z, 16)
    region_x = floor_div(chunk_x, 32)
    region_z = floor_div(chunk_z, 32)
    slot = (chunk_x & 31) + (chunk_z & 31) * 32
    return {
        "dimension": dimension,
        "chunk": [chunk_x, chunk_z],
        "region": [region_x, region_z],
        "region_file": f"r.{region_x}.{region_z}.mca",
        "slot": slot,
    }


def chunk_key(value: dict[str, Any]) -> tuple[str, int, int]:
    return value["dimension"], value["chunk"][0], value["chunk"][1]


def read_chunk(path: Path, slot: int) -> dict[str, Any] | None:
    with path.open("rb") as handle:
        header = handle.read(8192)
        if len(header) < 8192:
            raise ValueError("region header is truncated")
        entry = header[slot * 4 : (slot + 1) * 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if offset == 0:
            return None
        if sectors == 0 or offset < 2:
            raise ValueError(f"invalid allocation at slot {slot}")
        handle.seek(offset * 4096)
        length = int.from_bytes(handle.read(4), "big")
        kind = handle.read(1)[0]
        if length < 1 or length > sectors * 4096 - 4:
            raise ValueError(f"invalid payload length {length} at slot {slot}")
        raw = decompress(handle.read(length - 1), kind)
    return plain(nbtlib.File.parse(io.BytesIO(raw), byteorder="big"))


def chunk_payload_sha256(path: Path, slot: int) -> str | None:
    with path.open("rb") as handle:
        header = handle.read(8192)
        if len(header) < 8192:
            raise ValueError("region header is truncated")
        entry = header[slot * 4 : (slot + 1) * 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if offset == 0:
            return None
        if sectors == 0 or offset < 2:
            raise ValueError(f"invalid allocation at slot {slot}")
        handle.seek(offset * 4096)
        length_bytes = handle.read(4)
        length = int.from_bytes(length_bytes, "big")
        if length < 1 or length > sectors * 4096 - 4:
            raise ValueError(f"invalid payload length {length} at slot {slot}")
        encoded = length_bytes + handle.read(length)
    return hashlib.sha256(encoded).hexdigest()


def block_entities(chunk: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not chunk:
        return []
    for key in ("block_entities", "BlockEntities", "blockEntities", "TileEntities"):
        value = chunk.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    level = chunk.get("Level")
    if isinstance(level, dict):
        for key in ("block_entities", "BlockEntities", "blockEntities", "TileEntities"):
            value = level.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def position(value: dict[str, Any]) -> tuple[int, int, int] | None:
    coords = tuple(value.get(key) for key in ("x", "y", "z"))
    if all(isinstance(item, int) for item in coords):
        return coords  # type: ignore[return-value]
    return None


def get_path(value: Any, path: str) -> Any:
    current = value
    for segment in path.split(".") if path else ():
        if "[" in segment:
            key, rest = segment.split("[", 1)
            if key:
                if not isinstance(current, dict) or key not in current:
                    return None
                current = current[key]
            while rest:
                index_text, remainder = rest.split("]", 1)
                if not isinstance(current, list):
                    return None
                index = int(index_text)
                if index < 0 or index >= len(current):
                    return None
                current = current[index]
                rest = remainder[1:] if remainder.startswith("[") else ""
        else:
            if not isinstance(current, dict) or segment not in current:
                return None
            current = current[segment]
    return current


def fluid_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {"present": isinstance(value, dict), "empty": True, "raw": value}
    identifier = value.get("id")
    amount = value.get("amount")
    return {
        "present": True,
        "empty": not (isinstance(identifier, str) and isinstance(amount, int) and amount > 0),
        "id": identifier,
        "amount": amount,
        "components": value.get("components"),
        "keys": sorted(value),
        "raw": value,
    }


def expected_target_path(owner_id: str, source_path: str) -> str:
    if owner_id == "create:fluid_tank" and source_path == "Fluid":
        return "TankContent.Fluid"
    if owner_id == "create:hose_pulley" and source_path == "Fluid":
        return "Tank.Fluid"
    if source_path.endswith("TankContent"):
        return f"{source_path}.Fluid"
    return source_path


def expected_target_amount(source_record: dict[str, Any]) -> int | None:
    converted = source_record.get("target_amount")
    if isinstance(converted, int):
        return converted
    identifier = source_record.get("id")
    amount = source_record.get("amount")
    divisor = source_record.get("unit_divisor")
    if identifier == "create:potion" and isinstance(amount, int) and isinstance(divisor, int) and divisor > 0:
        return (amount + divisor // 2) // divisor
    return None


def category(owner_id: str, source_path: str) -> str:
    if ".Flow." in source_path or ".OpenEnd." in source_path:
        return "transient_transport"
    if owner_id == "create:fluid_tank":
        return "multiblock_tank"
    if owner_id == "create:hose_pulley":
        return "hose_internal_tank"
    if "TankContent" in source_path:
        return "machine_internal_tank"
    return "other_persisted_fluid"


def locate_block_entity(
    server_root: Path,
    layout: str,
    dimension: str,
    pos: tuple[int, int, int],
    cache: dict[tuple[Path, int], dict[str, Any] | None],
) -> dict[str, Any]:
    x, y, z = pos
    region_x, region_z, slot = region_address(x, z)
    dim_root = server_root / DIMENSION_ROOTS[layout][dimension]
    region_path = dim_root / "region" / f"r.{region_x}.{region_z}.mca"
    result: dict[str, Any] = {
        "dimension_root": str(dim_root),
        "region": str(region_path),
        "slot": slot,
        "region_exists": region_path.is_file(),
        "block_entity": None,
    }
    if not region_path.is_file():
        return result
    key = (region_path, slot)
    if key not in cache:
        cache[key] = read_chunk(region_path, slot)
    for value in block_entities(cache[key]):
        if position(value) == pos:
            result["block_entity"] = value
            break
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--source-audit", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()

    source_audit = json.loads(args.source_audit.read_text(encoding="utf-8"))
    grouped: dict[tuple[str, tuple[int, int, int], str], list[dict[str, Any]]] = defaultdict(list)
    for record in source_audit.get("records", []):
        if record.get("kind") != "fluid_stack":
            continue
        raw_pos = record.get("owner_pos")
        if not isinstance(raw_pos, list) or len(raw_pos) != 3 or not all(isinstance(v, int) for v in raw_pos):
            continue
        relative = str(record.get("file", "")).replace("\\", "/")
        if not relative.startswith("region/"):
            continue
        pos = tuple(raw_pos)
        grouped[("minecraft:overworld", pos, str(record.get("owner_id")))].append(record)

    caches: dict[str, dict[tuple[Path, int], dict[str, Any] | None]] = {
        "source": {},
        "staging": {},
        "runtime": {},
    }
    records: list[dict[str, Any]] = []
    for (dimension, pos, owner_id), source_records in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1], item[0][2])
    ):
        located = {
            "source": locate_block_entity(args.source_root, "source", dimension, pos, caches["source"]),
            "staging": locate_block_entity(args.staging_root, "target", dimension, pos, caches["staging"]),
            "runtime": locate_block_entity(args.runtime_root, "target", dimension, pos, caches["runtime"]),
        }
        source_be = located["source"]["block_entity"]
        staging_be = located["staging"]["block_entity"]
        runtime_be = located["runtime"]["block_entity"]
        for source_record in source_records:
            source_path = str(source_record["path"]).split("]", 1)[-1].lstrip(".")
            target_path = expected_target_path(owner_id, source_path)
            expected_id = source_record.get("target_id")
            expected_amount = expected_target_amount(source_record)
            source_value = get_path(source_be, source_path) if source_be else None
            staging_source_path_value = get_path(staging_be, source_path) if staging_be else None
            staging_target_path_value = get_path(staging_be, target_path) if staging_be else None
            runtime_source_path_value = get_path(runtime_be, source_path) if runtime_be else None
            runtime_target_path_value = get_path(runtime_be, target_path) if runtime_be else None
            staging_payload = fluid_summary(staging_source_path_value)
            runtime_target = fluid_summary(runtime_target_path_value)
            runtime_source = fluid_summary(runtime_source_path_value)
            same_runtime_owner = isinstance(runtime_be, dict) and runtime_be.get("id") == owner_id
            same_staging_owner = isinstance(staging_be, dict) and staging_be.get("id") == owner_id
            staging_payload_matches = (
                staging_payload.get("id") == expected_id
                and staging_payload.get("amount") == expected_amount
            )
            runtime_is_nonempty = not runtime_target.get("empty", True)
            source_field_differs = source_path != target_path
            force_restore_candidate = (
                source_field_differs
                and same_staging_owner
                and same_runtime_owner
                and staging_payload_matches
            )
            ota_candidate = force_restore_candidate and runtime_target.get("empty", True)
            conflict_reason = None
            if source_field_differs and not force_restore_candidate:
                if not same_staging_owner:
                    conflict_reason = "staging owner missing or changed"
                elif not same_runtime_owner:
                    conflict_reason = "runtime owner missing or changed"
                elif not staging_payload_matches:
                    conflict_reason = "converted staging payload does not match audited source conversion"
                else:
                    conflict_reason = "unclassified safety conflict"
            records.append(
                {
                    "dimension": dimension,
                    "pos": list(pos),
                    "owner_id": owner_id,
                    "category": category(owner_id, source_path),
                    "source_path": source_path,
                    "target_path": target_path,
                    "source": {
                        "id": source_record.get("id"),
                        "amount": source_record.get("amount"),
                        "target_id": expected_id,
                        "target_amount": expected_amount,
                        "max_capacity": source_record.get("max_capacity"),
                        "target_max_capacity": source_record.get("target_max_capacity"),
                        "value": fluid_summary(source_value),
                        "size": source_be.get("Size") if isinstance(source_be, dict) else None,
                        "height": source_be.get("Height") if isinstance(source_be, dict) else None,
                        "controller": source_be.get("Controller") if isinstance(source_be, dict) else None,
                    },
                    "staging": {
                        "owner_id": staging_be.get("id") if isinstance(staging_be, dict) else None,
                        "source_path_value": staging_payload,
                        "target_path_value": fluid_summary(staging_target_path_value),
                    },
                    "runtime": {
                        "owner_id": runtime_be.get("id") if isinstance(runtime_be, dict) else None,
                        "source_path_value": runtime_source,
                        "target_path_value": runtime_target,
                        "size": runtime_be.get("Size") if isinstance(runtime_be, dict) else None,
                        "height": runtime_be.get("Height") if isinstance(runtime_be, dict) else None,
                        "controller": runtime_be.get("Controller") if isinstance(runtime_be, dict) else None,
                    },
                    "ota_candidate": ota_candidate,
                    "force_restore_candidate": force_restore_candidate,
                    "runtime_was_nonempty": runtime_is_nonempty,
                    "conflict_reason": conflict_reason,
                    "locations": {
                        key: {name: value for name, value in location.items() if name != "block_entity"}
                        for key, location in located.items()
                    },
                }
            )

    categories = Counter(record["category"] for record in records)
    owners = Counter(record["owner_id"] for record in records)
    ota_records = [record for record in records if record["ota_candidate"]]
    force_restore_records = [record for record in records if record["force_restore_candidate"]]
    ota_by_owner = Counter(record["owner_id"] for record in ota_records)
    force_restore_by_owner = Counter(record["owner_id"] for record in force_restore_records)
    conflicts = [record for record in records if record["conflict_reason"]]
    runtime_nonempty = [
        record for record in force_restore_records if record["runtime_was_nonempty"]
    ]
    capacity_violations = []
    for record in force_restore_records:
        amount = record["source"].get("target_amount")
        ledger_capacity = record["source"].get("target_max_capacity")
        if isinstance(amount, int) and isinstance(ledger_capacity, int) and amount > ledger_capacity:
            capacity_violations.append(
                {
                    "dimension": record["dimension"],
                    "pos": record["pos"],
                    "owner_id": record["owner_id"],
                    "amount": amount,
                    "capacity": ledger_capacity,
                    "reason": "payload exceeds converted source capacity",
                }
            )
        if record["owner_id"] == "create:fluid_tank":
            size = record["runtime"].get("size")
            height = record["runtime"].get("height")
            if isinstance(amount, int) and isinstance(size, int) and isinstance(height, int):
                runtime_capacity = size * size * height * 8_000
                if amount > runtime_capacity:
                    capacity_violations.append(
                        {
                            "dimension": record["dimension"],
                            "pos": record["pos"],
                            "owner_id": record["owner_id"],
                            "amount": amount,
                            "capacity": runtime_capacity,
                            "reason": "payload exceeds current runtime multiblock capacity",
                        }
                    )

    multiblock_groups = []
    for controller_record in sorted(
        (record for record in records if record["owner_id"] == "create:fluid_tank"),
        key=lambda record: (record["dimension"], record["pos"]),
    ):
        dimension = controller_record["dimension"]
        controller_pos = tuple(controller_record["pos"])
        source_width = controller_record["source"].get("size")
        source_height = controller_record["source"].get("height")
        runtime_width = controller_record["runtime"].get("size")
        runtime_height = controller_record["runtime"].get("height")
        width = source_width if isinstance(source_width, int) and source_width > 0 else runtime_width
        height = source_height if isinstance(source_height, int) and source_height > 0 else runtime_height
        if not isinstance(width, int) or width <= 0 or not isinstance(height, int) or height <= 0:
            multiblock_groups.append(
                {
                    "dimension": dimension,
                    "controller": list(controller_pos),
                    "error": "controller has no usable Size/Height",
                }
            )
            continue
        members = []
        member_chunks: dict[tuple[str, int, int], dict[str, Any]] = {}
        membership_errors = []
        for dx in range(width):
            for dy in range(height):
                for dz in range(width):
                    member_pos = (
                        controller_pos[0] + dx,
                        controller_pos[1] + dy,
                        controller_pos[2] + dz,
                    )
                    member = {"pos": list(member_pos)}
                    for world_name, server_root, layout in (
                        ("source", args.source_root, "source"),
                        ("staging", args.staging_root, "target"),
                        ("runtime", args.runtime_root, "target"),
                    ):
                        located_member = locate_block_entity(
                            server_root,
                            layout,
                            dimension,
                            member_pos,
                            caches[world_name],
                        )
                        be = located_member["block_entity"]
                        member[world_name] = {
                            "owner_id": be.get("id") if isinstance(be, dict) else None,
                            "controller": be.get("Controller") if isinstance(be, dict) else None,
                            "region": located_member["region"],
                            "slot": located_member["slot"],
                        }
                        if not isinstance(be, dict) or be.get("id") != "create:fluid_tank":
                            membership_errors.append(
                                {
                                    "world": world_name,
                                    "pos": list(member_pos),
                                    "owner_id": be.get("id") if isinstance(be, dict) else None,
                                }
                            )
                    descriptor = chunk_descriptor(dimension, member_pos[0], member_pos[2])
                    member["chunk"] = descriptor
                    member_chunks[chunk_key(descriptor)] = descriptor
                    members.append(member)
        multiblock_groups.append(
            {
                "dimension": dimension,
                "controller": list(controller_pos),
                "source_size": source_width,
                "source_height": source_height,
                "runtime_size": runtime_width,
                "runtime_height": runtime_height,
                "member_count": len(members),
                "member_chunks": sorted(member_chunks.values(), key=chunk_key),
                "membership_errors": membership_errors,
                "members": members,
            }
        )

    field_chunks: dict[tuple[str, int, int], dict[str, Any]] = {}
    all_member_chunks: dict[tuple[str, int, int], dict[str, Any]] = {}
    for record in force_restore_records:
        descriptor = chunk_descriptor(record["dimension"], record["pos"][0], record["pos"][2])
        field_chunks[chunk_key(descriptor)] = descriptor
        all_member_chunks[chunk_key(descriptor)] = descriptor
    for group in multiblock_groups:
        for descriptor in group.get("member_chunks", []):
            all_member_chunks[chunk_key(descriptor)] = descriptor

    def enrich_chunk(descriptor: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(descriptor)
        files = {}
        for world_name, server_root, layout in (
            ("source", args.source_root, "source"),
            ("staging", args.staging_root, "target"),
            ("runtime", args.runtime_root, "target"),
        ):
            dimension_root = server_root / DIMENSION_ROOTS[layout][descriptor["dimension"]]
            region_path = dimension_root / "region" / descriptor["region_file"]
            stat = region_path.stat() if region_path.is_file() else None
            files[world_name] = {
                "path": str(region_path),
                "exists": region_path.is_file(),
                "region_size": stat.st_size if stat else None,
                "region_mtime_ns": stat.st_mtime_ns if stat else None,
                "chunk_payload_sha256": (
                    chunk_payload_sha256(region_path, descriptor["slot"]) if stat else None
                ),
            }
        enriched["files"] = files
        return enriched

    field_chunk_list = [
        enrich_chunk(value) for value in sorted(field_chunks.values(), key=chunk_key)
    ]
    all_member_chunk_list = [
        enrich_chunk(value) for value in sorted(all_member_chunks.values(), key=chunk_key)
    ]
    report = {
        "schema": 1,
        "read_only": True,
        "source_root": str(args.source_root.resolve()),
        "staging_root": str(args.staging_root.resolve()),
        "runtime_root": str(args.runtime_root.resolve()),
        "source_audit": str(args.source_audit.resolve()),
        "summary": {
            "source_fluid_records_with_block_positions": len(records),
            "unique_block_entities": len(grouped),
            "categories": dict(sorted(categories.items())),
            "owners": dict(sorted(owners.items())),
            "ota_candidates": len(ota_records),
            "ota_candidates_by_owner": dict(sorted(ota_by_owner.items())),
            "force_restore_candidates": len(force_restore_records),
            "force_restore_candidates_by_owner": dict(sorted(force_restore_by_owner.items())),
            "runtime_nonempty_force_overwrites": len(runtime_nonempty),
            "conflicts": len(conflicts),
            "capacity_violations": len(capacity_violations),
            "multiblock_groups": len(multiblock_groups),
            "field_chunks": len(field_chunks),
            "all_member_chunks": len(all_member_chunks),
        },
        "ota_policy": {
            "coordinate_level_only": True,
            "replace_regions": False,
            "require_same_block_entity_id": True,
            "require_converted_staging_payload_matches_source_ledger": True,
            "write_only_when_runtime_target_field_empty": True,
            "never_overwrite_nonempty_runtime_content": True,
        },
        "force_restore_policy": {
            "purpose": "test-server-only authoritative rollback of confirmed fluid-storage schema losses",
            "coordinate_level_fields": True,
            "replace_regions": False,
            "require_same_block_entity_id": True,
            "require_converted_staging_payload_matches_source_ledger": True,
            "may_overwrite_nonempty_runtime_content": True,
        },
        "ota_candidates": ota_records,
        "force_restore_candidates": force_restore_records,
        "runtime_nonempty_force_overwrites": runtime_nonempty,
        "conflicts": conflicts,
        "capacity_violations": capacity_violations,
        "multiblock_groups": multiblock_groups,
        "affected_chunks": {
            "field_chunks": field_chunk_list,
            "all_multiblock_member_chunks": all_member_chunk_list,
        },
        "records": records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.manifest:
        compact_fields = []
        for record in force_restore_records:
            compact_fields.append(
                {
                    "dimension": record["dimension"],
                    "pos": record["pos"],
                    "owner_id": record["owner_id"],
                    "category": record["category"],
                    "source_path": record["source_path"],
                    "target_path": record["target_path"],
                    "payload": record["staging"]["source_path_value"]["raw"],
                    "authoritative_source": {
                        "id": record["source"]["id"],
                        "amount": record["source"]["amount"],
                        "target_id": record["source"]["target_id"],
                        "target_amount": record["source"]["target_amount"],
                    },
                    "audited_runtime_value": record["runtime"]["target_path_value"]["raw"],
                    "runtime_was_nonempty": record["runtime_was_nonempty"],
                    "chunk": chunk_descriptor(
                        record["dimension"], record["pos"][0], record["pos"][2]
                    ),
                }
            )
        compact_groups = [
            {
                "dimension": group.get("dimension"),
                "controller": group.get("controller"),
                "size": group.get("source_size"),
                "height": group.get("source_height"),
                "member_count": group.get("member_count"),
                "member_chunks": group.get("member_chunks", []),
                "membership_errors": group.get("membership_errors", []),
            }
            for group in multiblock_groups
        ]
        manifest = {
            "schema": 1,
            "mode": "test_server_authoritative_force_restore",
            "read_only_audit": True,
            "source_root": str(args.source_root.resolve()),
            "staging_root": str(args.staging_root.resolve()),
            "runtime_root": str(args.runtime_root.resolve()),
            "preconditions": [
                "stop the server cleanly before applying",
                "take a recoverable backup of the 18 affected chunks",
                "re-audit runtime chunk hashes immediately before applying",
                "merge only listed chunks into region files; never replace a full region",
                "at each coordinate require the same block-entity id before writing",
                "write only the listed target path and payload; preserve all unrelated NBT",
            ],
            "summary": report["summary"],
            "fields": compact_fields,
            "multiblock_groups": compact_groups,
            "affected_chunks": report["affected_chunks"],
        }
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.markdown:
        lines = [
            "# Fluid storage OTA forensic report",
            "",
            "## Finding",
            "",
            "The migrated payloads were unit/id converted, but their storage envelopes still used the Fabric shape.",
            "NeoForge therefore loaded them as empty and rewrote the affected fields on save.",
            "",
            "- `create:fluid_tank`: `Fluid` -> `TankContent.Fluid`.",
            "- `create:hose_pulley`: `Fluid` -> `Tank.Fluid`.",
            "- SmartFluidTankBehaviour machines: `...TankContent` -> `...TankContent.Fluid`.",
            "",
            "## Scope",
            "",
            f"- Confirmed authoritative fields: {len(force_restore_records)} across {len({(r['dimension'], tuple(r['pos'])) for r in force_restore_records})} block entities.",
            f"- Empty-only conservative restore: {len(ota_records)} fields.",
            f"- Test-server force restore: {len(force_restore_records)} fields; {len(runtime_nonempty)} currently non-empty fields will be overwritten.",
            f"- Multiblock tanks: {len(multiblock_groups)} groups; membership errors: {sum(len(g.get('membership_errors', [])) for g in multiblock_groups)}.",
            f"- Chunks containing restored fields: {len(field_chunk_list)}.",
            f"- Chunks including every multiblock member: {len(all_member_chunk_list)}.",
            "- Dimensions affected: overworld only.",
            "- Region files affected: `r.-1.-1.mca` and `r.53.-26.mca` only.",
            "",
            "## OTA safety contract",
            "",
            "Stop the server, back up the listed chunks, verify chunk hashes, then merge only the listed chunks.",
            "Within each chunk, patch only the listed block-entity target path; preserve unrelated NBT.",
            "Do not replace either full region file or the full world.",
            "",
            "The full JSON report and compact manifest contain coordinates, payloads, multiblock membership, chunk slots, and current chunk hashes.",
        ]
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
