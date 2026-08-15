#!/usr/bin/env python3
"""Fail-closed offline Tom's Storage MCA attachment downgrade.

The fixed pipeline order is:
  itemstack_components -> block_filter_attachment -> anvil_region_rebuild

Only a new output directory may be written. The source is opened read-only.
"""
from __future__ import annotations

import argparse
import copy
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nbtlib import Byte, Compound, File, Int, IntArray, List as NbtList, String
from nbtlib.tag import Numeric


class MigrationError(RuntimeError):
    pass


FABRIC_ATTACHMENTS = "fabric:attachments"
NEOFORGE_ATTACHMENTS = "neoforge:attachments"
BLOCK_FILTER_ID = "toms_storage:block_filter"
TAG_FILTER_ID = "toms_storage:tag_filter"
SIMPLE_FILTER_ID = "toms_storage:simple_item_filter"
VALID_SIDES = {"down", "up", "north", "south", "east", "west"}
PRIORITIES = {"lowest": 0, "low": 1, "normal": 2, "high": 3, "highest": 4}
LEGACY_FIELDS = {"connected", "filter", "keep_last", "pos", "priority", "side", "skip"}
TAG_FILTER_FIELDS = {"allow_list", "tags"}
SIMPLE_FILTER_FIELDS = {"allow_list", "match_component", "stacks"}


@dataclass(frozen=True)
class ManifestEntry:
    dimension: str
    x: int
    y: int
    z: int
    rel_file: str

    @property
    def key(self) -> tuple[int, int, int]:
        return self.x, self.y, self.z

    @property
    def region_path(self) -> str:
        return self.rel_file.replace("\\", "/")


@dataclass
class RegionRecord:
    slot: int
    chunk_x: int
    chunk_z: int
    record_bytes: bytes
    compression: int
    external: bool
    root: File


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: Any) -> Any:
    if isinstance(value, Compound):
        return {str(key): canonical(value[key]) for key in sorted(value.keys(), key=str)}
    if isinstance(value, (NbtList, list, tuple)):
        return [canonical(item) for item in value]
    if isinstance(value, IntArray):
        return [int(item) for item in value]
    if isinstance(value, Numeric):
        return int(value) if float(value).is_integer() else float(value)
    if isinstance(value, String):
        return str(value)
    return value


def as_int(tag: Any, field: str, context: str) -> int:
    if not isinstance(tag, Numeric):
        raise MigrationError(f"{context}: {field} must be numeric")
    value = float(tag)
    if not math.isfinite(value) or int(value) != value:
        raise MigrationError(f"{context}: {field} must be an integer")
    return int(value)


def as_string(tag: Any, field: str, context: str) -> str:
    if not isinstance(tag, String):
        raise MigrationError(f"{context}: {field} must be a string")
    return str(tag)


def as_bool(tag: Any, field: str, context: str) -> bool:
    if tag is None:
        return False
    if isinstance(tag, Numeric):
        return as_int(tag, field, context) != 0
    if isinstance(tag, String) and str(tag).lower() in {"true", "false"}:
        return str(tag).lower() == "true"
    raise MigrationError(f"{context}: {field} must be boolean/numeric")


def coordinates(tag: Any, field: str, context: str) -> tuple[int, int, int]:
    values: list[int] | None = None
    if isinstance(tag, IntArray):
        values = [as_int(item, field, context) for item in tag]
    elif isinstance(tag, (NbtList, list, tuple)) and len(tag) == 3:
        values = [as_int(item, f"{field}[{i}]", context) for i, item in enumerate(tag)]
    elif isinstance(tag, Compound) and all(k in tag for k in ("x", "y", "z")):
        values = [
            as_int(tag["x"], "x", f"{context}:{field}"),
            as_int(tag["y"], "y", f"{context}:{field}"),
            as_int(tag["z"], "z", f"{context}:{field}"),
        ]
    if values is None or len(values) != 3:
        raise MigrationError(f"{context}: {field} must contain exactly three integer coordinates")
    return values[0], values[1], values[2]


def normalize_bool(tag: Any, field: str, context: str) -> Byte:
    return Byte(1 if as_bool(tag, field, context) else 0)


def nbt_root(raw: bytes, context: str) -> File:
    try:
        return File.parse(io.BytesIO(raw))
    except Exception as exc:
        raise MigrationError(f"{context}: NBT parse failed: {exc}") from exc


def nbt_bytes(root: File) -> bytes:
    stream = io.BytesIO()
    root.write(stream)
    return stream.getvalue()


def decompress_chunk(compression: int, payload: bytes, context: str) -> bytes:
    try:
        if compression == 1:
            return gzip.decompress(payload)
        if compression == 2:
            return zlib.decompress(payload)
        if compression == 3:
            return payload
    except Exception as exc:
        raise MigrationError(f"{context}: decompression failed: {exc}") from exc
    raise MigrationError(f"{context}: unsupported compression type {compression}")


def compress_chunk(compression: int, raw: bytes, context: str) -> bytes:
    if compression == 1:
        return gzip.compress(raw, mtime=0)
    if compression == 2:
        return zlib.compress(raw, level=6)
    if compression == 3:
        return raw
    raise MigrationError(f"{context}: unsupported compression type {compression}")


def read_manifest(path: Path) -> list[ManifestEntry]:
    entries: list[ManifestEntry] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                entries.append(ManifestEntry(
                    str(row["dimension"]), int(row["x"]), int(row["y"]), int(row["z"]),
                    str(row["file"]).replace("\\", "/"),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                raise MigrationError(f"invalid manifest row: {row}") from exc
    if not entries or len({entry.key for entry in entries}) != len(entries):
        raise MigrationError("manifest is empty or contains duplicate coordinates")
    return entries


def block_entities(root: File, context: str) -> list[Compound]:
    values = root.get("block_entities", root.get("TileEntities"))
    if values is None:
        return []
    if not isinstance(values, (NbtList, list, tuple)):
        raise MigrationError(f"{context}: block_entities is not a list")
    for index, value in enumerate(values):
        if not isinstance(value, Compound):
            raise MigrationError(f"{context}: block_entities[{index}] is not a compound")
    # Return the live NBT list so a converted block entity can be replaced in
    # the parsed chunk before it is serialized.
    return values


def attachment_payload(be: Compound, namespace: str) -> Any:
    root = be.get(namespace)
    return root.get(BLOCK_FILTER_ID) if isinstance(root, Compound) else None


def normalize_tag_filter(payload: Any, context: str, counters: dict[str, int]) -> Compound:
    if not isinstance(payload, Compound):
        raise MigrationError(f"{context}: {TAG_FILTER_ID} must be a compound")
    unknown = set(payload.keys()) - TAG_FILTER_FIELDS
    if unknown:
        raise MigrationError(f"{context}: unsupported {TAG_FILTER_ID} fields {sorted(map(str, unknown))}")
    tags = payload.get("tags")
    if not isinstance(tags, (NbtList, list, tuple)):
        raise MigrationError(f"{context}: {TAG_FILTER_ID}.tags must be a list")
    values = [String(as_string(value, f"tags[{index}]", context))
              for index, value in enumerate(tags)]
    counters["component_payloads"] += 1
    return Compound({
        "allow_list": normalize_bool(payload.get("allow_list"), "allow_list", context),
        "tags": NbtList[String](values),
    })


def normalize_simple_filter(payload: Any, context: str, counters: dict[str, int]) -> Compound:
    if not isinstance(payload, Compound):
        raise MigrationError(f"{context}: {SIMPLE_FILTER_ID} must be a compound")
    unknown = set(payload.keys()) - SIMPLE_FILTER_FIELDS
    if unknown:
        raise MigrationError(
            f"{context}: unsupported {SIMPLE_FILTER_ID} fields {sorted(map(str, unknown))}"
        )
    stacks = payload.get("stacks")
    if not isinstance(stacks, (NbtList, list, tuple)) or len(stacks) != 9:
        raise MigrationError(f"{context}: {SIMPLE_FILTER_ID}.stacks must contain exactly 9 entries")
    values = [
        normalize_item_stack(stack, f"{context}:stacks[{index}]", counters)
        for index, stack in enumerate(stacks)
    ]
    counters["component_payloads"] += 1
    return Compound({
        "allow_list": normalize_bool(payload.get("allow_list"), "allow_list", context),
        "match_component": normalize_bool(payload.get("match_component"), "match_component", context),
        "stacks": NbtList[Compound](values),
    })


def normalize_item_stack(stack: Any, context: str, counters: dict[str, int]) -> Compound:
    """Normalize audited filter stacks; unknown schema is a hard error."""
    if not isinstance(stack, Compound):
        raise MigrationError(f"{context}: ItemStack must be a compound")
    if not stack:
        return copy.deepcopy(stack)
    allowed = {"id", "count", "components"}
    unknown = set(stack.keys()) - allowed
    if unknown:
        raise MigrationError(f"{context}: unsupported ItemStack fields {sorted(map(str, unknown))}")
    item_id = as_string(stack.get("id"), "id", context)
    count = as_int(stack.get("count"), "count", context)
    if not item_id or count <= 0:
        raise MigrationError(f"{context}: invalid ItemStack id/count")
    result = Compound({"id": String(item_id), "count": Int(count)})
    components = stack.get("components")
    if components is not None:
        if not isinstance(components, Compound):
            raise MigrationError(f"{context}: components must be a compound")
        normalized = Compound()
        for component_id, payload in components.items():
            component_id = str(component_id)
            if component_id == TAG_FILTER_ID:
                normalized[component_id] = normalize_tag_filter(payload, context, counters)
            elif component_id == SIMPLE_FILTER_ID:
                normalized[component_id] = normalize_simple_filter(payload, context, counters)
            else:
                raise MigrationError(
                    f"{context}: no 1.21.1 converter registered for component {component_id}"
                )
        result["components"] = normalized
        counters["components"] += len(normalized)
    counters["itemstacks"] += 1
    return result


def migrate_attachment(
    block_entity: Compound,
    holder: tuple[int, int, int],
    counters: dict[str, int],
) -> tuple[str, Compound, list[str]]:
    """Convert one block entity; input is never mutated."""
    context = f"block_filter@{holder[0]},{holder[1]},{holder[2]}"
    result = copy.deepcopy(block_entity)
    fabric_root = result.get(FABRIC_ATTACHMENTS)
    neo_root = result.get(NEOFORGE_ATTACHMENTS)
    if fabric_root is not None and not isinstance(fabric_root, Compound):
        raise MigrationError(f"{context}: {FABRIC_ATTACHMENTS} is not a compound")
    if neo_root is not None and not isinstance(neo_root, Compound):
        raise MigrationError(f"{context}: {NEOFORGE_ATTACHMENTS} is not a compound")
    fabric = fabric_root
    neo = neo_root
    legacy = fabric.get(BLOCK_FILTER_ID) if fabric is not None else None
    target = neo.get(BLOCK_FILTER_ID) if neo is not None else None
    if target is not None:
        if not isinstance(target, Compound):
            raise MigrationError(f"{context}: NeoForge block_filter is not a compound")
        status = "NEOFORGE_WINS_CONFLICT" if legacy is not None else "ALREADY_NEOFORGE"
        warning = ["NeoForge attachment wins; legacy Fabric payload retained"] if legacy is not None else []
        return status, result, warning
    if legacy is None:
        return "NO_LEGACY", result, []
    if not isinstance(legacy, Compound):
        raise MigrationError(f"{context}: legacy block_filter is not a compound")
    unknown = set(legacy.keys()) - LEGACY_FIELDS
    if unknown:
        raise MigrationError(f"{context}: unsupported legacy fields {sorted(map(str, unknown))}")
    source_pos = coordinates(legacy.get("pos"), "pos", context)
    if source_pos != holder:
        raise MigrationError(f"{context}: pos {source_pos} does not match holder {holder}")
    connected = legacy.get("connected")
    if not isinstance(connected, (NbtList, list, tuple)):
        raise MigrationError(f"{context}: connected must be a list")
    seen: set[tuple[int, int, int]] = set()
    connected_out = []
    for index, value in enumerate(connected):
        absolute = coordinates(value, f"connected[{index}]", context)
        if absolute in seen:
            continue
        seen.add(absolute)
        connected_out.append(Compound({
            "x": Int(absolute[0] - holder[0]),
            "y": Int(absolute[1] - holder[1]),
            "z": Int(absolute[2] - holder[2]),
        }))
    side = as_string(legacy.get("side"), "side", context).lower()
    if side not in VALID_SIDES:
        raise MigrationError(f"{context}: unknown side {side!r}")
    priority_tag = legacy.get("priority")
    if isinstance(priority_tag, Numeric):
        priority = as_int(priority_tag, "priority", context)
        if priority < 0 or priority > 4:
            raise MigrationError(f"{context}: priority ordinal out of range: {priority}")
    else:
        priority_name = as_string(priority_tag, "priority", context).lower()
        if priority_name not in PRIORITIES:
            raise MigrationError(f"{context}: unknown priority {priority_name!r}")
        priority = PRIORITIES[priority_name]
    filter_tag = legacy.get("filter")
    if filter_tag is not None and not isinstance(filter_tag, Compound):
        raise MigrationError(f"{context}: filter must be a compound")
    converted_filter = None
    if isinstance(filter_tag, Compound) and len(filter_tag) > 0:
        converted_filter = normalize_item_stack(filter_tag, context, counters)
    target_payload = Compound({
        "connected": NbtList[Compound](connected_out),
        "skip": normalize_bool(legacy.get("skip"), "skip", context),
        "side": String(side),
        "priority": Int(priority),
        "keepLast": normalize_bool(legacy.get("keep_last"), "keep_last", context),
    })
    if converted_filter is not None:
        target_payload["filter"] = converted_filter
    if neo is None:
        neo = Compound()
        result[NEOFORGE_ATTACHMENTS] = neo
    neo[BLOCK_FILTER_ID] = target_payload
    if fabric is not None:
        del fabric[BLOCK_FILTER_ID]
        if len(fabric) == 0:
            del result[FABRIC_ATTACHMENTS]
    counters["attachments_converted"] += 1
    return "CONVERTED", result, ["ItemStack/component stage completed before attachment stage"]


def load_region(path: Path) -> tuple[bytes, list[RegionRecord | None]]:
    data = path.read_bytes()
    if len(data) < 8192:
        raise MigrationError(f"{path}: MCA header shorter than 8192 bytes")
    match = re.match(r"r\.(-?\d+)\.(-?\d+)\.mca$", path.name)
    if not match:
        raise MigrationError(f"{path}: unsupported region filename")
    region_x, region_z = int(match.group(1)), int(match.group(2))
    header = data[:8192]
    records: list[RegionRecord | None] = [None] * 1024
    occupied: set[int] = set()
    sector_limit = (len(data) + 4095) // 4096
    for slot in range(1024):
        location = struct.unpack_from(">I", header, slot * 4)[0]
        sector, sector_count = location >> 8, location & 0xFF
        if sector == 0 or sector_count == 0:
            continue
        if sector < 2 or sector + sector_count > sector_limit:
            raise MigrationError(f"{path}: invalid sector range at slot {slot}")
        if any(index in occupied for index in range(sector, sector + sector_count)):
            raise MigrationError(f"{path}: overlapping allocation at slot {slot}")
        occupied.update(range(sector, sector + sector_count))
        record_bytes = data[sector * 4096:(sector + sector_count) * 4096]
        length = struct.unpack_from(">I", record_bytes, 0)[0]
        if length < 1 or length > sector_count * 4096 - 4:
            raise MigrationError(f"{path}: invalid chunk length at slot {slot}")
        compression_raw = record_bytes[4]
        external = bool(compression_raw & 0x80)
        compression = compression_raw & 0x7F
        chunk_x = region_x * 32 + slot % 32
        chunk_z = region_z * 32 + slot // 32
        payload = record_bytes[5:4 + length]
        if external:
            sidecar = path.parent / f"c.{chunk_x}.{chunk_z}.mcc"
            if not sidecar.is_file():
                raise MigrationError(f"{path}: missing external chunk {sidecar.name}")
            payload = sidecar.read_bytes()
        raw = decompress_chunk(compression, payload, f"{path.name} slot {slot}")
        records[slot] = RegionRecord(
            slot, chunk_x, chunk_z, record_bytes, compression, external,
            nbt_root(raw, f"{path.name} slot {slot}"),
        )
    return header, records


def replacement_record(record: RegionRecord, root: File, context: str) -> bytes:
    if record.external:
        raise MigrationError(f"{context}: external chunks cannot be rewritten")
    payload = compress_chunk(record.compression, nbt_bytes(root), context)
    length = len(payload) + 1
    sectors = (length + 4095) // 4096
    if sectors > 255:
        raise MigrationError(f"{context}: rebuilt chunk exceeds 255 sectors")
    return struct.pack(">I", length) + bytes([record.compression]) + payload


def rebuild_region(
    destination: Path,
    source_header: bytes,
    records: list[RegionRecord | None],
    replacements: dict[int, bytes],
) -> None:
    header = bytearray(source_header)
    output = bytearray(b"\x00" * 8192)
    sector = 2
    for slot, record in enumerate(records):
        if record is None:
            continue
        record_bytes = replacements.get(slot, record.record_bytes)
        sectors = (len(record_bytes) + 4095) // 4096
        if sectors < 1 or sectors > 255:
            raise MigrationError(f"{destination.name}: invalid rebuilt sector count")
        struct.pack_into(">I", header, slot * 4, (sector << 8) | sectors)
        output.extend(record_bytes)
        output.extend(b"\x00" * (sectors * 4096 - len(record_bytes)))
        sector += sectors
    output[:8192] = header
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + f".tmp-{os.getpid()}")
    if temporary.exists():
        raise MigrationError(f"refusing stale temporary output: {temporary}")
    with temporary.open("wb") as stream:
        stream.write(output)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)


def replace_expected(
    root: File,
    expected: dict[tuple[int, int, int], ManifestEntry],
    region_rel: str,
    counters: dict[str, int],
) -> tuple[list[dict[str, Any]], set[tuple[int, int, int]], bool]:
    statuses: list[dict[str, Any]] = []
    found: set[tuple[int, int, int]] = set()
    changed = False
    values = block_entities(root, region_rel)
    for index, be in enumerate(values):
        if not all(key in be for key in ("x", "y", "z")):
            continue
        holder = (
            as_int(be["x"], "x", region_rel),
            as_int(be["y"], "y", region_rel),
            as_int(be["z"], "z", region_rel),
        )
        if holder not in expected:
            if attachment_payload(be, FABRIC_ATTACHMENTS) is not None:
                raise MigrationError(f"{region_rel}: legacy attachment outside manifest at {holder}")
            continue
        if holder in found:
            raise MigrationError(f"{region_rel}: duplicate block entity at {holder}")
        found.add(holder)
        status, migrated, warnings = migrate_attachment(be, holder, counters)
        statuses.append({
            "dimension": expected[holder].dimension,
            "x": holder[0], "y": holder[1], "z": holder[2],
            "file": region_rel, "status": status, "warnings": warnings,
        })
        if status == "CONVERTED":
            values[index] = migrated
            changed = True
    return statuses, found, changed


def convert_world(
    source_world: Path,
    target_world: Path,
    manifest_path: Path,
    write: bool,
) -> dict[str, Any]:
    source_world = source_world.resolve()
    target_world = target_world.resolve()
    manifest_path = manifest_path.resolve()
    if source_world == target_world:
        raise MigrationError("source and target world paths must differ")
    if not source_world.is_dir():
        raise MigrationError(f"source world does not exist: {source_world}")
    entries = read_manifest(manifest_path)
    expected_all = {entry.key: entry for entry in entries}
    by_region: dict[str, list[ManifestEntry]] = {}
    for entry in entries:
        by_region.setdefault(entry.region_path, []).append(entry)
    if write:
        if target_world.exists() and any(target_world.iterdir()):
            raise MigrationError(f"refusing non-empty target world: {target_world}")
        target_world.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "pipeline": [
            "itemstack_components_1.21.11_to_1.21.1",
            "toms_storage_block_filter_attachment",
            "anvil_region_rebuild",
        ],
        "source_world": str(source_world),
        "target_world": str(target_world),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "write_enabled": write,
        "regions": [], "statuses": [], "errors": [],
        "counts": {
            "expected_coordinates": len(entries), "found_coordinates": 0,
            "converted": 0, "already_neoforge": 0,
            "target_wins_conflict": 0, "no_legacy": 0,
            "writes": 0, "itemstacks": 0, "components": 0,
            "component_payloads": 0, "attachments_converted": 0,
        },
    }
    for region_rel, region_entries in sorted(by_region.items()):
        source_path = source_world / Path(region_rel)
        if not source_path.is_file():
            raise MigrationError(f"missing source region: {source_path}")
        before = source_path.stat()
        source_hash = sha256_file(source_path)
        header, records = load_region(source_path)
        expected = {entry.key: entry for entry in region_entries}
        statuses: list[dict[str, Any]] = []
        replacements: dict[int, bytes] = {}
        found_region: set[tuple[int, int, int]] = set()
        counters = {"attachments_converted": 0, "itemstacks": 0,
                    "components": 0, "component_payloads": 0}
        for record in records:
            if record is None:
                continue
            chunk_expected = {
                key: value for key, value in expected.items()
                if key[0] // 16 == record.chunk_x and key[2] // 16 == record.chunk_z
            }
            if not chunk_expected:
                for be in block_entities(record.root, f"{region_rel} slot {record.slot}"):
                    if attachment_payload(be, FABRIC_ATTACHMENTS) is not None:
                        raise MigrationError(
                            f"{region_rel}: legacy attachment outside manifest at "
                            f"{be.get('x')},{be.get('y')},{be.get('z')}"
                        )
                continue
            chunk_statuses, found, changed = replace_expected(
                record.root, chunk_expected, region_rel, counters
            )
            statuses.extend(chunk_statuses)
            found_region.update(found)
            if changed:
                replacements[record.slot] = replacement_record(
                    record, record.root, f"{region_rel} slot {record.slot}"
                )
        if found_region != set(expected):
            raise MigrationError(
                f"{region_rel}: expected coordinates missing: {sorted(set(expected) - found_region)}"
            )
        after = source_path.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise MigrationError(f"source changed while reading: {source_path}")
        target_path = target_world / Path(region_rel)
        if write:
            if replacements:
                rebuild_region(target_path, header, records, replacements)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
            report["counts"]["writes"] += len(replacements)
        for key, value in counters.items():
            report["counts"][key] += value
        report["counts"]["found_coordinates"] += len(found_region)
        report["statuses"].extend(statuses)
        report["regions"].append({
            "file": region_rel, "source_sha256": source_hash,
            "source_bytes": before.st_size, "changed_chunk_count": len(replacements),
            "touched_slots": sorted(replacements),
            "target": str(target_path) if write else None,
        })
    for status in report["statuses"]:
        name = status["status"]
        if name == "CONVERTED":
            report["counts"]["converted"] += 1
        elif name == "ALREADY_NEOFORGE":
            report["counts"]["already_neoforge"] += 1
        elif name == "NEOFORGE_WINS_CONFLICT":
            report["counts"]["target_wins_conflict"] += 1
        elif name == "NO_LEGACY":
            report["counts"]["no_legacy"] += 1
    report["ok"] = (
        report["counts"]["found_coordinates"] == report["counts"]["expected_coordinates"]
        and not report["errors"]
    )
    return report


def semantic_payload(be: Compound, holder: tuple[int, int, int]) -> dict[str, Any]:
    root = be.get(NEOFORGE_ATTACHMENTS)
    payload = root.get(BLOCK_FILTER_ID) if isinstance(root, Compound) else None
    if not isinstance(payload, Compound):
        root = be.get(FABRIC_ATTACHMENTS)
        payload = root.get(BLOCK_FILTER_ID) if isinstance(root, Compound) else None
    if not isinstance(payload, Compound):
        raise MigrationError(f"no block_filter payload at {holder}")
    connected_absolute = []
    for value in payload.get("connected", []):
        if isinstance(value, Compound) and all(k in value for k in ("x", "y", "z")):
            connected_absolute.append([
                holder[0] + as_int(value["x"], "x", str(holder)),
                holder[1] + as_int(value["y"], "y", str(holder)),
                holder[2] + as_int(value["z"], "z", str(holder)),
            ])
        else:
            connected_absolute.append(list(coordinates(value, "connected", str(holder))))
    result = {
        "connected_absolute": sorted(connected_absolute),
        "side": str(payload.get("side", "")),
        "priority": (
            as_int(payload.get("priority"), "priority", str(holder))
            if isinstance(payload.get("priority"), Numeric)
            else PRIORITIES.get(str(payload.get("priority", "")).lower(), -1)
        ),
        "skip": as_bool(payload.get("skip"), "skip", str(holder)),
        "keepLast": as_bool(payload.get("keepLast", payload.get("keep_last")), "keepLast", str(holder)),
        "filter": canonical(payload.get("filter", Compound())),
    }
    return result


def make_target_wins_fixture(entries: list[ManifestEntry]) -> dict[str, Any]:
    entry = entries[0]
    holder = entry.key
    legacy = Compound({
        "pos": IntArray(holder),
        "connected": NbtList[IntArray]([IntArray(holder)]),
        "skip": Byte(0), "side": String("down"),
        "priority": String("lowest"), "keep_last": Byte(0), "filter": Compound(),
    })
    target = Compound({
        "connected": NbtList[Compound]([Compound({"x": Int(0), "y": Int(0), "z": Int(0)})]),
        "skip": Byte(0), "side": String("down"), "priority": Int(4), "keepLast": Byte(0),
    })
    block_entity = Compound({
        "x": Int(holder[0]), "y": Int(holder[1]), "z": Int(holder[2]),
        FABRIC_ATTACHMENTS: Compound({BLOCK_FILTER_ID: legacy}),
        NEOFORGE_ATTACHMENTS: Compound({BLOCK_FILTER_ID: target}),
    })
    counters = {"attachments_converted": 0, "itemstacks": 0,
                "components": 0, "component_payloads": 0}
    status, result, warnings = migrate_attachment(block_entity, holder, counters)
    semantic = semantic_payload(result, holder)
    return {
        "coordinate": list(holder), "status": status, "warnings": warnings,
        "target_priority": semantic["priority"],
        "legacy_retained": attachment_payload(result, FABRIC_ATTACHMENTS) is not None,
        "ok": status == "NEOFORGE_WINS_CONFLICT" and semantic["priority"] == 4,
    }


def scan_semantics(world: Path, manifest: Path) -> dict[tuple[int, int, int], dict[str, Any]]:
    entries = read_manifest(manifest)
    expected = {entry.key: entry for entry in entries}
    result: dict[tuple[int, int, int], dict[str, Any]] = {}
    for rel in sorted({entry.region_path for entry in entries}):
        _, records = load_region(world / Path(rel))
        for record in records:
            if record is None:
                continue
            for be in block_entities(record.root, rel):
                if not all(key in be for key in ("x", "y", "z")):
                    continue
                holder = tuple(as_int(be[key], key, rel) for key in ("x", "y", "z"))
                if holder in expected:
                    if holder in result:
                        raise MigrationError(f"{rel}: duplicate semantic coordinate {holder}")
                    result[holder] = semantic_payload(be, holder)
    if set(result) != set(expected):
        raise MigrationError(f"{world}: semantic coordinate set mismatch")
    return result


def semantic_audit(
    source: dict[tuple[int, int, int], dict[str, Any]],
    first: dict[tuple[int, int, int], dict[str, Any]],
    second: dict[tuple[int, int, int], dict[str, Any]],
) -> dict[str, Any]:
    names = {0: "lowest", 1: "low", 2: "normal", 3: "high", 4: "highest"}
    def summary(values: dict[tuple[int, int, int], dict[str, Any]]) -> dict[str, Any]:
        priority = {}
        for value in values.values():
            name = names.get(value["priority"], f"ordinal-{value['priority']}")
            priority[name] = priority.get(name, 0) + 1
        return {
            "count": len(values),
            "priority": priority,
            "nonempty_filters": sum(bool(value["filter"]) for value in values.values()),
            "connected_self": sum(
                value["connected_absolute"] == [list(holder)]
                for holder, value in values.items()
            ),
        }
    return {
        "source": summary(source),
        "first_target": summary(first),
        "second_target": summary(second),
        "source_equals_first": source == first,
        "first_equals_second": first == second,
        "per_coordinate": {
            ",".join(map(str, holder)): {
                "source": source[holder], "target": first[holder]
            } for holder in sorted(source)
        },
    }


def region_integrity_audit(
    source_world: Path,
    target_world: Path,
    manifest: Path,
    touched: dict[str, set[int]],
) -> dict[str, Any]:
    entries = read_manifest(manifest)
    result: dict[str, Any] = {}
    for rel in sorted({entry.region_path for entry in entries}):
        source_header, source_records = load_region(source_world / Path(rel))
        target_header, target_records = load_region(target_world / Path(rel))
        source_slots = {index for index, record in enumerate(source_records) if record is not None}
        target_slots = {index for index, record in enumerate(target_records) if record is not None}
        touched_slots = touched.get(rel, set())
        unchanged_equal = 0
        unchanged_total = 0
        for slot in sorted(source_slots - touched_slots):
            unchanged_total += 1
            if source_records[slot].record_bytes == target_records[slot].record_bytes:
                unchanged_equal += 1
        item = {
            "occupied_slots_equal": source_slots == target_slots,
            "timestamp_table_equal": source_header[4096:8192] == target_header[4096:8192],
            "touched_slots": sorted(touched_slots),
            "unchanged_record_bytes_equal": unchanged_equal,
            "unchanged_record_count": unchanged_total,
            "ok": (
                source_slots == target_slots
                and source_header[4096:8192] == target_header[4096:8192]
                and unchanged_equal == unchanged_total
            ),
        }
        result[rel] = item
    return result


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=True)
        stream.write("\n")


def prepare_fixture(source_world: Path, fixture_root: Path, manifest: Path) -> Path:
    if fixture_root.exists():
        raise MigrationError(f"refusing existing fixture root: {fixture_root}")
    entries = read_manifest(manifest)
    fixture_world = fixture_root / "source-world"
    for rel in sorted({entry.region_path for entry in entries}):
        source = source_world / Path(rel)
        if not source.is_file():
            raise MigrationError(f"missing source region for fixture: {source}")
        destination = fixture_world / Path(rel)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    fixture_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest, fixture_root / "manifest.csv")
    return fixture_world


def run_fixture(source_world: Path, fixture_root: Path, manifest: Path) -> dict[str, Any]:
    fixture_source = prepare_fixture(source_world.resolve(), fixture_root.resolve(), manifest.resolve())
    manifest_copy = fixture_root / "manifest.csv"
    first = fixture_root / "converted-world"
    second = fixture_root / "idempotent-world"
    first_report = convert_world(fixture_source, first, manifest_copy, True)
    if first_report["counts"]["converted"] != 7 or first_report["counts"]["found_coordinates"] != 7:
        raise MigrationError(f"first pass is not 7/7: {first_report['counts']}")
    second_report = convert_world(first, second, manifest_copy, True)
    second_ok = (
        second_report["counts"]["already_neoforge"] == 7
        and second_report["counts"]["converted"] == 0
        and second_report["counts"]["writes"] == 0
    )
    if not second_ok:
        raise MigrationError(f"second pass is not idempotent: {second_report['counts']}")
    target_wins = make_target_wins_fixture(read_manifest(manifest_copy))
    if not target_wins["ok"]:
        raise MigrationError(f"target-wins fixture failed: {target_wins}")
    semantics = semantic_audit(
        scan_semantics(fixture_source, manifest_copy),
        scan_semantics(first, manifest_copy),
        scan_semantics(second, manifest_copy),
    )
    if (
        not semantics["source_equals_first"]
        or not semantics["first_equals_second"]
        or semantics["first_target"]["priority"] != {"lowest": 1, "normal": 3, "highest": 3}
        or semantics["first_target"]["nonempty_filters"] != 3
        or semantics["first_target"]["connected_self"] != 7
    ):
        raise MigrationError(f"semantic audit failed: {semantics}")
    touched = {
        region["file"]: set(region["touched_slots"])
        for region in first_report["regions"]
    }
    integrity = region_integrity_audit(fixture_source, first, manifest_copy, touched)
    if not all(item["ok"] for item in integrity.values()):
        raise MigrationError(f"region integrity audit failed: {integrity}")
    result = {
        "tool": "toms_global_mca_downgrade.py",
        "fixture_source": str(fixture_source),
        "first_pass": first_report,
        "second_pass": second_report,
        "target_wins_fixture": target_wins,
        "semantic_audit": semantics,
        "region_integrity_audit": integrity,
        "region_hashes": {
            "source": {
                entry.region_path: sha256_file(fixture_source / Path(entry.region_path))
                for entry in read_manifest(manifest_copy)
            },
            "first_target": {
                entry.region_path: sha256_file(first / Path(entry.region_path))
                for entry in read_manifest(manifest_copy)
            },
            "second_target": {
                entry.region_path: sha256_file(second / Path(entry.region_path))
                for entry in read_manifest(manifest_copy)
            },
        },
        "ok": first_report["ok"] and second_ok and target_wins["ok"],
    }
    write_json(fixture_root / "fixture-report.json", result)
    return result


def make_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    convert = sub.add_parser("convert")
    convert.add_argument("--source-world", type=Path, required=True)
    convert.add_argument("--target-world", type=Path, required=True)
    convert.add_argument("--manifest", type=Path, required=True)
    convert.add_argument("--write", action="store_true")
    convert.add_argument("--report", type=Path, required=True)
    fixture = sub.add_parser("fixture")
    fixture.add_argument("--source-world", type=Path, required=True)
    fixture.add_argument("--fixture-root", type=Path, required=True)
    fixture.add_argument("--manifest", type=Path, required=True)
    fixture.add_argument("--report", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        if args.command == "convert":
            report = convert_world(args.source_world, args.target_world, args.manifest, args.write)
            write_json(args.report, report)
            print(json.dumps(report["counts"], sort_keys=True))
            return 0 if report["ok"] else 2
        report = run_fixture(args.source_world, args.fixture_root, args.manifest)
        if args.report:
            write_json(args.report, report)
        print(json.dumps({
            "ok": report["ok"],
            "first": report["first_pass"]["counts"],
            "second": report["second_pass"]["counts"],
            "target_wins": report["target_wins_fixture"],
        }, sort_keys=True))
        return 0 if report["ok"] else 2
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
