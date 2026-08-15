"""Read-only, whole-world transfer audit for Anvil region trees.

The audit compares a converted staging world with a saved target copy.  It
walks every occupied slot in all three vanilla dimensions for ``region``,
``entities`` and ``poi`` trees, while retaining only bounded summaries rather
than copying arbitrary NBT into the report.  Identical MCA files are parsed
once; changed files are parsed on both sides.  A changed compressed payload is
therefore not treated as a gameplay loss by itself.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import copy
import gzip
import hashlib
import io
import json
import re
import time
import uuid
import zlib
from pathlib import Path
from typing import Any

import nbtlib


DIMENSIONS = {
    "minecraft:overworld": Path("."),
    "minecraft:the_nether": Path("DIM-1"),
    "minecraft:the_end": Path("DIM1"),
}
KINDS = ("region", "entities", "poi")
REGION_NAME = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
UUID_STRING = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
UUID_HEX = re.compile(r"^[0-9a-fA-F]{32}$")

ATTACHED_IDS = {
    "minecraft:painting",
    "minecraft:item_frame",
    "minecraft:glow_item_frame",
    "minecraft:leash_knot",
    "immersive_paintings:painting",
    "immersive_paintings:glow_painting",
    "immersive_paintings:graffiti",
    "immersive_paintings:glow_graffiti",
}

# Include the Create ecosystem without pretending that every mod id is a
# literal Create block.  The report keeps the exact id so the allow-list can
# be reviewed later.
CREATE_PREFIXES = (
    "create:",
    "create_",
    "createaddition:",
    "create_connected:",
    "create_dragons_plus:",
    "create_enchantment_industry:",
    "railways:",
)

BLOCK_STATE_KEYS = {
    "block_states",
    "blockstates",
    "palette",
    "data",
    "biomes",
    "block_light",
    "skylight",
    "sky_light",
}

RUNTIME_FILE_PREFIXES = (
    "data/",
    "DIM-1/data/",
    "DIM1/data/",
    "playerdata/",
    "advancements/",
    "stats/",
)
RUNTIME_FILE_NAMES = {
    "level.dat",
    "level.dat_old",
    "session.lock",
    "uid.dat",
    "xiyus_player_data.json",
    "xiyus_password_reset_requests.json",
}


def plain(value: Any) -> Any:
    """Convert nbtlib values to JSON-safe primitives."""
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


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def digest_value(value: Any) -> str:
    return digest_bytes(canonical_json(value).encode("utf-8"))


def decompress(payload: bytes, compression: int) -> bytes:
    compression &= 0x7F
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"unsupported compression type {compression}")


def region_coords(name: str) -> tuple[int, int] | None:
    match = REGION_NAME.fullmatch(name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def slot_chunk(coords: tuple[int, int] | None, slot: int) -> tuple[int, int] | None:
    if coords is None or not 0 <= slot < 1024:
        return None
    return coords[0] * 32 + (slot & 31), coords[1] * 32 + (slot >> 5)


def find_value(root: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in root:
            return root[name]
    level = root.get("Level")
    if isinstance(level, dict):
        for name in names:
            if name in level:
                return level[name]
    return []


def integer(value: Any) -> int | None:
    return value if type(value) is int else None


def uuid_text(value: dict[str, Any]) -> tuple[str | None, bool]:
    raw = value.get("UUID")
    if isinstance(raw, str):
        if UUID_STRING.fullmatch(raw):
            return raw.lower(), True
        if UUID_HEX.fullmatch(raw):
            return raw.lower(), True
        return raw.lower(), False
    if isinstance(raw, list) and len(raw) == 4 and all(type(part) is int for part in raw):
        number = 0
        for part in raw:
            number = (number << 32) | (part & 0xFFFFFFFF)
        return f"{number:032x}", True
    if "UUIDMost" in value and "UUIDLeast" in value:
        try:
            most = int(value["UUIDMost"]) & 0xFFFFFFFFFFFFFFFF
            least = int(value["UUIDLeast"]) & 0xFFFFFFFFFFFFFFFF
            return f"{most:016x}{least:016x}", True
        except Exception:
            return None, False
    return None, False


def is_create_id(identifier: str) -> bool:
    return identifier.startswith(CREATE_PREFIXES)


def collect_items(value: Any, result: list[dict[str, Any]], path: str = "") -> None:
    if isinstance(value, dict):
        identifier = value.get("id")
        count = value.get("count", value.get("Count"))
        if isinstance(identifier, str) and type(count) is int and count > 0:
            components = {key: child for key, child in value.items() if key not in {"id", "count", "Count"}}
            result.append(
                {
                    "id": identifier,
                    "count": count,
                    "components_sha256": digest_value(components),
                    "path": path,
                }
            )
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            collect_items(child, result, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            collect_items(child, result, f"{path}[{index}]")


def item_summary(value: Any) -> dict[str, Any]:
    stacks: list[dict[str, Any]] = []
    collect_items(value, stacks)
    counts = collections.Counter()
    for item in stacks:
        counts[(item["id"], item["components_sha256"])] += item["count"]
    units = sum(item["count"] for item in stacks)
    multiset = [
        {"id": key[0], "components_sha256": key[1], "units": count}
        for key, count in sorted(counts.items())
    ]
    return {
        "stack_count": len(stacks),
        "item_units": units,
        "item_multiset_sha256": digest_value(multiset),
        "items": stacks[:64],
    }


def record_key(base: str, seen: collections.Counter) -> str:
    occurrence = seen[base]
    seen[base] += 1
    return base if occurrence == 0 else f"{base}|dup{occurrence}"


def entity_record(
    value: dict[str, Any],
    dimension: str,
    relative: str,
    slot: int,
    index: int,
    seen: collections.Counter,
) -> tuple[dict[str, Any], list[str]]:
    identifier = str(value.get("id", "<missing>"))
    uid, uuid_valid = uuid_text(value)
    pos = plain(value.get("Pos", []))
    if uid:
        base = f"uuid:{uid}"
    else:
        base = f"loc:{dimension}|{relative}|{slot}|{index}|{identifier}|{canonical_json(pos)}"
    key = record_key(base, seen)
    errors: list[str] = []
    if uid is not None and not uuid_valid:
        errors.append("malformed_uuid")
    if not isinstance(value.get("id"), str):
        errors.append("missing_or_nonstring_id")
    attached_ok = None
    anchor: dict[str, Any] | None = None
    if identifier in ATTACHED_IDS:
        tile_present = all(axis in value for axis in ("TileX", "TileY", "TileZ"))
        tile = [value.get(axis) for axis in ("TileX", "TileY", "TileZ")]
        block_pos = value.get("block_pos", value.get("BlockPos"))
        attached_ok = tile_present or (isinstance(block_pos, list) and len(block_pos) == 3)
        anchor = {"tile": tile, "block_pos": plain(block_pos)}
        if not attached_ok:
            errors.append("missing_attachment_anchor")
    summary = {
        "key": key,
        "id": identifier,
        "uuid": uid,
        "uuid_valid": uuid_valid if uid is not None else None,
        "pos": pos,
        "dimension": dimension,
        "region": relative,
        "slot": slot,
        "index": index,
        "sha256": digest_value(value),
        "attached": identifier in ATTACHED_IDS,
        "attached_ok": attached_ok,
        "anchor": anchor,
    }
    return summary, errors


def block_entity_record(
    value: dict[str, Any],
    dimension: str,
    relative: str,
    slot: int,
    index: int,
    seen: collections.Counter,
) -> tuple[dict[str, Any], list[str]]:
    identifier = str(value.get("id", "<missing>"))
    pos = [value.get(axis) for axis in ("x", "y", "z")]
    if all(type(axis) is int for axis in pos):
        base = f"pos:{dimension}|{pos[0]},{pos[1]},{pos[2]}|{identifier}"
    else:
        base = f"loc:{dimension}|{relative}|{slot}|{index}|{identifier}"
    key = record_key(base, seen)
    errors: list[str] = []
    if not isinstance(value.get("id"), str):
        errors.append("missing_or_nonstring_id")
    items = item_summary(value)
    summary = {
        "key": key,
        "id": identifier,
        "pos": pos,
        "dimension": dimension,
        "region": relative,
        "slot": slot,
        "index": index,
        "sha256": digest_value(value),
        "item_units": items["item_units"],
        "item_multiset_sha256": items["item_multiset_sha256"],
        "item_stack_count": items["stack_count"],
        "items": items["items"] if is_create_id(identifier) else [],
        "create_container": is_create_id(identifier),
    }
    return summary, errors


def selected_block_hash(root: dict[str, Any]) -> str:
    sections = find_value(root, ("sections", "Sections"))
    selected: list[Any] = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                selected.append(section)
                continue
            selected.append(
                {
                    str(key): child
                    for key, child in section.items()
                    if str(key).lower() in BLOCK_STATE_KEYS
                }
            )
    return digest_value(selected)


def chunk_position(root: dict[str, Any]) -> tuple[int | None, int | None]:
    level = root.get("Level") if isinstance(root.get("Level"), dict) else root
    return integer(level.get("xPos")), integer(level.get("zPos"))


def parse_poi(root: dict[str, Any], dimension: str, relative: str, slot: int, coords: tuple[int, int] | None):
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    data_version = root.get("DataVersion")
    if type(data_version) is not int:
        errors.append({"slot": slot, "reason": "missing_or_noninteger_DataVersion"})
    sections = root.get("Sections")
    if not isinstance(sections, dict):
        errors.append({"slot": slot, "reason": "missing_or_noncompound_Sections"})
        return records, errors, data_version
    seen = collections.Counter()
    expected_chunk = slot_chunk(coords, slot)
    for section_name, section in sections.items():
        try:
            section_y = int(section_name)
        except (TypeError, ValueError):
            errors.append({"slot": slot, "reason": "noninteger_section_key", "section": str(section_name)})
            continue
        if not isinstance(section, dict):
            errors.append({"slot": slot, "section": section_y, "reason": "section_not_compound"})
            continue
        valid = section.get("Valid")
        if type(valid) is not int or valid not in (0, 1):
            errors.append({"slot": slot, "section": section_y, "reason": "invalid_Valid"})
        raw_records = section.get("Records")
        if not isinstance(raw_records, list):
            errors.append({"slot": slot, "section": section_y, "reason": "Records_not_list"})
            continue
        for index, raw in enumerate(raw_records):
            if not isinstance(raw, dict):
                errors.append({"slot": slot, "section": section_y, "record": index, "reason": "record_not_compound"})
                continue
            identifier = raw.get("type")
            pos = raw.get("pos")
            free = raw.get("free_tickets")
            if not isinstance(identifier, str) or ":" not in identifier:
                errors.append({"slot": slot, "section": section_y, "record": index, "reason": "invalid_type"})
            if not (isinstance(pos, list) and len(pos) == 3 and all(type(v) is int for v in pos)):
                errors.append({"slot": slot, "section": section_y, "record": index, "reason": "invalid_pos"})
            elif expected_chunk is not None and (pos[0] // 16, pos[2] // 16) != expected_chunk:
                errors.append({"slot": slot, "section": section_y, "record": index, "reason": "pos_chunk_mismatch", "pos": pos, "expected_chunk": expected_chunk})
            elif pos[1] // 16 != section_y:
                errors.append({"slot": slot, "section": section_y, "record": index, "reason": "pos_section_mismatch", "pos": pos})
            if type(free) is not int or free < 0:
                errors.append({"slot": slot, "section": section_y, "record": index, "reason": "invalid_free_tickets"})
            base = f"pos:{dimension}|{canonical_json(pos)}|{identifier}"
            key = record_key(base, seen)
            records.append(
                {
                    "key": key,
                    "type": str(identifier),
                    "pos": plain(pos),
                    "free_tickets": free,
                    "dimension": dimension,
                    "region": relative,
                    "slot": slot,
                    "section": section_y,
                    "index": index,
                    "sha256": digest_value(raw),
                }
            )
    return records, errors, data_version


def read_mca(path: Path, kind: str, dimension: str, relative: str) -> dict[str, Any]:
    data = path.read_bytes()
    result: dict[str, Any] = {
        "relative": relative,
        "dimension": dimension,
        "kind": kind,
        "bytes": len(data),
        "sha256": digest_bytes(data),
        "header_errors": [],
        "parse_errors": [],
        "slots": {},
    }
    # Empty MCA placeholders are emitted by Minecraft for regions with no
    # records. They have no Anvil header by design and are valid, equivalent
    # to an all-zero location table.
    if not data:
        result["empty_file"] = True
        result["occupied_slots"] = []
        result["occupied_slot_count"] = 0
        result["parse_ok"] = True
        return result
    result["empty_file"] = False
    if len(data) < 8192:
        result["header_errors"].append({"reason": "file_shorter_than_anvil_header", "bytes": len(data)})
        return result
    region_sector_count = (len(data) + 4095) // 4096
    coords = region_coords(path.name)
    occupied_ranges: dict[int, tuple[int, int]] = {}
    locations = data[:4096]
    for slot in range(1024):
        entry = locations[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if offset == 0:
            if sectors:
                result["header_errors"].append({"slot": slot, "reason": "zero_offset_nonzero_sector_count"})
            continue
        if offset < 2:
            result["header_errors"].append({"slot": slot, "reason": "chunk_points_into_header", "offset": offset})
            continue
        if sectors < 1 or offset + sectors > region_sector_count:
            result["header_errors"].append({"slot": slot, "reason": "chunk_extent_out_of_file", "offset": offset, "sectors": sectors, "file_sectors": region_sector_count})
            continue
        end = offset + sectors
        for other, (other_offset, other_end) in occupied_ranges.items():
            if offset < other_end and other_offset < end:
                result["header_errors"].append({"slot": slot, "reason": "chunk_sector_overlap", "other_slot": other, "offset": offset, "sectors": sectors})
        occupied_ranges[slot] = (offset, end)
        start = offset * 4096
        if start + 5 > len(data):
            result["parse_errors"].append({"slot": slot, "reason": "missing_chunk_header"})
            continue
        length = int.from_bytes(data[start : start + 4], "big")
        compression = data[start + 4]
        if length < 1 or length > sectors * 4096 - 4:
            result["parse_errors"].append({"slot": slot, "reason": "invalid_chunk_length", "length": length, "sectors": sectors})
            continue
        payload = data[start + 5 : start + 4 + length]
        if compression & 0x80:
            # External .mcc payloads are not expected in this migration. Keep
            # the slot visible as an explicit bounded parse blocker.
            result["parse_errors"].append({"slot": slot, "reason": "external_chunk_payload", "compression": compression})
            continue
        try:
            raw = decompress(payload, compression)
            root = plain(nbtlib.File.parse(io.BytesIO(raw), byteorder="big"))
        except Exception as exc:
            result["parse_errors"].append({"slot": slot, "reason": "nbt_decode_error", "error": f"{type(exc).__name__}: {exc}"})
            continue
        slot_result: dict[str, Any] = {
            "slot": slot,
            "offset": offset,
            "sectors": sectors,
            "compression": compression & 0x7F,
            "sha256": digest_value(root),
            "data_version": root.get("DataVersion"),
            "chunk_pos": list(chunk_position(root)),
            "expected_chunk": list(slot_chunk(coords, slot)) if slot_chunk(coords, slot) is not None else None,
            "block_content_sha256": selected_block_hash(root) if kind == "region" else None,
            "block_entities": [],
            "entities": [],
            "poi_records": [],
            "validation_errors": [],
        }
        expected = slot_chunk(coords, slot)
        actual = chunk_position(root)
        if kind in {"region", "entities"} and expected is not None and actual != (None, None) and actual != expected:
            slot_result["validation_errors"].append({"reason": "chunk_position_mismatch", "actual": list(actual), "expected": list(expected)})
        if kind == "region":
            values = find_value(root, ("block_entities", "BlockEntities", "blockEntities"))
            if not isinstance(values, list):
                slot_result["validation_errors"].append({"reason": "block_entities_not_list"})
                values = []
            seen = collections.Counter()
            for index, raw_value in enumerate(values):
                if not isinstance(raw_value, dict):
                    slot_result["validation_errors"].append({"reason": "block_entity_not_compound", "index": index})
                    continue
                record, errors = block_entity_record(raw_value, dimension, relative, slot, index, seen)
                slot_result["block_entities"].append(record)
                slot_result["validation_errors"].extend({"index": index, "reason": reason} for reason in errors)
        elif kind == "entities":
            values = find_value(root, ("Entities", "entities"))
            if not isinstance(values, list):
                slot_result["validation_errors"].append({"reason": "entities_not_list"})
                values = []
            seen = collections.Counter()
            for index, raw_value in enumerate(values):
                if not isinstance(raw_value, dict):
                    slot_result["validation_errors"].append({"reason": "entity_not_compound", "index": index})
                    continue
                record, errors = entity_record(raw_value, dimension, relative, slot, index, seen)
                slot_result["entities"].append(record)
                slot_result["validation_errors"].extend({"index": index, "reason": reason} for reason in errors)
        else:
            records, errors, data_version = parse_poi(root, dimension, relative, slot, coords)
            slot_result["poi_records"] = records
            slot_result["data_version"] = data_version
            slot_result["validation_errors"].extend(errors)
        result["slots"][str(slot)] = slot_result
    result["occupied_slots"] = sorted(int(slot) for slot in result["slots"])
    result["occupied_slot_count"] = len(result["slots"])
    result["parse_ok"] = not result["header_errors"] and not result["parse_errors"] and all(not value["validation_errors"] for value in result["slots"].values())
    return result


def path_is_mca(relative: str) -> bool:
    parts = relative.split("/")
    return len(parts) >= 2 and parts[-1].endswith(".mca") and parts[-2] in KINDS and (
        len(parts) == 2 or parts[-3] in {"DIM-1", "DIM1"}
    )


def mca_info(relative: str) -> tuple[str, str] | None:
    parts = relative.split("/")
    if len(parts) == 2:
        return "minecraft:overworld", parts[-2]
    if len(parts) == 3 and parts[0] in {"DIM-1", "DIM1"}:
        return ("minecraft:the_nether" if parts[0] == "DIM-1" else "minecraft:the_end"), parts[-2]
    return None


def inventory(root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        records[relative] = {"bytes": path.stat().st_size, "sha256": digest_file(path)}
    return records


def manifest_digest(records: dict[str, dict[str, Any]]) -> str:
    lines = [f"{name}\0{record['bytes']}\0{record['sha256']}\n" for name, record in sorted(records.items())]
    return digest_bytes("".join(lines).encode("utf-8"))


def collect_records(summaries: dict[str, dict[str, Any]], field: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for summary in summaries.values():
        for slot in summary.get("slots", {}).values():
            values.extend(slot.get(field, []))
    return values


def index_records(values: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    result: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for value in sorted(values, key=lambda item: (str(item.get("key")), str(item.get("region")), int(item.get("slot", -1)), int(item.get("index", -1)) )):
        key = str(value.get("key"))
        if key in result:
            duplicates.append(key)
            suffix = 1
            while f"{key}|dup{suffix}" in result:
                suffix += 1
            key = f"{key}|dup{suffix}"
        result[key] = value
    return result, duplicates


def compare_records(source: list[dict[str, Any]], target: list[dict[str, Any]], *, compare_fields: tuple[str, ...] = ("sha256",)) -> dict[str, Any]:
    left, left_dups = index_records(source)
    right, right_dups = index_records(target)
    missing_keys = sorted(set(left) - set(right))
    extra_keys = sorted(set(right) - set(left))
    common = sorted(set(left) & set(right))
    changed = [
        {"source": left[key], "target": right[key]}
        for key in common
        if any(left[key].get(field) != right[key].get(field) for field in compare_fields)
    ]
    def distribution(values: list[dict[str, Any]]) -> dict[str, Any]:
        identifiers = collections.Counter(str(item.get("id", item.get("type", "<missing>"))) for item in values)
        dimensions = collections.Counter(str(item.get("dimension", "<missing>")) for item in values)
        return {"by_dimension": dict(sorted(dimensions.items())), "by_id": dict(identifiers.most_common())}
    return {
        "source_count": len(source),
        "target_count": len(target),
        "missing_count": len(missing_keys),
        "extra_count": len(extra_keys),
        "changed_count": len(changed),
        "source_duplicates": left_dups,
        "target_duplicates": right_dups,
        "missing_sample": [left[key] for key in missing_keys[:200]],
        "extra_sample": [right[key] for key in extra_keys[:200]],
        "changed_sample": changed[:200],
        "source_distribution": distribution(source),
        "target_distribution": distribution(target),
    }


def compare_slots(source: dict[str, dict[str, Any]], target: dict[str, dict[str, Any]]) -> dict[str, Any]:
    left: dict[str, dict[str, Any]] = {}
    right: dict[str, dict[str, Any]] = {}
    for relative, summary in source.items():
        for slot, value in summary.get("slots", {}).items():
            left[f"{relative}|{slot}"] = {"relative": relative, **value}
    for relative, summary in target.items():
        for slot, value in summary.get("slots", {}).items():
            right[f"{relative}|{slot}"] = {"relative": relative, **value}
    missing = sorted(set(left) - set(right))
    extra = sorted(set(right) - set(left))
    changed: list[dict[str, Any]] = []
    categories = collections.Counter()

    def brief(value: dict[str, Any]) -> dict[str, Any]:
        return {
            "relative": value.get("relative"),
            "slot": value.get("slot"),
            "sha256": value.get("sha256"),
            "data_version": value.get("data_version"),
            "chunk_pos": value.get("chunk_pos"),
            "expected_chunk": value.get("expected_chunk"),
            "block_content_sha256": value.get("block_content_sha256"),
            "block_entity_count": len(value.get("block_entities", [])),
            "entity_count": len(value.get("entities", [])),
            "poi_record_count": len(value.get("poi_records", [])),
        }

    for key in sorted(set(left) & set(right)):
        a, b = left[key], right[key]
        if a.get("sha256") == b.get("sha256"):
            continue
        if a.get("block_content_sha256") == b.get("block_content_sha256"):
            category = "runtime_or_encoding_only"
        else:
            category = "block_content_changed"
        categories[category] += 1
        changed.append({"key": key, "category": category, "source": brief(a), "target": brief(b)})
    return {
        "source_count": len(left),
        "target_count": len(right),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "changed_count": len(changed),
        "changed_categories": dict(categories),
        "missing_sample": [left[key] for key in missing[:200]],
        "extra_sample": [right[key] for key in extra[:200]],
        "changed_sample": changed[:200],
    }


def runtime_path(relative: str) -> bool:
    return relative in RUNTIME_FILE_NAMES or relative.startswith(RUNTIME_FILE_PREFIXES)


def side_summary(summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {"files": len(summaries), "bytes": 0, "empty_files": 0, "occupied_slots": 0, "parse_errors": 0, "validation_errors": 0, "dimensions": {}, "kinds": {}}
    for summary in summaries.values():
        output["bytes"] += summary.get("bytes", 0)
        output["empty_files"] += int(summary.get("empty_file", False))
        output["occupied_slots"] += summary.get("occupied_slot_count", 0)
        output["parse_errors"] += len(summary.get("header_errors", [])) + len(summary.get("parse_errors", []))
        output["validation_errors"] += sum(len(slot.get("validation_errors", [])) for slot in summary.get("slots", {}).values())
        dim = summary["dimension"]
        kind = summary["kind"]
        output["dimensions"].setdefault(dim, {"files": 0, "bytes": 0, "occupied_slots": 0})
        output["dimensions"][dim]["files"] += 1
        output["dimensions"][dim]["bytes"] += summary.get("bytes", 0)
        output["dimensions"][dim]["occupied_slots"] += summary.get("occupied_slot_count", 0)
        output["kinds"].setdefault(kind, {"files": 0, "bytes": 0, "occupied_slots": 0})
        output["kinds"][kind]["files"] += 1
        output["kinds"][kind]["bytes"] += summary.get("bytes", 0)
        output["kinds"][kind]["occupied_slots"] += summary.get("occupied_slot_count", 0)
    return output


def audit(source_world: Path, target_world: Path, detail_limit: int = 200, workers: int = 1) -> dict[str, Any]:
    started = time.time()
    source_world = source_world.resolve()
    target_world = target_world.resolve()
    source_inventory = inventory(source_world)
    target_inventory = inventory(target_world)
    all_mca = sorted(rel for rel in set(source_inventory) | set(target_inventory) if path_is_mca(rel))
    source_mca: dict[str, dict[str, Any]] = {}
    target_mca: dict[str, dict[str, Any]] = {}
    jobs: list[tuple[str, str, Path, str, str]] = []
    for relative in all_mca:
        info = mca_info(relative)
        if info is None:
            continue
        dimension, kind = info
        if relative in source_inventory:
            jobs.append(("source", relative, source_world / relative, kind, dimension))
        if relative in target_inventory and (
            relative not in source_inventory
            or source_inventory[relative]["sha256"] != target_inventory[relative]["sha256"]
        ):
            jobs.append(("target", relative, target_world / relative, kind, dimension))

    completed = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
        pending = {
            executor.submit(read_mca, path, kind, dimension, relative): (side, relative)
            for side, relative, path, kind, dimension in jobs
        }
        for future in concurrent.futures.as_completed(pending):
            side, relative = pending[future]
            summary = future.result()
            (source_mca if side == "source" else target_mca)[relative] = summary
            completed += 1
            if completed % 100 == 0 or completed == len(jobs):
                print(json.dumps({"phase": "parse_mca", "completed": completed, "total": len(jobs)}), flush=True)

    for relative in all_mca:
        if relative in target_inventory and relative in source_inventory and source_inventory[relative]["sha256"] == target_inventory[relative]["sha256"]:
            target_mca[relative] = copy.deepcopy(source_mca[relative])
            target_mca[relative]["sha256"] = target_inventory[relative]["sha256"]

    source_slots = {f"{rel}|{slot}": {"relative": rel, **value} for rel, summary in source_mca.items() for slot, value in summary.get("slots", {}).items()}
    target_slots = {f"{rel}|{slot}": {"relative": rel, **value} for rel, summary in target_mca.items() for slot, value in summary.get("slots", {}).items()}
    slot_compare = compare_slots(source_mca, target_mca)

    source_entities = collect_records(source_mca, "entities")
    target_entities = collect_records(target_mca, "entities")
    source_blocks = collect_records(source_mca, "block_entities")
    target_blocks = collect_records(target_mca, "block_entities")
    source_poi = collect_records(source_mca, "poi_records")
    target_poi = collect_records(target_mca, "poi_records")
    entities_compare = compare_records(source_entities, target_entities)
    blocks_compare = compare_records(source_blocks, target_blocks)
    poi_compare = compare_records(source_poi, target_poi, compare_fields=("sha256", "free_tickets"))
    attached_compare = compare_records(
        [item for item in source_entities if item.get("attached")],
        [item for item in target_entities if item.get("attached")],
        compare_fields=("sha256", "attached_ok", "anchor"),
    )
    create_blocks_compare = compare_records(
        [item for item in source_blocks if item.get("create_container")],
        [item for item in target_blocks if item.get("create_container")],
        compare_fields=("item_units", "item_multiset_sha256"),
    )
    create_entities_compare = compare_records(
        [item for item in source_entities if is_create_id(str(item.get("id", "")))],
        [item for item in target_entities if is_create_id(str(item.get("id", "")))],
    )

    source_parse_errors = []
    target_parse_errors = []
    for side, summaries, destination in (("source", source_mca, source_parse_errors), ("target", target_mca, target_parse_errors)):
        for relative, summary in summaries.items():
            for error in summary.get("header_errors", []):
                destination.append({"path": relative, **error})
            for error in summary.get("parse_errors", []):
                destination.append({"path": relative, **error})
            for slot, slot_value in summary.get("slots", {}).items():
                for error in slot_value.get("validation_errors", []):
                    destination.append({"path": relative, "slot": int(slot), **error})

    changed_files = []
    for relative in sorted(set(source_inventory) | set(target_inventory)):
        left = source_inventory.get(relative)
        right = target_inventory.get(relative)
        if left is None or right is None or left["sha256"] != right["sha256"]:
            changed_files.append(
                {
                    "path": relative,
                    "source": left,
                    "target": right,
                    "classification": "runtime_or_save_side_effect" if runtime_path(relative) else "unclassified_changed_file",
                }
            )

    source_only = sorted(set(source_inventory) - set(target_inventory))
    target_only = sorted(set(target_inventory) - set(source_inventory))
    changed_mca = [item for item in changed_files if path_is_mca(item["path"])]
    result: dict[str, Any] = {
        "schema": 1,
        "status": "PASS_BOUNDED" if not source_parse_errors and not target_parse_errors and not slot_compare["missing_count"] and not blocks_compare["missing_count"] and not entities_compare["missing_count"] and not poi_compare["missing_count"] else "BLOCKED_DATA_DIFFERENCE_OR_PARSE_ERROR",
        "scope": {
            "source_world": str(source_world),
            "target_world": str(target_world),
            "dimensions": list(DIMENSIONS),
            "kinds": list(KINDS),
            "note": "The target is a previously started/saved copy. Unchanged MCA files were parsed once and treated as binary-identical on both sides; this report does not infer behavior outside the files and slots listed here.",
        },
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_seconds": round(time.time() - started, 3),
        "file_inventory": {
            "source": {"file_count": len(source_inventory), "total_bytes": sum(v["bytes"] for v in source_inventory.values()), "manifest_sha256": manifest_digest(source_inventory)},
            "target": {"file_count": len(target_inventory), "total_bytes": sum(v["bytes"] for v in target_inventory.values()), "manifest_sha256": manifest_digest(target_inventory)},
            "source_only_count": len(source_only),
            "target_only_count": len(target_only),
            "source_only": source_only[:detail_limit],
            "target_only": [{"path": path, "target": target_inventory[path]} for path in target_only[:detail_limit]],
            "changed_count": len(changed_files),
            "changed_mca_count": len(changed_mca),
            "changed": changed_files[: max(detail_limit, 500)],
        },
        "mca_inventory": {
            "source": side_summary(source_mca),
            "target": side_summary(target_mca),
            "source_file_count": len(source_mca),
            "target_file_count": len(target_mca),
            "source_mca_manifest_sha256": manifest_digest({k: source_inventory[k] for k in source_mca}),
            "target_mca_manifest_sha256": manifest_digest({k: target_inventory[k] for k in target_mca}),
            "binary_equal_files": sum(1 for path in set(source_mca) & set(target_mca) if source_inventory[path]["sha256"] == target_inventory[path]["sha256"]),
            "changed_files": [item["path"] for item in changed_mca],
            "changed_mca_count": len(changed_mca),
        },
        "slot_compare": slot_compare,
        "entities": entities_compare,
        "block_entities": blocks_compare,
        "attached_entities": attached_compare,
        "create_block_containers": create_blocks_compare,
        "create_entities": create_entities_compare,
        "poi_records": poi_compare,
        "parse_and_validation": {
            "source_error_count": len(source_parse_errors),
            "target_error_count": len(target_parse_errors),
            "source_errors": source_parse_errors[: max(detail_limit, 500)],
            "target_errors": target_parse_errors[: max(detail_limit, 500)],
        },
        "uuid_audit": {
            "source_invalid_count": sum(1 for item in source_entities if item.get("uuid") is not None and not item.get("uuid_valid")),
            "target_invalid_count": sum(1 for item in target_entities if item.get("uuid") is not None and not item.get("uuid_valid")),
            "source_missing_uuid_count": sum(1 for item in source_entities if item.get("uuid") is None),
            "target_missing_uuid_count": sum(1 for item in target_entities if item.get("uuid") is None),
            "source_duplicate_uuid_count": len(index_records([item for item in source_entities if item.get("uuid")])[1]),
            "target_duplicate_uuid_count": len(index_records([item for item in target_entities if item.get("uuid")])[1]),
        },
        "interpretation": {
            "missing_source_slots_or_records": "potential_data_loss_and_release_blocker",
            "target_extra_slots_or_records": "target_side_addition_or_runtime_effect; not counted as source loss",
            "changed_slot_with_same_block_content": "runtime_or_encoding_normalization_candidate; inspect record/container comparisons",
            "changed_block_content": "bounded semantic difference; not automatically loss, but requires release review",
            "scope_limit": "This is a filesystem/NBT audit of the two supplied copies. It cannot prove current remote-server changes that occurred after the historical staging snapshot.",
        },
    }
    return result


def markdown(report: dict[str, Any], json_path: Path) -> str:
    inv = report["file_inventory"]
    mca = report["mca_inventory"]
    slots = report["slot_compare"]
    entities = report["entities"]
    blocks = report["block_entities"]
    attached = report["attached_entities"]
    create_blocks = report["create_block_containers"]
    create_entities = report["create_entities"]
    poi = report["poi_records"]
    parse = report["parse_and_validation"]
    uuids = report["uuid_audit"]
    lines = [
        "# Whole-World Transfer Audit (Candidate6)",
        "",
        f"- Status: **{report['status']}** (bounded filesystem/NBT audit)",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Machine report: `{json_path.resolve()}`",
        "- Inputs are read-only; no Java process was started and no source/staging file was modified.",
        "",
        "## Scope",
        "",
        f"- Source: `{report['scope']['source_world']}`",
        f"- Target saved copy: `{report['scope']['target_world']}`",
        "- Dimensions: overworld, the_nether, the_end.",
        "- Trees: every file and every occupied slot under `region`, `entities`, and `poi`.",
        "",
        "## File Hashes",
        "",
        f"- Source files: `{inv['source']['file_count']}`; bytes `{inv['source']['total_bytes']}`; manifest SHA-256 `{inv['source']['manifest_sha256']}`",
        f"- Target files: `{inv['target']['file_count']}`; bytes `{inv['target']['total_bytes']}`; manifest SHA-256 `{inv['target']['manifest_sha256']}`",
        f"- Source MCA manifest: `{mca['source_mca_manifest_sha256']}`",
        f"- Target MCA manifest: `{mca['target_mca_manifest_sha256']}`",
        f"- MCA binary-equal files: `{mca['binary_equal_files']}`; changed MCA files: `{mca['changed_mca_count']}`",
        f"- Source-only files: `{inv['source_only_count']}`; target-only files: `{inv['target_only_count']}`; changed files: `{inv['changed_count']}`",
        "",
        "## Slot And Parse Checks",
        "",
        f"- Occupied slots source/target: `{slots['source_count']}` / `{slots['target_count']}`",
        f"- Missing source slots in target: **`{slots['missing_count']}`**; target-only slots: `{slots['extra_count']}`",
        f"- Rewritten slots: `{slots['changed_count']}`; categories: `{json.dumps(slots.get('changed_categories', {}), ensure_ascii=False)}`",
        f"- Parse/validation errors source/target: `{parse['source_error_count']}` / `{parse['target_error_count']}`",
        "- A rewritten Anvil payload is classified as runtime/encoding-only when its selected block-state content hash is unchanged.",
        "",
        "## Records",
        "",
        f"- Block entities: source/target `{blocks['source_count']}` / `{blocks['target_count']}`; missing `{blocks['missing_count']}`; extra `{blocks['extra_count']}`; changed `{blocks['changed_count']}`",
        f"- All entities: source/target `{entities['source_count']}` / `{entities['target_count']}`; missing `{entities['missing_count']}`; extra `{entities['extra_count']}`; changed `{entities['changed_count']}`",
        f"- Attached entities: source/target `{attached['source_count']}` / `{attached['target_count']}`; missing `{attached['missing_count']}`; anchor/semantic changes `{attached['changed_count']}`",
        f"- POI records: source/target `{poi['source_count']}` / `{poi['target_count']}`; missing `{poi['missing_count']}`; extra `{poi['extra_count']}`; changed `{poi['changed_count']}`",
        "",
        "## Create Containers",
        "",
        f"- Create-family block containers: source/target `{create_blocks['source_count']}` / `{create_blocks['target_count']}`; missing `{create_blocks['missing_count']}`; item-semantic changes `{create_blocks['changed_count']}`",
        f"- Create-family entities: source/target `{create_entities['source_count']}` / `{create_entities['target_count']}`; missing `{create_entities['missing_count']}`; changed `{create_entities['changed_count']}`",
        f"- UUID audit: invalid source/target `{uuids['source_invalid_count']}` / `{uuids['target_invalid_count']}`; missing UUID source/target `{uuids['source_missing_uuid_count']}` / `{uuids['target_missing_uuid_count']}`; duplicate UUID source/target `{uuids['source_duplicate_uuid_count']}` / `{uuids['target_duplicate_uuid_count']}`",
        "- Item-semantic comparison uses item id, component hash, and total units; a storage format rewrite with equal item semantics is not reported as loss.",
        "",
        "## Interpretation",
        "",
        "- Missing source slots or records are potential data-loss blockers.",
        "- Target-only records/files are additions or save/runtime effects and are not counted as source loss.",
        "- This report covers only the two supplied copies. It does not prove changes made on the live remote server after the historical snapshot.",
        "- Full production release still requires a fresh stopped remote snapshot and the separate authentication/integration gates.",
        "",
        "Detailed samples, changed paths, slot keys, record ids, and all hashes are in the machine report.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-world", type=Path, required=True)
    parser.add_argument("--target-world", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--detail-limit", type=int, default=200)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    report = audit(args.source_world, args.target_world, max(1, args.detail_limit), max(1, args.workers))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(report, args.json), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "source_manifest": report["file_inventory"]["source"]["manifest_sha256"],
        "target_manifest": report["file_inventory"]["target"]["manifest_sha256"],
        "changed_files": report["file_inventory"]["changed_count"],
        "changed_mca": report["file_inventory"]["changed_mca_count"],
        "missing_slots": report["slot_compare"]["missing_count"],
        "missing_block_entities": report["block_entities"]["missing_count"],
        "missing_entities": report["entities"]["missing_count"],
        "missing_poi": report["poi_records"]["missing_count"],
        "parse_errors": report["parse_and_validation"]["source_error_count"] + report["parse_and_validation"]["target_error_count"],
        "json": str(args.json.resolve()),
        "markdown": str(args.markdown.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
