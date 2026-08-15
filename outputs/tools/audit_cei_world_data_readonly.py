#!/usr/bin/env python3
"""Read-only Create: Enchantment Industry world-data audit.

The scanner deliberately opens every source file read-only.  It first searches
decompressed region payloads for the CEI namespace and only parses matching
chunks, which keeps a full-world audit practical without sacrificing coverage.
"""

from __future__ import annotations

import argparse
import collections
import copy
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import re
import struct
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

import nbtlib


NAMESPACE = "create_enchantment_industry"
PREFIX = f"{NAMESPACE}:"
PREFIX_BYTES = PREFIX.encode("utf-8")
TOKEN_RE = re.compile(r"create_enchantment_industry:[a-z0-9_./-]+")
NBT_SUFFIXES = {".dat", ".dat_old", ".nbt"}
JSON_SUFFIXES = {".json", ".mcmeta"}
KNOWN_NON_NBT = {"uid.dat"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


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


def tag_type(value: Any) -> str:
    return type(value).__name__.removeprefix("TAG_").split("[", 1)[0]


def path_text(parts: Iterable[str | int]) -> str:
    result = ""
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif result:
            result += f".{part}"
        else:
            result = str(part)
    return result


def normalized_path(parts: Iterable[str | int]) -> str:
    return path_text("[]" if isinstance(part, int) else part for part in parts)


def bounded(value: Any, limit: int = 250_000) -> Any:
    unpacked = plain(value)
    encoded = json.dumps(
        unpacked, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if len(encoded) <= limit:
        return unpacked
    return {
        "_truncated": True,
        "json_chars": len(encoded),
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper(),
        "preview": encoded[: min(limit, 12_000)],
    }


def scalar(value: Any) -> Any:
    value = plain(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return bounded(value, 20_000)


def token_list(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return TOKEN_RE.findall(value.lower())


def value_tokens(value: Any, depth: int = 0) -> set[str]:
    if depth > 16:
        return set()
    if isinstance(value, dict):
        result: set[str] = set()
        for key, child in value.items():
            result.update(token_list(str(key)))
            result.update(value_tokens(child, depth + 1))
        return result
    if isinstance(value, (list, tuple)):
        result: set[str] = set()
        for child in value:
            result.update(value_tokens(child, depth + 1))
        return result
    return set(token_list(plain(value)))


def coordinate_from(value: Any) -> list[float | int] | None:
    if not isinstance(value, dict):
        return None
    coords = [plain(value.get(key)) for key in ("x", "y", "z")]
    if all(isinstance(item, (int, float)) for item in coords):
        return coords
    pos = plain(value.get("Pos"))
    if isinstance(pos, list) and len(pos) >= 3 and all(
        isinstance(item, (int, float)) for item in pos[:3]
    ):
        return pos[:3]
    block_pos = plain(value.get("BlockPos"))
    if isinstance(block_pos, list) and len(block_pos) >= 3:
        return block_pos[:3]
    return None


def schema_fields(value: Any) -> dict[str, list[str]]:
    fields: dict[str, set[str]] = collections.defaultdict(set)

    def visit(node: Any, parts: list[str | int], depth: int) -> None:
        if depth > 24:
            fields[normalized_path(parts)].add("DEPTH_LIMIT")
            return
        if parts:
            fields[normalized_path(parts)].add(tag_type(node))
        if isinstance(node, dict):
            for key, child in node.items():
                visit(child, parts + [str(key)], depth + 1)
        elif isinstance(node, (list, tuple)):
            for child in node:
                visit(child, parts + [0], depth + 1)

    visit(value, [], 0)
    return {key: sorted(types) for key, types in sorted(fields.items())}


def dimension_from_relative(relative: str) -> str:
    parts = relative.replace("\\", "/").split("/")
    if parts[0] == "DIM-1":
        return "minecraft:the_nether"
    if parts[0] == "DIM1":
        return "minecraft:the_end"
    return "minecraft:overworld"


def region_expected_chunk(path: Path, slot: int) -> tuple[int | None, int | None]:
    match = re.fullmatch(r"r\.(-?\d+)\.(-?\d+)\.mca", path.name)
    if not match:
        return None, None
    region_x, region_z = map(int, match.groups())
    return region_x * 32 + slot % 32, region_z * 32 + slot // 32


def decompress(payload: bytes, compression: int) -> bytes:
    kind = compression & 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported region compression type {kind}")


def iter_region_bytes(data: bytes):
    if not data:
        return
    if len(data) < 8192:
        raise ValueError("non-empty region is shorter than its header")
    locations = data[:4096]
    for slot in range(1024):
        entry = locations[slot * 4 : (slot + 1) * 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if not offset:
            continue
        start = offset * 4096
        if offset < 2 or sectors < 1 or start + 5 > len(data):
            raise ValueError(f"slot {slot} has an invalid allocation")
        length = struct.unpack(">I", data[start : start + 4])[0]
        if length < 1 or start + 4 + length > min(len(data), start + sectors * 4096):
            raise ValueError(f"slot {slot} has an invalid payload length")
        compression = data[start + 4]
        if compression & 0x80:
            raise ValueError(f"slot {slot} uses an external chunk stream")
        yield slot, compression, data[start + 5 : start + 4 + length]


def chunk_level(chunk: Any) -> Any:
    level = chunk.get("Level") if isinstance(chunk, dict) else None
    return level if isinstance(level, dict) else chunk


def first_list(container: Any, names: Iterable[str]) -> list[Any]:
    if not isinstance(container, dict):
        return []
    for name in names:
        value = container.get(name)
        if isinstance(value, (list, tuple)):
            return list(value)
    return []


def decode_palette_indices(data_value: Any, palette_size: int) -> tuple[list[int], str]:
    if palette_size <= 1:
        return [0] * 4096, "singleton"
    values = plain(data_value)
    if not isinstance(values, list):
        raise ValueError("non-singleton palette has no long array")
    values = [int(value) & ((1 << 64) - 1) for value in values]
    bits = max(4, math.ceil(math.log2(palette_size)))
    values_per_long = 64 // bits
    padded_expected = math.ceil(4096 / values_per_long)
    compact_expected = math.ceil(4096 * bits / 64)
    mask = (1 << bits) - 1
    result: list[int] = []
    if len(values) == padded_expected:
        for index in range(4096):
            packed = values[index // values_per_long]
            result.append((packed >> ((index % values_per_long) * bits)) & mask)
        mode = f"padded-{bits}bit"
    elif len(values) == compact_expected:
        for index in range(4096):
            bit_index = index * bits
            long_index = bit_index // 64
            start = bit_index % 64
            value = values[long_index] >> start
            if start + bits > 64:
                value |= values[long_index + 1] << (64 - start)
            result.append(value & mask)
        mode = f"compact-{bits}bit"
    else:
        raise ValueError(
            f"unexpected block-state long count {len(values)}; "
            f"expected padded={padded_expected} or compact={compact_expected}"
        )
    invalid = [index for index in result if index >= palette_size]
    if invalid:
        raise ValueError(
            f"decoded {len(invalid)} palette indices outside palette size {palette_size}"
        )
    return result, mode


def base_reference(
    relative: str,
    slot: int | None,
    chunk_x: int | None,
    chunk_z: int | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "dimension": dimension_from_relative(relative),
        "file": relative,
    }
    if slot is not None:
        result["slot"] = slot
    if chunk_x is not None and chunk_z is not None:
        result["chunk"] = [chunk_x, chunk_z]
    return result


def append_namespace_occurrence(
    output: dict[str, Any],
    token: str,
    value: str,
    nbt_path: str,
    context: str,
    reference: dict[str, Any],
    source_kind: str,
    key_occurrence: bool = False,
) -> None:
    lower_path = nbt_path.lower()
    flags: list[str] = []
    if "fluid" in lower_path or "tank" in lower_path:
        flags.append("fluid")
    if "recipe" in lower_path:
        flags.append("recipe")
    if "advancement" in lower_path or source_kind == "advancement_json":
        flags.append("advancement")
    if "component" in lower_path:
        flags.append("component")
    record = {
        **reference,
        "source_kind": source_kind,
        "context": context,
        "path": nbt_path,
        "token": token,
        "value": value,
        "key_occurrence": key_occurrence,
        "semantic_flags": flags,
    }
    output["namespace_occurrences"].append(record)


def visit_tree(
    value: Any,
    output: dict[str, Any],
    parts: list[str | int],
    reference: dict[str, Any],
    source_kind: str,
    context: str,
    owner_id: str | None,
    owner_position: list[float | int] | None,
) -> None:
    if isinstance(value, dict):
        identifier_value = plain(value.get("id"))
        identifier = identifier_value if isinstance(identifier_value, str) else None
        count_present = "count" in value or "Count" in value
        components = value.get("components")
        direct_tokens: set[str] = set()
        for child in value.values():
            child_plain = plain(child)
            if isinstance(child_plain, str):
                direct_tokens.update(token_list(child_plain))

        if identifier and count_present:
            component_tokens = value_tokens(components) if isinstance(components, dict) else set()
            if identifier.startswith(PREFIX) or component_tokens:
                output["item_stacks"].append(
                    {
                        **reference,
                        "source_kind": source_kind,
                        "owner_id": owner_id,
                        "owner_position": owner_position,
                        "path": path_text(parts),
                        "item_id": identifier,
                        "count": scalar(value.get("count", value.get("Count"))),
                        "cei_tokens_in_components": sorted(component_tokens),
                        "schema": schema_fields(value),
                        "nbt": bounded(value),
                    }
                )

        name_value = plain(value.get("Name"))
        if isinstance(name_value, str) and name_value.startswith(PREFIX):
            output["embedded_block_states"].append(
                {
                    **reference,
                    "source_kind": source_kind,
                    "owner_id": owner_id,
                    "owner_position": owner_position,
                    "path": path_text(parts),
                    "block_id": name_value,
                    "properties": plain(value.get("Properties", {})),
                }
            )

        lower_path = path_text(parts).lower()
        if direct_tokens and (
            "fluid" in lower_path
            or "tank" in lower_path
            or any("fluid" in str(key).lower() for key in value)
            or any(token.endswith(":experience") or token.endswith(":hyper_experience") for token in direct_tokens)
        ):
            output["fluid_compounds"].append(
                {
                    **reference,
                    "source_kind": source_kind,
                    "owner_id": owner_id,
                    "owner_position": owner_position,
                    "path": path_text(parts),
                    "tokens": sorted(direct_tokens),
                    "schema": schema_fields(value),
                    "nbt": bounded(value, 100_000),
                }
            )

        for key, child in value.items():
            key_string = str(key)
            for token in token_list(key_string):
                append_namespace_occurrence(
                    output,
                    token,
                    key_string,
                    path_text(parts + [key_string]),
                    context,
                    reference,
                    source_kind,
                    True,
                )
            visit_tree(
                child,
                output,
                parts + [key_string],
                reference,
                source_kind,
                context,
                owner_id,
                owner_position,
            )
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            visit_tree(
                child,
                output,
                parts + [index],
                reference,
                source_kind,
                context,
                owner_id,
                owner_position,
            )
    else:
        unpacked = plain(value)
        if isinstance(unpacked, str):
            for token in token_list(unpacked):
                append_namespace_occurrence(
                    output,
                    token,
                    unpacked,
                    path_text(parts),
                    context,
                    reference,
                    source_kind,
                )


def scan_block_states(
    chunk: Any,
    output: dict[str, Any],
    relative: str,
    slot: int,
    chunk_x: int,
    chunk_z: int,
) -> None:
    level = chunk_level(chunk)
    sections = first_list(level, ("sections", "Sections"))
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        section_y = plain(section.get("Y"))
        if not isinstance(section_y, int):
            continue
        block_states = section.get("block_states")
        if not isinstance(block_states, dict):
            continue
        palette = first_list(block_states, ("palette", "Palette"))
        if not palette:
            continue
        cei_indices: dict[int, tuple[str, dict[str, Any]]] = {}
        for palette_index, entry in enumerate(palette):
            if not isinstance(entry, dict):
                continue
            name = plain(entry.get("Name", entry.get("name")))
            if isinstance(name, str) and name.startswith(PREFIX):
                properties = plain(entry.get("Properties", entry.get("properties", {})))
                if not isinstance(properties, dict):
                    properties = {}
                cei_indices[palette_index] = (name, properties)
        if not cei_indices:
            continue
        try:
            indices, packing = decode_palette_indices(
                block_states.get("data", block_states.get("Data")), len(palette)
            )
        except Exception as exc:
            output["decode_errors"].append(
                {
                    "file": relative,
                    "slot": slot,
                    "chunk": [chunk_x, chunk_z],
                    "section_index": section_index,
                    "section_y": section_y,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return
        for block_index, palette_index in enumerate(indices):
            if palette_index not in cei_indices:
                continue
            block_id, properties = cei_indices[palette_index]
            local_x = block_index & 15
            local_z = (block_index >> 4) & 15
            local_y = (block_index >> 8) & 15
            output["block_states"].append(
                {
                    "dimension": dimension_from_relative(relative),
                    "file": relative,
                    "slot": slot,
                    "chunk": [chunk_x, chunk_z],
                    "position": [
                        chunk_x * 16 + local_x,
                        section_y * 16 + local_y,
                        chunk_z * 16 + local_z,
                    ],
                    "block_id": block_id,
                    "properties": properties,
                    "packing": packing,
                }
            )


def entity_tree_records(
    entity: Any,
    output: dict[str, Any],
    reference: dict[str, Any],
    parts: list[str | int],
) -> None:
    if not isinstance(entity, dict):
        return
    identifier = plain(entity.get("id"))
    position = coordinate_from(entity)
    if isinstance(identifier, str) and identifier.startswith(PREFIX):
        output["entities"].append(
            {
                **reference,
                "path": path_text(parts),
                "entity_id": identifier,
                "position": position,
                "uuid": scalar(entity.get("UUID")),
                "schema": schema_fields(entity),
                "nbt": bounded(entity),
            }
        )
    entity_without_passengers = {
        str(key): child for key, child in entity.items() if str(key) != "Passengers"
    }
    visit_tree(
        entity_without_passengers,
        output,
        parts,
        reference,
        "entity",
        "entity_nbt",
        identifier if isinstance(identifier, str) else None,
        position,
    )
    passengers = entity.get("Passengers")
    if isinstance(passengers, (list, tuple)):
        for index, passenger in enumerate(passengers):
            entity_tree_records(passenger, output, reference, parts + ["Passengers", index])


def empty_scan_output() -> dict[str, Any]:
    return {
        "block_states": [],
        "block_entities": [],
        "entities": [],
        "item_stacks": [],
        "embedded_block_states": [],
        "fluid_compounds": [],
        "namespace_occurrences": [],
        "decode_errors": [],
    }


def scan_chunk(
    root: Any,
    relative: str,
    slot: int,
    region_path: Path,
    kind: str,
) -> dict[str, Any]:
    output = empty_scan_output()
    expected_x, expected_z = region_expected_chunk(region_path, slot)
    level = chunk_level(root)
    chunk_x = plain(level.get("xPos")) if isinstance(level, dict) else None
    chunk_z = plain(level.get("zPos")) if isinstance(level, dict) else None
    if not isinstance(chunk_x, int):
        chunk_x = expected_x
    if not isinstance(chunk_z, int):
        chunk_z = expected_z
    reference = base_reference(relative, slot, chunk_x, chunk_z)
    if kind == "region":
        scan_block_states(root, output, relative, slot, chunk_x, chunk_z)
        block_entities = first_list(
            level,
            ("block_entities", "BlockEntities", "blockEntities", "TileEntities"),
        )
        for index, block_entity in enumerate(block_entities):
            if not isinstance(block_entity, dict):
                continue
            identifier = plain(block_entity.get("id"))
            position = coordinate_from(block_entity)
            if isinstance(identifier, str) and identifier.startswith(PREFIX):
                output["block_entities"].append(
                    {
                        **reference,
                        "index": index,
                        "block_entity_id": identifier,
                        "position": position,
                        "schema": schema_fields(block_entity),
                        "nbt": bounded(block_entity),
                    }
                )
            visit_tree(
                block_entity,
                output,
                ["block_entities", index],
                reference,
                "block_entity",
                "block_entity_nbt",
                identifier if isinstance(identifier, str) else None,
                position,
            )
        # Scheduled ticks and structure metadata can also retain namespaced IDs.
        for name in ("block_ticks", "fluid_ticks", "structures"):
            if isinstance(level, dict) and name in level:
                visit_tree(
                    level[name],
                    output,
                    [name],
                    reference,
                    "chunk_metadata",
                    name,
                    None,
                    None,
                )
    elif kind == "entities":
        entities = first_list(level, ("Entities", "entities"))
        for index, entity in enumerate(entities):
            entity_tree_records(entity, output, reference, ["Entities", index])
    return output


def merge_scan_output(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in empty_scan_output():
        target[key].extend(source.get(key, []))


def classify_mca(relative: str) -> str | None:
    parent = Path(relative).parent.name.lower()
    if parent == "region":
        return "region"
    if parent == "entities":
        return "entities"
    return None


def scan_region_file(path_string: str, root_string: str) -> dict[str, Any]:
    path = Path(path_string)
    root = Path(root_string)
    relative = path.relative_to(root).as_posix()
    data = path.read_bytes()
    result = {
        "manifest": {
            "path": relative,
            "bytes": len(data),
            "mtime_ns": path.stat().st_mtime_ns,
            "sha256": hashlib.sha256(data).hexdigest().upper(),
        },
        "scan": empty_scan_output(),
        "occupied_chunks": 0,
        "namespace_chunks": 0,
        "parse_errors": [],
    }
    kind = classify_mca(relative)
    if kind is None or not data:
        return result
    try:
        for slot, compression, payload in iter_region_bytes(data):
            result["occupied_chunks"] += 1
            try:
                raw = decompress(payload, compression)
            except Exception as exc:
                result["parse_errors"].append(
                    {
                        "file": relative,
                        "slot": slot,
                        "stage": "decompress",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            if PREFIX_BYTES not in raw:
                continue
            result["namespace_chunks"] += 1
            try:
                chunk = nbtlib.File.parse(io.BytesIO(raw), byteorder="big")
                merge_scan_output(result["scan"], scan_chunk(chunk, relative, slot, path, kind))
            except Exception as exc:
                result["parse_errors"].append(
                    {
                        "file": relative,
                        "slot": slot,
                        "stage": "parse_or_scan",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    except Exception as exc:
        result["parse_errors"].append(
            {
                "file": relative,
                "slot": None,
                "stage": "region",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    return result


def nbt_payload(data: bytes) -> tuple[bytes, str]:
    try:
        return gzip.decompress(data), "gzip"
    except Exception:
        return data, "plain"


def scan_nbt_file(path: Path, root: Path, data: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    relative = path.relative_to(root).as_posix()
    if path.name.lower() in KNOWN_NON_NBT:
        return empty_scan_output(), []
    payload, encoding = nbt_payload(data)
    if PREFIX_BYTES not in payload.lower():
        return empty_scan_output(), []
    errors: list[dict[str, Any]] = []
    parsed = None
    attempts = [encoding == "gzip", encoding != "gzip"]
    for gzipped in attempts:
        try:
            parsed = nbtlib.load(path, gzipped=gzipped)
            break
        except Exception as exc:
            errors.append(
                {
                    "file": relative,
                    "stage": f"nbt_load_gzipped_{str(gzipped).lower()}",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    if parsed is None:
        return empty_scan_output(), errors
    output = empty_scan_output()
    parts = relative.split("/")
    if "playerdata" in parts:
        source_kind = "playerdata"
        context = "player_nbt"
    elif path.name.lower().startswith("level.dat"):
        source_kind = "level_dat"
        context = "level_dat"
    elif "data" in parts:
        source_kind = "saveddata"
        context = "saveddata"
    else:
        source_kind = "nbt_file"
        context = "nbt_file"
    identifier = "minecraft:player" if source_kind == "playerdata" else None
    position = coordinate_from(parsed)
    reference = {
        "dimension": dimension_from_relative(relative),
        "file": relative,
    }
    visit_tree(
        parsed,
        output,
        [],
        reference,
        source_kind,
        context,
        identifier,
        position,
    )
    return output, []


def json_source_kind(relative: str) -> str:
    lower = relative.lower()
    if "/advancements/" in f"/{lower}" or lower.startswith("advancements/"):
        return "advancement_json"
    if "/stats/" in f"/{lower}" or lower.startswith("stats/"):
        return "stats_json"
    if "/recipe/" in f"/{lower}" or "/recipes/" in f"/{lower}":
        return "datapack_recipe"
    if "/advancement/" in f"/{lower}":
        return "datapack_advancement"
    return "json_file"


def scan_json_file(path: Path, root: Path, data: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output = empty_scan_output()
    relative = path.relative_to(root).as_posix()
    lower_data = data.lower()
    path_tokens = token_list(relative.lower())
    if PREFIX_BYTES not in lower_data and not path_tokens and NAMESPACE not in relative.lower():
        return output, []
    try:
        decoded = data.decode("utf-8-sig")
        value = json.loads(decoded)
    except Exception as exc:
        return output, [
            {
                "file": relative,
                "stage": "json_load",
                "error": f"{type(exc).__name__}: {exc}",
            }
        ]
    reference = {
        "dimension": dimension_from_relative(relative),
        "file": relative,
    }
    kind = json_source_kind(relative)
    for token in path_tokens:
        append_namespace_occurrence(
            output,
            token,
            relative,
            "$path",
            kind,
            reference,
            kind,
        )
    visit_tree(value, output, [], reference, kind, kind, None, None)
    return output, []


def scan_regular_file(path_string: str, root_string: str) -> dict[str, Any]:
    path = Path(path_string)
    root = Path(root_string)
    relative = path.relative_to(root).as_posix()
    data = path.read_bytes()
    result = {
        "manifest": {
            "path": relative,
            "bytes": len(data),
            "mtime_ns": path.stat().st_mtime_ns,
            "sha256": hashlib.sha256(data).hexdigest().upper(),
        },
        "scan": empty_scan_output(),
        "parse_errors": [],
    }
    suffix = path.suffix.lower()
    try:
        if suffix in NBT_SUFFIXES:
            result["scan"], result["parse_errors"] = scan_nbt_file(path, root, data)
        elif suffix in JSON_SUFFIXES:
            result["scan"], result["parse_errors"] = scan_json_file(path, root, data)
    except Exception as exc:
        result["parse_errors"].append(
            {
                "file": relative,
                "stage": "regular_file_scan",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    return result


def hash_file(path_string: str, root_string: str) -> dict[str, Any]:
    path = Path(path_string)
    root = Path(root_string)
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(data),
        "mtime_ns": path.stat().st_mtime_ns,
        "sha256": hashlib.sha256(data).hexdigest().upper(),
    }


def relevant_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def tree_metadata(root: Path) -> dict[str, list[int]]:
    return {
        path.relative_to(root).as_posix(): [path.stat().st_size, path.stat().st_mtime_ns]
        for path in relevant_files(root)
    }


def counter_dict(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(collections.Counter(str(item.get(key)) for item in records).items()))


def state_signature(record: dict[str, Any]) -> str:
    properties = json.dumps(
        record.get("properties", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return f"{record['block_id']}|{properties}"


def aggregate_schemas(records: list[dict[str, Any]], id_key: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        grouped[str(record.get(id_key))].append(record)
    result: dict[str, Any] = {}
    for identifier, items in sorted(grouped.items()):
        field_counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
        field_presence: collections.Counter[str] = collections.Counter()
        for item in items:
            for path, types in item.get("schema", {}).items():
                field_presence[path] += 1
                for type_name in types:
                    field_counts[path][type_name] += 1
        result[identifier] = {
            "instances": len(items),
            "fields": {
                path: {
                    "present_in_instances": field_presence[path],
                    "types": dict(sorted(field_counts[path].items())),
                }
                for path in sorted(field_counts)
            },
        }
    return result


def summarize_scan(scan: dict[str, Any]) -> dict[str, Any]:
    occurrence_tokens = counter_dict(scan["namespace_occurrences"], "token")
    occurrence_kinds = counter_dict(scan["namespace_occurrences"], "source_kind")
    semantic_flags = collections.Counter()
    for item in scan["namespace_occurrences"]:
        semantic_flags.update(item.get("semantic_flags", []))
    return {
        "block_state_blocks": len(scan["block_states"]),
        "block_state_ids": counter_dict(scan["block_states"], "block_id"),
        "block_state_signatures": dict(
            sorted(collections.Counter(state_signature(item) for item in scan["block_states"]).items())
        ),
        "block_entity_instances": len(scan["block_entities"]),
        "block_entity_ids": counter_dict(scan["block_entities"], "block_entity_id"),
        "entity_instances": len(scan["entities"]),
        "entity_ids": counter_dict(scan["entities"], "entity_id"),
        "item_stack_instances": len(scan["item_stacks"]),
        "item_ids": counter_dict(scan["item_stacks"], "item_id"),
        "embedded_block_state_instances": len(scan["embedded_block_states"]),
        "embedded_block_state_ids": counter_dict(scan["embedded_block_states"], "block_id"),
        "fluid_compound_instances": len(scan["fluid_compounds"]),
        "namespace_occurrence_instances": len(scan["namespace_occurrences"]),
        "namespace_tokens": occurrence_tokens,
        "namespace_source_kinds": occurrence_kinds,
        "namespace_semantic_flags": dict(sorted(semantic_flags.items())),
        "decode_errors": len(scan["decode_errors"]),
    }


def manifest_digest(manifest: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(manifest, key=lambda entry: entry["path"]):
        digest.update(item["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(item["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def scan_world(root: Path, workers: int, progress_path: Path, label: str) -> dict[str, Any]:
    start = dt.datetime.now(dt.timezone.utc)
    before = tree_metadata(root)
    files = relevant_files(root)
    scan = empty_scan_output()
    manifests: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    occupied_chunks = 0
    namespace_chunks = 0
    completed = 0

    def progress() -> None:
        payload = {
            "label": label,
            "root": str(root),
            "status": "RUNNING",
            "completed_files": completed,
            "total_files": len(files),
            "occupied_chunks": occupied_chunks,
            "namespace_chunks": namespace_chunks,
            "namespace_occurrences": len(scan["namespace_occurrences"]),
            "updated_at_utc": utc_now(),
        }
        progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if workers <= 1:
        pending = []
        for path in files:
            try:
                result = (
                    scan_region_file(str(path), str(root))
                    if path.suffix.lower() == ".mca"
                    else scan_regular_file(str(path), str(root))
                )
                pending.append((path, result, None))
            except Exception as exc:
                pending.append((path, None, exc))
    else:
        executor = ProcessPoolExecutor(max_workers=workers)
        future_map = {}
        for path in files:
            if path.suffix.lower() == ".mca":
                future = executor.submit(scan_region_file, str(path), str(root))
            else:
                future = executor.submit(scan_regular_file, str(path), str(root))
            future_map[future] = path
        pending = ((future_map[future], future, None) for future in as_completed(future_map))
    try:
        for path, result_or_future, direct_error in pending:
            completed += 1
            try:
                if direct_error is not None:
                    raise direct_error
                result = result_or_future.result() if workers > 1 else result_or_future
                manifests.append(result["manifest"])
                merge_scan_output(scan, result.get("scan", {}))
                parse_errors.extend(result.get("parse_errors", []))
                occupied_chunks += result.get("occupied_chunks", 0)
                namespace_chunks += result.get("namespace_chunks", 0)
            except Exception as exc:
                parse_errors.append(
                    {
                        "file": path.relative_to(root).as_posix(),
                        "stage": "worker",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            if completed == 1 or completed % 100 == 0 or completed == len(files):
                progress()
    finally:
        if workers > 1:
            executor.shutdown(wait=True)

    for key in empty_scan_output():
        scan[key].sort(
            key=lambda item: (
                str(item.get("dimension", "")),
                str(item.get("file", "")),
                int(item.get("slot", -1) if item.get("slot") is not None else -1),
                str(item.get("path", "")),
                str(item.get("position", "")),
            )
        )
    after = tree_metadata(root)
    metadata_changes = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            metadata_changes.append({"path": path, "before": before.get(path), "after": after.get(path)})
    end = dt.datetime.now(dt.timezone.utc)
    return {
        "schema": 1,
        "status": "PASS_READ_ONLY" if not parse_errors and not scan["decode_errors"] and not metadata_changes else "REVIEW_REQUIRED",
        "label": label,
        "root": str(root.resolve()),
        "started_at_utc": start.replace(microsecond=0).isoformat(),
        "completed_at_utc": end.replace(microsecond=0).isoformat(),
        "duration_seconds": round((end - start).total_seconds(), 3),
        "workers": workers,
        "read_only_contract": {
            "world_open_mode": "binary read only",
            "minecraft_or_java_started": False,
            "metadata_snapshot_changed_during_scan": bool(metadata_changes),
            "metadata_changes": metadata_changes,
        },
        "inventory": {
            "files": len(manifests),
            "bytes": sum(item["bytes"] for item in manifests),
            "manifest_sha256": manifest_digest(manifests),
            "occupied_region_or_entity_chunks": occupied_chunks,
            "chunks_with_cei_namespace": namespace_chunks,
        },
        "manifest": sorted(manifests, key=lambda item: item["path"]),
        "parse_errors": parse_errors,
        "summary": summarize_scan(scan),
        "schemas": {
            "block_entities": aggregate_schemas(scan["block_entities"], "block_entity_id"),
            "entities": aggregate_schemas(scan["entities"], "entity_id"),
            "item_stacks": aggregate_schemas(scan["item_stacks"], "item_id"),
        },
        "records": scan,
    }


def hash_world(root: Path, workers: int, progress_path: Path, label: str) -> dict[str, Any]:
    start = dt.datetime.now(dt.timezone.utc)
    before = tree_metadata(root)
    files = relevant_files(root)
    manifests: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    completed = 0
    with ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(hash_file, str(path), str(root)): path for path in files
        }
        for future in as_completed(future_map):
            path = future_map[future]
            completed += 1
            try:
                manifests.append(future.result())
            except Exception as exc:
                errors.append(
                    {
                        "file": path.relative_to(root).as_posix(),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            if completed == 1 or completed % 100 == 0 or completed == len(files):
                progress_path.write_text(
                    json.dumps(
                        {
                            "label": label,
                            "root": str(root),
                            "status": "HASHING",
                            "completed_files": completed,
                            "total_files": len(files),
                            "updated_at_utc": utc_now(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
    after = tree_metadata(root)
    changes = [
        {"path": path, "before": before.get(path), "after": after.get(path)}
        for path in sorted(set(before) | set(after))
        if before.get(path) != after.get(path)
    ]
    end = dt.datetime.now(dt.timezone.utc)
    return {
        "schema": 1,
        "status": "PASS_READ_ONLY" if not errors and not changes else "REVIEW_REQUIRED",
        "label": label,
        "root": str(root.resolve()),
        "started_at_utc": start.replace(microsecond=0).isoformat(),
        "completed_at_utc": end.replace(microsecond=0).isoformat(),
        "duration_seconds": round((end - start).total_seconds(), 3),
        "workers": workers,
        "read_only_contract": {
            "world_open_mode": "binary read only",
            "minecraft_or_java_started": False,
            "metadata_snapshot_changed_during_scan": bool(changes),
            "metadata_changes": changes,
        },
        "inventory": {
            "files": len(manifests),
            "bytes": sum(item["bytes"] for item in manifests),
            "manifest_sha256": manifest_digest(manifests),
        },
        "manifest": sorted(manifests, key=lambda item: item["path"]),
        "errors": errors,
    }


def compare_manifests(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    left_map = {item["path"]: item for item in left}
    right_map = {item["path"]: item for item in right}
    identical: list[str] = []
    changed: list[dict[str, Any]] = []
    for path in sorted(set(left_map) | set(right_map)):
        a = left_map.get(path)
        b = right_map.get(path)
        if a and b and a["bytes"] == b["bytes"] and a["sha256"] == b["sha256"]:
            identical.append(path)
        else:
            changed.append({"path": path, "left": a, "right": b})
    return {
        "left_files": len(left_map),
        "right_files": len(right_map),
        "binary_identical_files": len(identical),
        "changed_files": changed,
        "changed_count": len(changed),
    }


def stable_block_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in report["records"]["block_states"]:
        key = f"{item['dimension']}|{','.join(map(str, item['position']))}"
        result[key] = {"block_id": item["block_id"], "properties": item["properties"]}
    return result


def stable_be_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in report["records"]["block_entities"]:
        key = f"{item['dimension']}|{','.join(map(str, item.get('position') or []))}|{item['block_entity_id']}"
        result[key] = item
    return result


def map_diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(set(left) - set(right))
    extra = sorted(set(right) - set(left))
    changed = [key for key in sorted(set(left) & set(right)) if left[key] != right[key]]
    return {
        "left_count": len(left),
        "right_count": len(right),
        "missing_keys": missing,
        "extra_keys": extra,
        "changed_keys": changed,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "changed_count": len(changed),
    }


def schema_diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for identifier in sorted(set(left) | set(right)):
        left_fields = set(left.get(identifier, {}).get("fields", {}))
        right_fields = set(right.get(identifier, {}).get("fields", {}))
        common = left_fields & right_fields
        type_changes = {}
        for path in sorted(common):
            left_types = sorted(left[identifier]["fields"][path]["types"])
            right_types = sorted(right[identifier]["fields"][path]["types"])
            if left_types != right_types:
                type_changes[path] = {"left": left_types, "right": right_types}
        result[identifier] = {
            "left_instances": left.get(identifier, {}).get("instances", 0),
            "right_instances": right.get(identifier, {}).get("instances", 0),
            "left_only_fields": sorted(left_fields - right_fields),
            "right_only_fields": sorted(right_fields - left_fields),
            "type_changes": type_changes,
        }
    return result


def occurrence_file_tokens(report: dict[str, Any], paths: set[str]) -> dict[str, int]:
    return dict(
        sorted(
            collections.Counter(
                item["token"]
                for item in report["records"]["namespace_occurrences"]
                if item["file"] in paths
            ).items()
        )
    )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    source = report["datasets"]["source"]
    staging = report["datasets"]["staging"]
    attempt = report["datasets"]["attempt2"]
    comparison = report["comparisons"]["source_to_staging"]
    attempt_compare = report["comparisons"]["staging_to_attempt2"]
    lines = [
        "# CEI 存档兼容性只读审计（2026-08-14）",
        "",
        "## 结论",
        "",
        f"- 世界扫描状态：`{report['status']}`。扫描过程未启动 Java/Minecraft，也未写入三套世界。",
        f"- 原始世界 CEI 方块：{source['summary']['block_state_blocks']}；转换 staging：{staging['summary']['block_state_blocks']}；attempt2：{attempt['summary']['block_state_blocks']}。",
        f"- 原始世界 CEI 方块实体：{source['summary']['block_entity_instances']}；转换 staging：{staging['summary']['block_entity_instances']}；attempt2：{attempt['summary']['block_entity_instances']}。",
        f"- staging 与 attempt2 的世界文件二进制差异数：{attempt_compare['manifest']['changed_count']}；其中含 CEI 引用的差异文件数：{attempt_compare['changed_files_with_cei_count']}。",
        f"- 原始到 staging 的 CEI 方块坐标：缺失 {comparison['block_states']['missing_count']}、新增 {comparison['block_states']['extra_count']}、状态变化 {comparison['block_states']['changed_count']}。",
        "",
        "最终的 2.4.2 可读性结论需要与同批生成的 JAR 注册表/持久化代码差异报告合并；本报告只对世界实际数据给出确定事实。",
        "",
        "## 三套数据",
        "",
        "| 数据集 | 根目录 | 文件 | 扫描区块 | 含 CEI 的区块 | CEI 命名空间引用 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in (source, staging, attempt):
        lines.append(
            f"| {item['label']} | `{item['root']}` | {item['inventory']['files']} | "
            f"{item['inventory'].get('occupied_region_or_entity_chunks', '复用 staging')} | "
            f"{item['inventory'].get('chunks_with_cei_namespace', '复用 staging')} | "
            f"{item['summary']['namespace_occurrence_instances']} |"
        )
    lines.extend(["", "## 世界中实际出现的 ID", ""])
    for label, item in (("原始", source), ("staging", staging), ("attempt2", attempt)):
        lines.append(f"### {label}")
        lines.append("")
        for category in (
            "block_state_ids",
            "block_entity_ids",
            "entity_ids",
            "item_ids",
            "embedded_block_state_ids",
            "namespace_tokens",
        ):
            lines.append(f"- `{category}`: `{json.dumps(item['summary'][category], ensure_ascii=False, sort_keys=True)}`")
        lines.append("")
    lines.extend(
        [
            "## 原始 → staging",
            "",
            f"- 方块坐标对比：`{json.dumps(comparison['block_states'], ensure_ascii=False)}`",
            f"- 方块实体坐标/ID 对比：`{json.dumps(comparison['block_entities'], ensure_ascii=False)}`",
            "- 方块实体字段差异详见 JSON 的 `comparisons.source_to_staging.block_entity_schema`。",
            "- 物品栈字段差异详见 JSON 的 `comparisons.source_to_staging.item_stack_schema`。",
            "- 流体复合标签的完整数值、字段和宿主坐标详见各数据集的 `records.fluid_compounds`。",
            "",
            "## staging → attempt2",
            "",
            f"- 完整文件 SHA-256 对比：`{json.dumps(attempt_compare['manifest'], ensure_ascii=False)}`",
            f"- 有差异且包含 CEI 引用的文件：`{json.dumps(attempt_compare['changed_files_with_cei'], ensure_ascii=False)}`",
            "- attempt2 的 CEI 语义记录来自 staging 的逐文件二进制等价复用；仅当差异文件均确认不含 CEI 时才允许复用。",
            "",
            "## 证据入口",
            "",
            f"- 主 JSON：`{report['report_paths']['json']}`",
            f"- 原始详细 JSON：`{report['report_paths']['source_detail']}`",
            f"- staging 详细 JSON：`{report['report_paths']['staging_detail']}`",
            f"- attempt2 文件清单：`{report['report_paths']['attempt2_manifest']}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_dataset(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in report.items()
        if key not in {"manifest", "records", "schemas"}
    } | {
        "schemas": copy.deepcopy(report["schemas"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--attempt2", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    for root in (args.source, args.staging, args.attempt2):
        if not root.is_dir():
            raise SystemExit(f"world root does not exist: {root}")
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    progress = out / "progress.json"
    source_detail_path = out / "source-original-cei-world-data.json"
    staging_detail_path = out / "handoff-converted-staging-cei-world-data.json"
    attempt_manifest_path = out / "fresh-attempt2-world-manifest.json"
    main_json_path = out / "cei-world-data-compat-audit-20260814.json"
    main_md_path = out / "cei-world-data-compat-audit-20260814.md"

    source = scan_world(args.source.resolve(), args.workers, progress, "source_original_1.21.11")
    write_json(source_detail_path, source)
    staging = scan_world(args.staging.resolve(), args.workers, progress, "handoff_converted_staging_1.21.1")
    write_json(staging_detail_path, staging)
    attempt_manifest = hash_world(args.attempt2.resolve(), args.workers, progress, "fresh_attempt2_1.21.1")
    write_json(attempt_manifest_path, attempt_manifest)

    manifest_compare = compare_manifests(staging["manifest"], attempt_manifest["manifest"])
    changed_paths = {item["path"] for item in manifest_compare["changed_files"]}
    staging_changed_tokens = occurrence_file_tokens(staging, changed_paths)

    # Inspect changed attempt2 files directly.  Region changes require a full CEI
    # scan before reuse; ordinary NBT/JSON files can be scanned individually.
    changed_attempt_scan = empty_scan_output()
    changed_attempt_errors: list[dict[str, Any]] = []
    changed_mca = False
    attempt_root = args.attempt2.resolve()
    for relative in sorted(changed_paths):
        path = attempt_root / Path(relative)
        if not path.is_file():
            continue
        if path.suffix.lower() == ".mca":
            changed_mca = True
            result = scan_region_file(str(path), str(attempt_root))
        else:
            result = scan_regular_file(str(path), str(attempt_root))
        merge_scan_output(changed_attempt_scan, result.get("scan", {}))
        changed_attempt_errors.extend(result.get("parse_errors", []))
    changed_attempt_tokens = counter_dict(changed_attempt_scan["namespace_occurrences"], "token")
    changed_files_with_cei = sorted(
        {
            item["file"]
            for item in changed_attempt_scan["namespace_occurrences"]
        }
        | {
            item["file"]
            for item in staging["records"]["namespace_occurrences"]
            if item["file"] in changed_paths
        }
    )

    can_reuse = (
        not changed_mca
        and not changed_files_with_cei
        and not changed_attempt_errors
        and not attempt_manifest.get("errors")
    )
    if not can_reuse:
        attempt = scan_world(attempt_root, args.workers, progress, "fresh_attempt2_1.21.1")
        attempt["semantic_derivation"] = "FULL_SCAN"
    else:
        attempt = compact_dataset(staging)
        attempt.update(
            {
                "status": attempt_manifest["status"],
                "label": "fresh_attempt2_1.21.1",
                "root": str(attempt_root),
                "started_at_utc": attempt_manifest["started_at_utc"],
                "completed_at_utc": attempt_manifest["completed_at_utc"],
                "duration_seconds": attempt_manifest["duration_seconds"],
                "workers": args.workers,
                "read_only_contract": attempt_manifest["read_only_contract"],
                "inventory": {
                    **attempt_manifest["inventory"],
                    "occupied_region_or_entity_chunks": staging["inventory"]["occupied_region_or_entity_chunks"],
                    "chunks_with_cei_namespace": staging["inventory"]["chunks_with_cei_namespace"],
                },
                "summary": copy.deepcopy(staging["summary"]),
                "schemas": copy.deepcopy(staging["schemas"]),
                "semantic_derivation": "BINARY_EQUIVALENT_CEI_SCOPE_REUSED_FROM_STAGING",
                "semantic_reuse_evidence": {
                    "manifest_compare": manifest_compare,
                    "changed_paths": sorted(changed_paths),
                    "staging_changed_tokens": staging_changed_tokens,
                    "attempt2_changed_tokens": changed_attempt_tokens,
                    "changed_attempt_scan_errors": changed_attempt_errors,
                },
                "record_reference": str(staging_detail_path),
            }
        )

    source_block_map = stable_block_map(source)
    staging_block_map = stable_block_map(staging)
    source_be_map = stable_be_map(source)
    staging_be_map = stable_be_map(staging)
    source_to_staging = {
        "block_states": map_diff(source_block_map, staging_block_map),
        "block_entities": map_diff(
            {key: {"id": value["block_entity_id"]} for key, value in source_be_map.items()},
            {key: {"id": value["block_entity_id"]} for key, value in staging_be_map.items()},
        ),
        "block_entity_schema": schema_diff(source["schemas"]["block_entities"], staging["schemas"]["block_entities"]),
        "entity_schema": schema_diff(source["schemas"]["entities"], staging["schemas"]["entities"]),
        "item_stack_schema": schema_diff(source["schemas"]["item_stacks"], staging["schemas"]["item_stacks"]),
        "namespace_token_counts": {
            "source": source["summary"]["namespace_tokens"],
            "staging": staging["summary"]["namespace_tokens"],
        },
    }
    staging_to_attempt = {
        "manifest": manifest_compare,
        "changed_files_with_cei": changed_files_with_cei,
        "changed_files_with_cei_count": len(changed_files_with_cei),
        "staging_changed_tokens": staging_changed_tokens,
        "attempt2_changed_tokens": changed_attempt_tokens,
        "semantic_reuse_allowed": can_reuse,
    }
    status = "PASS_WORLD_DATA_COMPAT" if (
        source["status"] == "PASS_READ_ONLY"
        and staging["status"] == "PASS_READ_ONLY"
        and attempt["status"] == "PASS_READ_ONLY"
        and not source_to_staging["block_states"]["missing_count"]
        and not source_to_staging["block_states"]["extra_count"]
        and not source_to_staging["block_states"]["changed_count"]
        and not source_to_staging["block_entities"]["missing_count"]
        and not source_to_staging["block_entities"]["extra_count"]
        and not changed_files_with_cei
    ) else "REVIEW_REQUIRED"
    final = {
        "schema": 1,
        "generated_at_utc": utc_now(),
        "status": status,
        "scope": {
            "namespace": NAMESPACE,
            "source_policy": "authoritative original 1.21.11 world, immutable read only",
            "staging_policy": "handoff converted staging, read only",
            "attempt2_policy": "fresh attempt2 world, read only",
            "java_or_minecraft_started": False,
            "world_files_written": False,
        },
        "datasets": {
            "source": compact_dataset(source),
            "staging": compact_dataset(staging),
            "attempt2": attempt,
        },
        "comparisons": {
            "source_to_staging": source_to_staging,
            "staging_to_attempt2": staging_to_attempt,
        },
        "report_paths": {
            "json": str(main_json_path),
            "markdown": str(main_md_path),
            "source_detail": str(source_detail_path),
            "staging_detail": str(staging_detail_path),
            "attempt2_manifest": str(attempt_manifest_path),
        },
        "interpretation": {
            "world_data_only": "This report proves what CEI IDs and schemas actually exist in the three worlds.",
            "jar_compatibility_dependency": "Final 2.4.2 readability must also prove every used registry ID and persistence field is accepted by the NeoForge 2.4.2 JAR.",
            "fail_closed": True,
        },
    }
    write_json(main_json_path, final)
    write_markdown(main_md_path, final)
    progress.write_text(
        json.dumps(
            {
                "status": "COMPLETE",
                "result": status,
                "json": str(main_json_path),
                "markdown": str(main_md_path),
                "completed_at_utc": utc_now(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"status": status, "json": str(main_json_path), "markdown": str(main_md_path)}, ensure_ascii=False))
    return 0 if status == "PASS_WORLD_DATA_COMPAT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
