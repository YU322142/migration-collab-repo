#!/usr/bin/env python3
"""Fail-closed object-level entity OTA for the protected Overworld circle.

The tool preserves every current C entity and all NBT payload fields.  Only
``Pos`` may change, and only for entities that the collision/POI gate marked
BLOCKED or REVIEW.  Aquatic entities are moved to water, ground mobs to a safe
surface, items to a supported non-hazardous location, flying entities to clear
air, and falling blocks to clear air with a one-block fall path.

The exact protected selection is fixed at 29,305 chunk slots in 40 regions.
Entity MCA files are rebuilt slot-by-slot: selected slots contain the complete
preserved/rebucketed C entity set, while every outside slot retains C's raw
compressed record and timestamp.  Missing or ambiguous inputs, unsafe targets,
payload drift, silent deletion, UUID duplication, external .mcc storage, or a
CAS mismatch fail closed.

``plan`` is read-only.  ``build`` writes only a detached bundle.  ``apply`` and
``rollback`` are the only world-mutating commands and require both an explicit
write switch and the literal stopped-server acknowledgement.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import uuid
import zlib
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import nbtlib


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import audit_protected_zone_entity_poi_gate as collision_gate  # noqa: E402
import protected_zone_terrain_ota as terrain_ota  # noqa: E402


SCHEMA_PLAN = "protected-zone-entity-ota-plan/v1"
SCHEMA_BUNDLE = "protected-zone-entity-ota-bundle/v1"
SCHEMA_RECEIPT = "protected-zone-entity-ota-apply-receipt/v1"
SCHEMA_TARGET_VERIFY = "protected-zone-entity-ota-target-verification/v1"
EXPECTED_SOURCE_SHA256 = "ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92"
EXPECTED_GATE_SHA256 = "2AD47BEB843B3BC0C148F3CBA334C2E1484009099985228982DF86CDEC281131"
EXPECTED_STRICT_AUDIT_SHA256 = "854A2EFFFCF2EDEE7C126FBFD897A3B117FDCE9B22EBA49846E092CFDDC18D6B"
EXPECTED_ENTITIES = 198
EXPECTED_CHUNKS = 29_305
EXPECTED_REGIONS = 40
DATA_VERSION = 3955
MIN_Y = -64
NATURAL_TOP_Y = 319
MAX_BUILD_Y = 479
STOPPED_ACK = "SERVER_IS_STOPPED"
DEFAULT_CURRENT = Path(r"<DOWNLOAD_ROOT>\mechanomania-matched-runtime-attempt13-2.zip")
DEFAULT_GATE = SCRIPT_DIR.parent / "protected-zone-entity-collision-poi-gate-20260815.json"
DEFAULT_V_WORLD = Path(
    r"<AUDIT_ROOT>\vanilla-reference-v-20260815"
    r"\strict-reference-world\vanilla-reference-v"
)
INTENDED_TERRAIN_TEST_CLONE = Path(
    r"<AUDIT_ROOT>\protected-terrain-ota-test-server-20260815"
    r"\mechanomania-matched-runtime-attempt13-20260814"
)

AQUATIC_WATERLIKE = {
    "minecraft:water",
    "minecraft:bubble_column",
    "minecraft:seagrass",
    "minecraft:tall_seagrass",
    "minecraft:kelp",
    "minecraft:kelp_plant",
}
LEAF_SUFFIXES = ("_leaves",)
CATEGORY_RADIUS = {
    "aquatic": 128,
    "ground": 64,
    "flying": 64,
    "falling_block": 64,
    "item": 64,
}
CATEGORY_ORDER = {
    "aquatic": 0,
    "ground": 1,
    "flying": 2,
    "falling_block": 3,
    "item": 4,
}


class EntityOtaError(RuntimeError):
    """A fail-closed input, safety, or transaction error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value))


def json_load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise EntityOtaError(f"JSON root is not an object: {path}")
    return value


def plain(value: Any) -> Any:
    if hasattr(value, "unpack"):
        try:
            unpacked = value.unpack()
            if unpacked is not value:
                return plain(unpacked)
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return plain(value.tolist())
        except Exception:
            pass
    if isinstance(value, Mapping):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [plain(child) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def typed_plain(value: Any) -> Any:
    """Canonical, tag-type-aware NBT projection used for payload hashes."""

    tag_type = type(value).__name__
    if isinstance(value, Mapping):
        return {
            "tag": tag_type,
            "value": {str(key): typed_plain(value[key]) for key in sorted(value, key=str)},
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return {"tag": tag_type, "value": [typed_plain(child) for child in value]}
    unpacked = plain(value)
    return {"tag": tag_type, "value": unpacked}


def entity_payload_sha256(entity: Mapping[str, Any]) -> str:
    payload = {str(key): typed_plain(entity[key]) for key in sorted(entity, key=str) if str(key) != "Pos"}
    return sha256_bytes(canonical_json_bytes(payload))


def entity_semantic_sha256(entity: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(typed_plain(entity)))


def parse_uuid(value: Any) -> str | None:
    unpacked = plain(value)
    try:
        if isinstance(unpacked, str):
            return str(uuid.UUID(unpacked))
        if isinstance(unpacked, list) and len(unpacked) == 4:
            number = 0
            for part in unpacked:
                number = (number << 32) | (int(part) & 0xFFFFFFFF)
            return str(uuid.UUID(int=number))
    except (ValueError, TypeError, AttributeError):
        return None
    return None


def uuid_from_entity(entity: Mapping[str, Any]) -> str | None:
    direct = parse_uuid(entity.get("UUID"))
    if direct is not None:
        return direct
    if "UUIDMost" in entity and "UUIDLeast" in entity:
        try:
            high = int(plain(entity["UUIDMost"])) & 0xFFFFFFFFFFFFFFFF
            low = int(plain(entity["UUIDLeast"])) & 0xFFFFFFFFFFFFFFFF
            return str(uuid.UUID(int=(high << 64) | low))
        except (ValueError, TypeError, AttributeError):
            return None
    return None


def entity_position(entity: Mapping[str, Any]) -> tuple[float, float, float]:
    value = entity.get("Pos")
    if not isinstance(value, Sequence) or len(value) < 3:
        raise EntityOtaError("entity has no usable Pos list")
    try:
        return float(plain(value[0])), float(plain(value[1])), float(plain(value[2]))
    except (ValueError, TypeError) as exc:
        raise EntityOtaError("entity Pos contains a non-numeric value") from exc


def set_entity_position(entity: Mapping[str, Any], position: Sequence[float]) -> None:
    value = entity.get("Pos")
    if not isinstance(value, Sequence) or len(value) < 3:
        raise EntityOtaError("cannot update entity without a three-value Pos list")
    value[0] = nbtlib.Double(float(position[0]))
    value[1] = nbtlib.Double(float(position[1]))
    value[2] = nbtlib.Double(float(position[2]))


def nested_passenger_count(entity: Mapping[str, Any]) -> int:
    total = 0
    passengers = entity.get("Passengers")
    if isinstance(passengers, Sequence):
        for passenger in passengers:
            total += 1
            if isinstance(passenger, Mapping):
                total += nested_passenger_count(passenger)
    return total


def decode_record(raw_record: bytes, label: str) -> tuple[Any, int]:
    if len(raw_record) < 5:
        raise EntityOtaError(f"{label}: truncated MCA record")
    length = struct.unpack(">I", raw_record[:4])[0]
    if length != len(raw_record) - 4:
        raise EntityOtaError(f"{label}: record length mismatch")
    compression = raw_record[4]
    if compression & 0x80:
        raise EntityOtaError(f"{label}: external .mcc storage is refused")
    payload = raw_record[5:]
    if compression == 1:
        nbt_bytes = gzip.decompress(payload)
    elif compression == 2:
        nbt_bytes = zlib.decompress(payload)
    elif compression == 3:
        nbt_bytes = payload
    else:
        raise EntityOtaError(f"{label}: unsupported compression type {compression}")
    try:
        return nbtlib.File.parse(io.BytesIO(nbt_bytes), byteorder="big"), compression
    except Exception as exc:
        raise EntityOtaError(f"{label}: NBT decode failed: {type(exc).__name__}: {exc}") from exc


def encode_record(root: Any, compression: int, label: str) -> bytes:
    buffer = io.BytesIO()
    try:
        root.write(buffer, byteorder="big")
    except Exception as exc:
        raise EntityOtaError(f"{label}: NBT encode failed: {type(exc).__name__}: {exc}") from exc
    nbt_bytes = buffer.getvalue()
    if compression == 1:
        payload = gzip.compress(nbt_bytes, compresslevel=6, mtime=0)
    elif compression == 2:
        payload = zlib.compress(nbt_bytes, level=6)
    elif compression == 3:
        payload = nbt_bytes
    else:
        raise EntityOtaError(f"{label}: unsupported compression type {compression}")
    length = 1 + len(payload)
    return struct.pack(">I", length) + bytes([compression]) + payload


def file_identity_bytes(data: bytes | None) -> dict[str, Any]:
    return {
        "exists": data is not None,
        "bytes": len(data) if data is not None else 0,
        "sha256": sha256_bytes(data) if data is not None else None,
    }


def file_identity_path(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "bytes": 0, "sha256": None}
    return {"exists": True, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def identity_equal(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return (
        bool(actual.get("exists")) == bool(expected.get("exists"))
        and int(actual.get("bytes", 0)) == int(expected.get("bytes", 0))
        and actual.get("sha256") == expected.get("sha256")
    )


def entity_relative(region_x: int, region_z: int) -> str:
    return f"entities/r.{region_x}.{region_z}.mca"


def category_for(identifier: str) -> str:
    if identifier in collision_gate.AQUATIC:
        return "aquatic"
    if identifier in collision_gate.GROUND_REQUIRED:
        return "ground"
    if identifier in collision_gate.FLYING:
        return "flying"
    if identifier == "minecraft:falling_block":
        return "falling_block"
    if identifier == "minecraft:item":
        return "item"
    raise EntityOtaError(f"no relocation policy exists for {identifier}")


def chunk_for_position(position: Sequence[float]) -> tuple[int, int]:
    return math.floor(float(position[0])) // 16, math.floor(float(position[2])) // 16


def chunk_for_slot(region_x: int, region_z: int, slot: int) -> tuple[int, int]:
    return region_x * 32 + (slot & 31), region_z * 32 + (slot >> 5)


def block_chunks_for_body(
    position: Sequence[float], width: float, height: float
) -> set[tuple[int, int]]:
    return {
        (x // 16, z // 16)
        for x, _y, z in collision_gate.entity_aabb_blocks(position, width, height)
    }


def entity_box(position: Sequence[float], width: float, height: float) -> tuple[float, float, float, float, float, float]:
    x, y, z = float(position[0]), float(position[1]), float(position[2])
    return (x - width / 2, y, z - width / 2, x + width / 2, y + height, z + width / 2)


def boxes_overlap(
    left: Sequence[float], right: Sequence[float], epsilon: float = 1.0e-7
) -> bool:
    return not (
        float(left[3]) <= float(right[0]) + epsilon
        or float(right[3]) <= float(left[0]) + epsilon
        or float(left[4]) <= float(right[1]) + epsilon
        or float(right[4]) <= float(left[1]) + epsilon
        or float(left[5]) <= float(right[2]) + epsilon
        or float(right[5]) <= float(left[2]) + epsilon
    )


def safe_support(index: collision_gate.VBlockIndex, x: int, y: int, z: int) -> bool:
    state = index.state(x, y, z)
    name = str(state["name"])
    return (
        collision_gate.block_class(name) == "solid_or_unknown_collision"
        and name not in collision_gate.HAZARD_BLOCKS
        and not name.endswith(LEAF_SUFFIXES)
    )


def candidate_body_safe(
    index: collision_gate.VBlockIndex,
    position: Sequence[float],
    width: float,
    height: float,
    category: str,
    selected: set[tuple[int, int]],
) -> tuple[bool, str | None]:
    if float(position[1]) < MIN_Y or float(position[1]) + height > MAX_BUILD_Y + 1:
        return False, "body exceeds dimension build range"
    body = collision_gate.entity_aabb_blocks(position, width, height)
    if not body:
        return False, "empty AABB block projection"
    if any((x // 16, z // 16) not in selected for x, _y, z in body):
        return False, "body crosses an unselected chunk"
    for x, y, z in body:
        state = index.state(x, y, z)
        name = str(state["name"])
        classification = collision_gate.block_class(name)
        if name in collision_gate.HAZARD_BLOCKS:
            return False, f"hazardous block {name} at {x},{y},{z}"
        if category == "aquatic":
            if name not in AQUATIC_WATERLIKE:
                return False, f"aquatic body is not fully water-filled at {x},{y},{z}: {name}"
        elif category == "item":
            if classification not in {"air", "passable"}:
                return False, f"item body is not clear air/passable space at {x},{y},{z}: {name}"
        else:
            if classification not in {"air", "passable"}:
                return False, f"body intersects {classification} {name} at {x},{y},{z}"
    return True, None


def position_is_safe(
    index: collision_gate.VBlockIndex,
    position: Sequence[float],
    identifier: str,
    category: str,
    selected: set[tuple[int, int]],
) -> tuple[bool, str | None]:
    width, height = collision_gate.ENTITY_DIMENSIONS.get(identifier, (1.0, 2.0))
    body_ok, reason = candidate_body_safe(index, position, width, height, category, selected)
    if not body_ok:
        return False, reason
    center_x, center_z = math.floor(float(position[0])), math.floor(float(position[2]))
    feet_y = math.floor(float(position[1]) + 1.0e-7)
    if category == "ground":
        if not safe_support(index, center_x, feet_y - 1, center_z):
            return False, "ground entity lacks a full, non-hazardous support block"
    elif category == "item":
        if not safe_support(index, center_x, feet_y - 1, center_z):
            return False, "item lacks a full, non-hazardous solid support block"
    elif category == "falling_block":
        if not safe_support(index, center_x, feet_y - 2, center_z):
            return False, "falling block lacks a safe landing block two levels below"
        gap = index.state(center_x, feet_y - 1, center_z)
        gap_name = str(gap["name"])
        if (
            collision_gate.block_class(gap_name) not in {"air", "passable"}
            or gap_name in collision_gate.HAZARD_BLOCKS
        ):
            return False, "falling block has no clear one-block fall path"
    return True, None


def horizontal_offsets(radius: int) -> list[tuple[int, int, int]]:
    rows = [
        (dx * dx + dz * dz, dx, dz)
        for dx in range(-radius, radius + 1)
        for dz in range(-radius, radius + 1)
        if dx * dx + dz * dz <= radius * radius
    ]
    return sorted(rows, key=lambda row: (row[0], abs(row[1]) + abs(row[2]), row[1], row[2]))


_OFFSET_CACHE: dict[int, list[tuple[int, int, int]]] = {}


def offsets_for_radius(radius: int) -> list[tuple[int, int, int]]:
    if radius not in _OFFSET_CACHE:
        _OFFSET_CACHE[radius] = horizontal_offsets(radius)
    return _OFFSET_CACHE[radius]


def y_candidates_for_column(
    index: collision_gate.VBlockIndex,
    x: float,
    z: float,
    original_y: float,
    identifier: str,
    category: str,
    selected: set[tuple[int, int]],
) -> list[float]:
    width, height = collision_gate.ENTITY_DIMENSIONS.get(identifier, (1.0, 2.0))
    center_x, center_z = math.floor(x), math.floor(z)
    candidates: list[float] = []
    if category == "ground":
        # Approximate MOTION_BLOCKING_NO_LEAVES: use the highest full,
        # non-hazardous, non-leaf support with complete AABB clearance.
        for support_y in range(NATURAL_TOP_Y, MIN_Y - 1, -1):
            if not safe_support(index, center_x, support_y, center_z):
                continue
            candidate = (x, float(support_y + 1), z)
            if candidate_body_safe(index, candidate, width, height, category, selected)[0]:
                candidates.append(float(support_y + 1))
                break
    elif category == "item":
        for feet_y in range(MIN_Y, NATURAL_TOP_Y + 2):
            candidate = (x, float(feet_y), z)
            if position_is_safe(index, candidate, identifier, category, selected)[0]:
                candidates.append(float(feet_y))
        candidates.sort(key=lambda y: (abs(y - original_y), y))
        candidates = candidates[:8]
    elif category == "falling_block":
        for support_y in range(MIN_Y, NATURAL_TOP_Y + 1):
            feet_y = float(support_y + 2)
            candidate = (x, feet_y, z)
            if position_is_safe(index, candidate, identifier, category, selected)[0]:
                candidates.append(feet_y)
        candidates.sort(key=lambda y: (abs(y - original_y), y))
        candidates = candidates[:8]
    elif category == "aquatic":
        minimum = MIN_Y
        maximum = int(math.floor(NATURAL_TOP_Y + 1 - height))
        for feet_y in range(minimum, maximum + 1):
            candidate = (x, float(feet_y), z)
            if candidate_body_safe(index, candidate, width, height, category, selected)[0]:
                candidates.append(float(feet_y))
        candidates.sort(key=lambda y: (abs(y - original_y), y))
        candidates = candidates[:8]
    elif category == "flying":
        minimum = MIN_Y
        maximum = int(math.floor(MAX_BUILD_Y + 1 - height))
        values = list(range(minimum, maximum + 1))
        values.sort(key=lambda y: (abs(y - original_y), y))
        for feet_y in values:
            candidate = (x, float(feet_y), z)
            if candidate_body_safe(index, candidate, width, height, category, selected)[0]:
                candidates.append(float(feet_y))
                if len(candidates) >= 8:
                    break
    else:  # pragma: no cover - category_for prevents this
        raise EntityOtaError(f"unsupported relocation category {category}")
    return candidates


def relocate_entity(
    index: collision_gate.VBlockIndex,
    identifier: str,
    entity_uuid: str,
    original: Sequence[float],
    category: str,
    selected: set[tuple[int, int]],
    reserved_boxes: list[tuple[str, tuple[float, float, float, float, float, float]]],
) -> dict[str, Any]:
    width, height = collision_gate.ENTITY_DIMENSIONS.get(identifier, (1.0, 2.0))
    radius = CATEGORY_RADIUS[category]
    best: tuple[tuple[Any, ...], tuple[float, float, float], tuple[float, ...]] | None = None
    inspected_offsets = 0
    safe_before_occupancy = 0
    rejected_by_occupancy = 0
    equal_geometric_best = 0
    for horizontal_squared, dx, dz in offsets_for_radius(radius):
        if best is not None and horizontal_squared > float(best[0][0]):
            break
        inspected_offsets += 1
        x = float(original[0]) + dx
        z = float(original[2]) + dz
        for y in y_candidates_for_column(index, x, z, float(original[1]), identifier, category, selected):
            position = (x, y, z)
            safe, _reason = position_is_safe(index, position, identifier, category, selected)
            if not safe:
                continue
            safe_before_occupancy += 1
            box = entity_box(position, width, height)
            collisions = [reserved_uuid for reserved_uuid, other in reserved_boxes if boxes_overlap(box, other)]
            if collisions:
                rejected_by_occupancy += 1
                continue
            dy = y - float(original[1])
            distance_squared = float(horizontal_squared) + dy * dy
            # The first item is the geometric score.  Remaining fields make
            # selection deterministic without turning symmetric geography
            # into a false ambiguity.
            score = (
                round(distance_squared, 12),
                horizontal_squared,
                round(abs(dy), 12),
                round(y, 6),
                dx,
                dz,
            )
            tie_key = (round(distance_squared, 12),)
            if best is None or score < best[0]:
                best = (score, position, tie_key)
                equal_geometric_best = 1
            elif best is not None and tie_key == best[2]:
                equal_geometric_best += 1
    if best is None:
        raise EntityOtaError(
            f"no unique unoccupied safe {category} point within {radius} blocks for "
            f"{identifier} {entity_uuid} at {list(original)}"
        )
    selected_position = tuple(round(float(value), 6) for value in best[1])
    selected_box = entity_box(selected_position, width, height)
    reserved_boxes.append((entity_uuid, selected_box))
    return {
        "new_pos": list(selected_position),
        "search_radius_blocks": radius,
        "inspected_horizontal_offsets": inspected_offsets,
        "safe_candidates_before_entity_occupancy": safe_before_occupancy,
        "rejected_by_preserved_entity_occupancy": rejected_by_occupancy,
        "equal_geometric_nearest_candidates": equal_geometric_best,
        "assignment_is_unique": True,
        "selection_tiebreak": "distance_squared,horizontal_squared,abs_dy,y,dx,dz",
    }


@dataclass
class SlotRoot:
    region: tuple[int, int]
    slot: int
    chunk: tuple[int, int]
    timestamp: int
    compression: int
    raw: bytes
    root: Any


@dataclass
class EntityRecord:
    uuid: str
    identifier: str
    source_region: tuple[int, int]
    source_slot: int
    source_chunk: tuple[int, int]
    source_index: int
    position: tuple[float, float, float]
    payload_sha256: str
    semantic_sha256: str
    entity: Any


@dataclass
class CurrentDataset:
    images: dict[tuple[int, int], terrain_ota.RegionImage]
    raw_files: dict[tuple[int, int], bytes | None]
    slots: dict[tuple[int, int], SlotRoot]
    entities: dict[str, EntityRecord]


class ByteMapWorldSource:
    """Minimal read-only source used for detached bundle semantic audits."""

    source_type = "byte-map"

    def __init__(self, files: Mapping[str, bytes | None]):
        self.files = dict(files)

    def read(self, relative: str) -> bytes | None:
        return self.files.get(relative)

    def descriptor(self) -> dict[str, Any]:
        return {"type": self.source_type, "files": len(self.files)}


def load_current_dataset(source: terrain_ota.WorldSource) -> CurrentDataset:
    grouped = terrain_ota.selection_by_region()
    if sum(len(slots) for slots in grouped.values()) != EXPECTED_CHUNKS or len(grouped) != EXPECTED_REGIONS:
        raise EntityOtaError("protected selection geometry drift")
    images: dict[tuple[int, int], terrain_ota.RegionImage] = {}
    raw_files: dict[tuple[int, int], bytes | None] = {}
    slot_roots: dict[tuple[int, int], SlotRoot] = {}
    entities: dict[str, EntityRecord] = {}
    for region, selected_slots in grouped.items():
        relative = entity_relative(*region)
        data = source.read(relative)
        try:
            image = terrain_ota.RegionImage.parse(data, f"current::{relative}")
        except Exception as exc:
            raise EntityOtaError(str(exc)) from exc
        images[region] = image
        raw_files[region] = data
        for slot in sorted(image.records.keys() & selected_slots):
            chunk = chunk_for_slot(region[0], region[1], slot)
            record = image.records[slot]
            root, compression = decode_record(record.raw, f"{relative} slot {slot}")
            root_position = plain(root.get("Position")) if isinstance(root, Mapping) else None
            if root_position != [chunk[0], chunk[1]]:
                raise EntityOtaError(
                    f"{relative} slot {slot}: root Position {root_position!r} != chunk {chunk}"
                )
            version = int(plain(root.get("DataVersion", -1)))
            if version != DATA_VERSION:
                raise EntityOtaError(f"{relative} slot {slot}: DataVersion {version} != {DATA_VERSION}")
            root_entities = root.get("Entities")
            if not isinstance(root_entities, Sequence):
                raise EntityOtaError(f"{relative} slot {slot}: Entities is not a list")
            slot_roots[chunk] = SlotRoot(
                region=region,
                slot=slot,
                chunk=chunk,
                timestamp=record.timestamp,
                compression=compression,
                raw=record.raw,
                root=root,
            )
            for source_index, entity in enumerate(root_entities):
                if not isinstance(entity, Mapping):
                    raise EntityOtaError(f"{relative} slot {slot}: entity {source_index} is not a compound")
                nested = nested_passenger_count(entity)
                if nested:
                    raise EntityOtaError(
                        f"{relative} slot {slot}: nested Passengers are unsupported by the bound gate ({nested})"
                    )
                entity_uuid = uuid_from_entity(entity)
                if entity_uuid is None:
                    raise EntityOtaError(f"{relative} slot {slot}: entity {source_index} has no valid UUID")
                if entity_uuid in entities:
                    raise EntityOtaError(f"duplicate entity UUID in selected slots: {entity_uuid}")
                position = entity_position(entity)
                actual_chunk = chunk_for_position(position)
                if actual_chunk != chunk:
                    raise EntityOtaError(
                        f"entity {entity_uuid} position belongs to {actual_chunk}, not source chunk {chunk}"
                    )
                identifier = str(plain(entity.get("id", "<missing>")))
                entities[entity_uuid] = EntityRecord(
                    uuid=entity_uuid,
                    identifier=identifier,
                    source_region=region,
                    source_slot=slot,
                    source_chunk=chunk,
                    source_index=source_index,
                    position=position,
                    payload_sha256=entity_payload_sha256(entity),
                    semantic_sha256=entity_semantic_sha256(entity),
                    entity=entity,
                )
    if len(entities) != EXPECTED_ENTITIES:
        raise EntityOtaError(f"selected entity count {len(entities)} != {EXPECTED_ENTITIES}")
    return CurrentDataset(images=images, raw_files=raw_files, slots=slot_roots, entities=entities)


def load_and_verify_gate(gate_path: Path, source_sha: str, v_world: Path) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    gate_path = gate_path.resolve()
    gate_sha = sha256_file(gate_path)
    if gate_sha != EXPECTED_GATE_SHA256:
        raise EntityOtaError(f"collision gate SHA drift: {gate_sha}")
    gate = json_load(gate_path)
    if gate.get("status") != "BLOCKED_ENTITY_RELOCATION_OR_POLICY_REQUIRED":
        raise EntityOtaError(f"unexpected collision gate status: {gate.get('status')}")
    if gate.get("inputs", {}).get("source_archive", {}).get("sha256") != source_sha:
        raise EntityOtaError("collision gate is not bound to the current source archive")
    gate_v = Path(str(gate.get("inputs", {}).get("v_world", ""))).resolve()
    if gate_v != v_world.resolve():
        raise EntityOtaError(f"collision gate V path drift: {gate_v} != {v_world.resolve()}")
    strict_path = Path(str(gate["inputs"]["v_strict_audit"]["path"])).resolve()
    strict_sha = sha256_file(strict_path)
    if strict_sha != EXPECTED_STRICT_AUDIT_SHA256:
        raise EntityOtaError(f"V strict audit SHA drift: {strict_sha}")
    if gate["inputs"]["v_strict_audit"].get("sha256") != strict_sha:
        raise EntityOtaError("collision gate's V strict-audit binding is stale")
    strict = json_load(strict_path)
    if strict.get("status") != "PASS":
        raise EntityOtaError(f"V strict audit is not PASS: {strict.get('status')}")
    target = strict.get("target", {})
    if (
        int(target.get("chunks", -1)) != EXPECTED_CHUNKS
        or int(target.get("regions", -1)) != EXPECTED_REGIONS
        or int(target.get("missing_terrain_chunks", -1)) != 0
        or int(target.get("extra_terrain_chunks", -1)) != 0
    ):
        raise EntityOtaError(f"V strict target drift: {target}")
    failures: list[str] = []
    manifest = strict.get("mca", {}).get("region", {}).get("manifest", [])
    if len(manifest) != EXPECTED_REGIONS:
        failures.append(f"V region manifest has {len(manifest)} files, expected {EXPECTED_REGIONS}")
    for row in manifest:
        path = Path(str(row.get("path", ""))).resolve()
        expected_parent = (v_world.resolve() / "region")
        if path.parent != expected_parent:
            failures.append(f"V manifest path escapes strict world: {path}")
            continue
        if not path.is_file():
            failures.append(f"missing V region file: {path}")
            continue
        actual = sha256_file(path)
        if actual != row.get("sha256"):
            failures.append(f"V region hash drift: {path.name}: {actual}")
    if failures:
        raise EntityOtaError("; ".join(failures[:5]))
    return gate, gate_sha, strict, strict_sha


def validate_gate_against_dataset(gate: Mapping[str, Any], dataset: CurrentDataset) -> dict[str, Mapping[str, Any]]:
    rows = gate.get("entity_gate", {}).get("all_rows", [])
    if not isinstance(rows, Sequence) or len(rows) != EXPECTED_ENTITIES:
        raise EntityOtaError(f"collision gate entity rows {len(rows) if isinstance(rows, Sequence) else 'invalid'} != {EXPECTED_ENTITIES}")
    by_uuid: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise EntityOtaError("collision gate contains a non-object entity row")
        entity_uuid = str(row.get("uuid"))
        if entity_uuid in by_uuid:
            raise EntityOtaError(f"collision gate contains duplicate UUID {entity_uuid}")
        by_uuid[entity_uuid] = row
    if set(by_uuid) != set(dataset.entities):
        missing = sorted(set(dataset.entities) - set(by_uuid))
        extra = sorted(set(by_uuid) - set(dataset.entities))
        raise EntityOtaError(f"collision gate/source UUID mismatch: missing={missing[:3]}, extra={extra[:3]}")
    for entity_uuid, record in dataset.entities.items():
        row = by_uuid[entity_uuid]
        if str(row.get("id")) != record.identifier:
            raise EntityOtaError(f"collision gate id drift for {entity_uuid}")
        gate_pos = row.get("pos")
        if not isinstance(gate_pos, Sequence) or len(gate_pos) < 3:
            raise EntityOtaError(f"collision gate position missing for {entity_uuid}")
        if any(abs(float(gate_pos[i]) - record.position[i]) > 1.0e-9 for i in range(3)):
            raise EntityOtaError(f"collision gate position drift for {entity_uuid}")
        if list(row.get("source_chunk", [])) != list(record.source_chunk):
            raise EntityOtaError(f"collision gate source chunk drift for {entity_uuid}")
        if row.get("verdict") not in {"PASS", "REVIEW", "BLOCKED"}:
            raise EntityOtaError(f"collision gate verdict invalid for {entity_uuid}: {row.get('verdict')}")
    return by_uuid


def relocation_priority(record: EntityRecord, gate_row: Mapping[str, Any]) -> tuple[Any, ...]:
    category = category_for(record.identifier)
    persistent = "persistent" in set(gate_row.get("flags", []))
    width, height = collision_gate.ENTITY_DIMENSIONS.get(record.identifier, (1.0, 2.0))
    return (CATEGORY_ORDER[category], 0 if persistent else 1, -(width * width * height), record.uuid)


def create_assignments(
    dataset: CurrentDataset,
    gate_rows: Mapping[str, Mapping[str, Any]],
    v_world: Path,
) -> list[dict[str, Any]]:
    selected = set(terrain_ota.selected_chunks())
    index = collision_gate.VBlockIndex(v_world)
    reserved: list[tuple[str, tuple[float, float, float, float, float, float]]] = []
    assignments: dict[str, dict[str, Any]] = {}
    for record in dataset.entities.values():
        row = gate_rows[record.uuid]
        if row.get("verdict") != "PASS":
            continue
        width, height = collision_gate.ENTITY_DIMENSIONS.get(record.identifier, (1.0, 2.0))
        reserved.append((record.uuid, entity_box(record.position, width, height)))
        assignments[record.uuid] = {
            "uuid": record.uuid,
            "id": record.identifier,
            "gate_verdict": "PASS",
            "category": category_for(record.identifier),
            "moved": False,
            "old_pos": list(record.position),
            "new_pos": list(record.position),
            "source_chunk": list(record.source_chunk),
            "destination_chunk": list(record.source_chunk),
            "source_region": list(record.source_region),
            "source_slot": record.source_slot,
            "payload_sha256": record.payload_sha256,
            "pre_semantic_sha256": record.semantic_sha256,
            "search": None,
        }
    to_move = [record for record in dataset.entities.values() if gate_rows[record.uuid].get("verdict") != "PASS"]
    to_move.sort(key=lambda record: relocation_priority(record, gate_rows[record.uuid]))
    for record in to_move:
        row = gate_rows[record.uuid]
        category = category_for(record.identifier)
        result = relocate_entity(
            index,
            record.identifier,
            record.uuid,
            record.position,
            category,
            selected,
            reserved,
        )
        new_position = tuple(float(value) for value in result.pop("new_pos"))
        destination_chunk = chunk_for_position(new_position)
        if destination_chunk not in selected:
            raise EntityOtaError(f"relocation escaped selected chunks for {record.uuid}: {destination_chunk}")
        assignments[record.uuid] = {
            "uuid": record.uuid,
            "id": record.identifier,
            "gate_verdict": row.get("verdict"),
            "category": category,
            "moved": True,
            "old_pos": list(record.position),
            "new_pos": list(new_position),
            "source_chunk": list(record.source_chunk),
            "destination_chunk": list(destination_chunk),
            "source_region": list(record.source_region),
            "source_slot": record.source_slot,
            "payload_sha256": record.payload_sha256,
            "pre_semantic_sha256": record.semantic_sha256,
            "search": result,
        }
    if set(assignments) != set(dataset.entities):
        raise EntityOtaError("assignment set does not cover every selected entity")
    return [assignments[key] for key in sorted(assignments)]


def assignment_map(assignments: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in assignments:
        entity_uuid = str(row.get("uuid"))
        if entity_uuid in result:
            raise EntityOtaError(f"duplicate assignment UUID {entity_uuid}")
        result[entity_uuid] = row
    return result


def validate_assignments(
    dataset: CurrentDataset,
    gate_rows: Mapping[str, Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    v_world: Path,
) -> None:
    by_uuid = assignment_map(assignments)
    if set(by_uuid) != set(dataset.entities):
        raise EntityOtaError("assignment UUID set differs from source entity UUID set")
    selected = set(terrain_ota.selected_chunks())
    index = collision_gate.VBlockIndex(v_world)
    pass_boxes: list[tuple[str, tuple[float, float, float, float, float, float]]] = []
    moved_rows: list[tuple[EntityRecord, Mapping[str, Any]]] = []
    for entity_uuid, record in dataset.entities.items():
        row = by_uuid[entity_uuid]
        if row.get("id") != record.identifier or row.get("payload_sha256") != record.payload_sha256:
            raise EntityOtaError(f"assignment identity/payload drift for {entity_uuid}")
        old_pos = row.get("old_pos")
        new_pos = row.get("new_pos")
        if not isinstance(old_pos, Sequence) or not isinstance(new_pos, Sequence):
            raise EntityOtaError(f"assignment position missing for {entity_uuid}")
        if any(abs(float(old_pos[i]) - record.position[i]) > 1.0e-9 for i in range(3)):
            raise EntityOtaError(f"assignment old position drift for {entity_uuid}")
        expected_move = gate_rows[entity_uuid].get("verdict") != "PASS"
        if bool(row.get("moved")) != expected_move:
            raise EntityOtaError(f"assignment move policy drift for {entity_uuid}")
        width, height = collision_gate.ENTITY_DIMENSIONS.get(record.identifier, (1.0, 2.0))
        if expected_move:
            moved_rows.append((record, row))
        else:
            if any(abs(float(new_pos[i]) - record.position[i]) > 1.0e-9 for i in range(3)):
                raise EntityOtaError(f"PASS entity position changed in assignment: {entity_uuid}")
            pass_boxes.append((entity_uuid, entity_box(new_pos, width, height)))
    moved_rows.sort(key=lambda pair: relocation_priority(pair[0], gate_rows[pair[0].uuid]))
    reserved = list(pass_boxes)
    for record, row in moved_rows:
        new_pos = [float(value) for value in row["new_pos"]]
        category = category_for(record.identifier)
        if row.get("category") != category:
            raise EntityOtaError(f"assignment category drift for {record.uuid}")
        safe, reason = position_is_safe(index, new_pos, record.identifier, category, selected)
        if not safe:
            raise EntityOtaError(f"assigned destination is unsafe for {record.uuid}: {reason}")
        width, height = collision_gate.ENTITY_DIMENSIONS.get(record.identifier, (1.0, 2.0))
        box = entity_box(new_pos, width, height)
        collisions = [other_uuid for other_uuid, other in reserved if boxes_overlap(box, other)]
        if collisions:
            raise EntityOtaError(f"assigned destination overlaps preserved entity for {record.uuid}: {collisions[:3]}")
        if chunk_for_position(new_pos) != tuple(int(v) for v in row["destination_chunk"]):
            raise EntityOtaError(f"assignment destination chunk drift for {record.uuid}")
        reserved.append((record.uuid, box))


def make_new_root(chunk: tuple[int, int], entities: Sequence[Any]) -> Any:
    compound = nbtlib.Compound(
        {
            "Entities": nbtlib.List[nbtlib.Compound](list(entities)),
            "DataVersion": nbtlib.Int(DATA_VERSION),
            "Position": nbtlib.IntArray([chunk[0], chunk[1]]),
            "brewinandchewin:data_version": nbtlib.Int(100),
        }
    )
    return nbtlib.File(compound)


def build_desired_images(
    dataset: CurrentDataset,
    assignments: Sequence[Mapping[str, Any]],
) -> tuple[dict[tuple[int, int], bytes | None], list[dict[str, Any]], dict[str, Any]]:
    by_uuid = assignment_map(assignments)
    mutated_entities: dict[str, Any] = {}
    destinations: dict[tuple[int, int], list[tuple[tuple[Any, ...], str, Any]]] = defaultdict(list)
    for entity_uuid, record in dataset.entities.items():
        entity = copy.deepcopy(record.entity)
        assignment = by_uuid[entity_uuid]
        set_entity_position(entity, assignment["new_pos"])
        payload_sha = entity_payload_sha256(entity)
        if payload_sha != record.payload_sha256:
            raise EntityOtaError(f"entity payload changed while relocating {entity_uuid}")
        if uuid_from_entity(entity) != entity_uuid:
            raise EntityOtaError(f"entity UUID changed while relocating {entity_uuid}")
        mutated_entities[entity_uuid] = entity
        destination = tuple(int(value) for value in assignment["destination_chunk"])
        same_slot = destination == record.source_chunk
        order = (0 if same_slot else 1, record.source_index if same_slot else 0, entity_uuid)
        destinations[destination].append((order, entity_uuid, entity))
    post_payloads: dict[str, str] = {}
    post_semantics: dict[str, str] = {}
    for entity_uuid, entity in mutated_entities.items():
        post_payloads[entity_uuid] = entity_payload_sha256(entity)
        post_semantics[entity_uuid] = entity_semantic_sha256(entity)
    if set(post_payloads) != set(dataset.entities) or len(post_payloads) != EXPECTED_ENTITIES:
        raise EntityOtaError("postimage entity UUID set/count drift")
    if any(post_payloads[key] != dataset.entities[key].payload_sha256 for key in post_payloads):
        raise EntityOtaError("postimage entity payload hash drift")

    grouped = terrain_ota.selection_by_region()
    desired_files: dict[tuple[int, int], bytes | None] = {}
    file_rows: list[dict[str, Any]] = []
    occupied_post_chunks = 0
    for region, selected_slots in grouped.items():
        current_image = dataset.images[region]
        desired_records = dict(current_image.records)
        desired_timestamps = list(current_image.timestamps)
        for slot in selected_slots:
            chunk = chunk_for_slot(region[0], region[1], slot)
            rows = sorted(destinations.get(chunk, []), key=lambda row: row[0])
            if not rows:
                desired_records.pop(slot, None)
                desired_timestamps[slot] = 0
                continue
            occupied_post_chunks += 1
            entities = [entity for _order, _uuid, entity in rows]
            source_slot = dataset.slots.get(chunk)
            if source_slot is None:
                root = make_new_root(chunk, entities)
                compression = 2
                source_timestamps = [
                    dataset.slots[dataset.entities[entity_uuid].source_chunk].timestamp
                    for _order, entity_uuid, _entity in rows
                ]
                timestamp = max(source_timestamps, default=0)
            else:
                root = copy.deepcopy(source_slot.root)
                root["Entities"] = nbtlib.List[nbtlib.Compound](entities)
                root["DataVersion"] = nbtlib.Int(DATA_VERSION)
                root["Position"] = nbtlib.IntArray([chunk[0], chunk[1]])
                compression = source_slot.compression
                timestamp = source_slot.timestamp
            raw = encode_record(root, compression, f"post::{entity_relative(*region)} slot {slot}")
            if source_slot is not None and raw == source_slot.raw:
                raw = source_slot.raw
            desired_records[slot] = terrain_ota.ChunkRecord(timestamp=timestamp, raw=raw)
            desired_timestamps[slot] = timestamp
        desired_image = terrain_ota.RegionImage(desired_records, desired_timestamps)
        if desired_image.semantically_equal(current_image):
            post_data = dataset.raw_files[region]
        elif not desired_image.records:
            post_data = None
        else:
            post_data = desired_image.encode()
        reparsed = terrain_ota.RegionImage.parse(post_data, f"rebuilt::{entity_relative(*region)}")
        outside = frozenset(set(range(1024)) - set(selected_slots))
        if reparsed.signature(outside) != current_image.signature(outside):
            raise EntityOtaError(f"outside entity slots changed in region {region}")
        if reparsed.signature(selected_slots) != desired_image.signature(selected_slots):
            raise EntityOtaError(f"selected entity slots do not match desired image in region {region}")
        relative = entity_relative(*region)
        pre = file_identity_bytes(dataset.raw_files[region])
        post = file_identity_bytes(post_data)
        desired_files[region] = post_data
        file_rows.append(
            {
                "kind": "entities",
                "region": list(region),
                "relative_path": relative,
                "selected_slots": len(selected_slots),
                "changed": not identity_equal(pre, post),
                "pre": pre,
                "post": post,
                "selected_pre_signature": current_image.signature(selected_slots),
                "selected_post_signature": reparsed.signature(selected_slots),
                "outside_pre_signature": current_image.signature(outside),
                "outside_post_signature": reparsed.signature(outside),
                "selected_pre_occupied": len(current_image.records.keys() & selected_slots),
                "selected_post_occupied": len(reparsed.records.keys() & selected_slots),
                "outside_occupied": len(current_image.records.keys() & outside),
            }
        )
    semantic = {
        "pre_entity_count": len(dataset.entities),
        "post_entity_count": len(post_payloads),
        "pre_uuid_sha256": sha256_bytes(canonical_json_bytes(sorted(dataset.entities))),
        "post_uuid_sha256": sha256_bytes(canonical_json_bytes(sorted(post_payloads))),
        "pre_payload_map_sha256": sha256_bytes(
            canonical_json_bytes({key: dataset.entities[key].payload_sha256 for key in sorted(dataset.entities)})
        ),
        "post_payload_map_sha256": sha256_bytes(
            canonical_json_bytes({key: post_payloads[key] for key in sorted(post_payloads)})
        ),
        "post_semantic_map_sha256": sha256_bytes(
            canonical_json_bytes({key: post_semantics[key] for key in sorted(post_semantics)})
        ),
        "occupied_selected_entity_slots_pre": len(dataset.slots),
        "occupied_selected_entity_slots_post": occupied_post_chunks,
        "silent_deletions": 0,
        "payload_drifts": 0,
        "duplicate_uuids": 0,
    }
    if semantic["pre_uuid_sha256"] != semantic["post_uuid_sha256"]:
        raise EntityOtaError("postimage UUID manifest drift")
    if semantic["pre_payload_map_sha256"] != semantic["post_payload_map_sha256"]:
        raise EntityOtaError("postimage payload manifest drift")
    return desired_files, file_rows, semantic


def operational_digest_payload(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_archive_sha256": plan["inputs"]["current"]["archive"]["sha256"],
        "world_prefix": plan["inputs"]["current"].get("world_prefix"),
        "gate_sha256": plan["inputs"]["collision_gate"]["sha256"],
        "v_world": plan["inputs"]["v_world"],
        "v_strict_audit_sha256": plan["inputs"]["v_strict_audit"]["sha256"],
        "selection": plan["selection"],
        "policy": plan["policy"],
        "assignments": plan["assignments"],
        "files": plan["files"],
        "semantic_postconditions": plan["semantic_postconditions"],
        "delivery": plan["delivery"],
    }


def create_plan(
    current: terrain_ota.WorldSource,
    gate_path: Path,
    v_world: Path,
) -> tuple[dict[str, Any], dict[tuple[int, int], bytes | None]]:
    descriptor = current.descriptor()
    source_sha = descriptor.get("archive", {}).get("sha256") if descriptor.get("type") == "zip" else None
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise EntityOtaError(f"current archive SHA drift: {source_sha}")
    gate, gate_sha, strict, strict_sha = load_and_verify_gate(gate_path, source_sha, v_world)
    dataset = load_current_dataset(current)
    gate_rows = validate_gate_against_dataset(gate, dataset)
    assignments = create_assignments(dataset, gate_rows, v_world)
    validate_assignments(dataset, gate_rows, assignments, v_world)
    desired, file_rows, semantic = build_desired_images(dataset, assignments)
    verdict_counts = Counter(row["gate_verdict"] for row in assignments)
    category_counts = Counter(row["category"] for row in assignments if row["moved"])
    cross_chunk = sum(row["source_chunk"] != row["destination_chunk"] for row in assignments)
    plan: dict[str, Any] = {
        "schema": SCHEMA_PLAN,
        "generated_at_utc": utc_now(),
        "status": "READY_FOR_DETACHED_BUNDLE_BUILD",
        "operation": "payload-preserving-protected-zone-selected-entity-slot-rebuild",
        "inputs": {
            "current": descriptor,
            "collision_gate": {"path": str(gate_path.resolve()), "sha256": gate_sha},
            "v_world": str(v_world.resolve()),
            "v_strict_audit": {
                "path": gate["inputs"]["v_strict_audit"]["path"],
                "sha256": strict_sha,
                "status": strict.get("status"),
            },
        },
        "selection": {
            "dimension": "minecraft:overworld",
            "center": {"x": terrain_ota.CENTER_X, "z": terrain_ota.CENTER_Z},
            "radius_blocks": terrain_ota.FREEZE_RADIUS,
            "selected_chunks": EXPECTED_CHUNKS,
            "selected_regions": EXPECTED_REGIONS,
        },
        "policy": {
            "preserve_all_current_entities": True,
            "preserve_all_payload_fields_except_position": True,
            "allowed_entity_nbt_changes": ["Pos"],
            "selected_slots": "complete C entity set, with blocked/review entities relocated and rebucketed",
            "outside_slots": "raw compressed record and timestamp byte-identical to C",
            "aquatic": "nearest deterministic unoccupied fully-water-filled AABB",
            "ground": "nearest deterministic unoccupied top safe surface",
            "item": "nearest deterministic unoccupied supported non-hazardous point",
            "flying": "nearest deterministic unoccupied clear-air AABB",
            "falling_block": "nearest deterministic unoccupied clear point with one-block fall path and safe landing",
            "no_safe_unique_point": "BLOCK; never delete silently",
        },
        "summary": {
            "entities": len(assignments),
            "moved": sum(bool(row["moved"]) for row in assignments),
            "unchanged_position": sum(not bool(row["moved"]) for row in assignments),
            "gate_verdict_counts": dict(sorted(verdict_counts.items())),
            "moved_category_counts": dict(sorted(category_counts.items())),
            "cross_chunk_moves": cross_chunk,
            "changed_entity_region_files": sum(bool(row["changed"]) for row in file_rows),
        },
        "assignments": assignments,
        "files": file_rows,
        "semantic_postconditions": semantic,
        "delivery": {
            "intended_validation_target": str(INTENDED_TERRAIN_TEST_CLONE),
            "production_world_apply_authorized": False,
            "production_release_requires_fresh_stopped-world_CAS_validation": True,
        },
        "non_actions": {
            "source_archive_modified": False,
            "v_world_modified": False,
            "existing_clone_modified": False,
            "java_started": False,
        },
    }
    plan["operational_digest_sha256"] = sha256_bytes(canonical_json_bytes(operational_digest_payload(plan)))
    return plan, desired


def source_from_plan(plan: Mapping[str, Any]) -> terrain_ota.WorldSource:
    try:
        source = terrain_ota.source_from_descriptor(plan["inputs"]["current"])
    except Exception as exc:
        raise EntityOtaError(str(exc)) from exc
    descriptor = source.descriptor()
    expected = plan["inputs"]["current"]
    if descriptor != expected:
        source.close()
        raise EntityOtaError("current source descriptor changed after planning")
    return source


def validate_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema") != SCHEMA_PLAN or plan.get("status") != "READY_FOR_DETACHED_BUNDLE_BUILD":
        raise EntityOtaError("plan schema/status is not buildable")
    if plan.get("selection", {}).get("selected_chunks") != EXPECTED_CHUNKS:
        raise EntityOtaError("plan selected-chunk count drift")
    if plan.get("selection", {}).get("selected_regions") != EXPECTED_REGIONS:
        raise EntityOtaError("plan selected-region count drift")
    digest = sha256_bytes(canonical_json_bytes(operational_digest_payload(plan)))
    if digest != plan.get("operational_digest_sha256"):
        raise EntityOtaError("plan operational digest mismatch")


def safe_bundle_relative(relative: str) -> None:
    try:
        terrain_ota.validate_relative_path(relative)
    except Exception as exc:
        raise EntityOtaError(str(exc)) from exc
    if not relative.startswith("entities/"):
        raise EntityOtaError(f"entity OTA path must stay under entities/: {relative}")


def build_bundle(plan_path: Path, bundle_root: Path) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    plan = json_load(plan_path)
    validate_plan(plan)
    bundle_root = bundle_root.resolve()
    if bundle_root.exists():
        raise EntityOtaError(f"bundle root already exists: {bundle_root}")
    with source_from_plan(plan) as current:
        source_sha = current.descriptor()["archive"]["sha256"]
        gate_path = Path(str(plan["inputs"]["collision_gate"]["path"]))
        v_world = Path(str(plan["inputs"]["v_world"]))
        gate, gate_sha, _strict, strict_sha = load_and_verify_gate(gate_path, source_sha, v_world)
        if gate_sha != plan["inputs"]["collision_gate"]["sha256"]:
            raise EntityOtaError("collision gate changed after planning")
        if strict_sha != plan["inputs"]["v_strict_audit"]["sha256"]:
            raise EntityOtaError("V strict audit changed after planning")
        dataset = load_current_dataset(current)
        gate_rows = validate_gate_against_dataset(gate, dataset)
        validate_assignments(dataset, gate_rows, plan["assignments"], v_world)
        desired, files, semantic = build_desired_images(dataset, plan["assignments"])
        if files != plan["files"] or semantic != plan["semantic_postconditions"]:
            raise EntityOtaError("recomputed postimage differs from the signed plan")

        temporary_parent = bundle_root.parent
        temporary_parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{bundle_root.name}.build-", dir=temporary_parent))
        try:
            plan_copy = staging / "plan.json"
            atomic_write_bytes(plan_copy, plan_path.read_bytes())
            changes: list[dict[str, Any]] = []
            guards: list[dict[str, Any]] = []
            for row in files:
                relative = str(row["relative_path"])
                safe_bundle_relative(relative)
                region = tuple(int(value) for value in row["region"])
                pre_data = dataset.raw_files[region]
                preimage_relative = f"preimages/{relative}" if pre_data is not None else None
                if preimage_relative:
                    atomic_write_bytes(staging / Path(preimage_relative), pre_data)
                guard = {
                    "kind": "entities",
                    "region": row["region"],
                    "relative_path": relative,
                    "selected_slots": row["selected_slots"],
                    "pre": row["pre"],
                    "post": row["post"],
                    "preimage_relative_path": preimage_relative,
                    "selected_pre_signature": row["selected_pre_signature"],
                    "selected_post_signature": row["selected_post_signature"],
                    "outside_pre_signature": row["outside_pre_signature"],
                    "outside_post_signature": row["outside_post_signature"],
                }
                guards.append(guard)
                if not row["changed"]:
                    continue
                post_data = desired[region]
                payload_relative = f"payload/{relative}" if post_data is not None else None
                if payload_relative:
                    atomic_write_bytes(staging / Path(payload_relative), post_data)
                changes.append(
                    {
                        **guard,
                        "payload_relative_path": payload_relative,
                    }
                )
            tool_paths = [
                Path(__file__).resolve(),
                SCRIPT_DIR / "test_protected_zone_entity_ota.py",
                SCRIPT_DIR / "protected_zone_terrain_ota.py",
                SCRIPT_DIR / "audit_protected_zone_entity_poi_gate.py",
            ]
            tools_manifest: list[dict[str, Any]] = []
            for tool in tool_paths:
                target = staging / "tools" / tool.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tool, target)
                tools_manifest.append(
                    {
                        "relative_path": target.relative_to(staging).as_posix(),
                        "bytes": target.stat().st_size,
                        "sha256": sha256_file(target),
                    }
                )
            manifest: dict[str, Any] = {
                "schema": SCHEMA_BUNDLE,
                "generated_at_utc": utc_now(),
                "status": "VERIFIED_DETACHED_BUNDLE",
                "plan_relative_path": "plan.json",
                "plan_sha256": sha256_file(plan_copy),
                "operational_digest_sha256": plan["operational_digest_sha256"],
                "changes": changes,
                "guard_files": guards,
                "semantic_postconditions": semantic,
                "intended_validation_target": plan["delivery"]["intended_validation_target"],
                "production_world_apply_authorized": False,
                "tools": tools_manifest,
                "application_requirements": {
                    "server_stopped": True,
                    "required_literal_ack": STOPPED_ACK,
                    "target_preimage_must_match_C": True,
                    "preimage_backup_required": True,
                    "automatic_rollback_on_apply_failure": True,
                    "idempotent_postimage_detection": True,
                },
            }
            atomic_write_json(staging / "bundle.json", manifest)
            readme = (
                "# Protected-zone entity OTA (detached)\n\n"
                "This bundle preserves all 198 current C entities and their payload.  It changes only selected "
                "Overworld entity chunk slots; outside raw records and timestamps remain C.\n\n"
                f"The intended validation target is `{plan['delivery']['intended_validation_target']}`.  This "
                "artifact does not authorize a production-world apply; production requires a fresh stopped-world "
                "CAS validation.\n\n"
                "Run `verify-bundle` first.  Apply only to a stopped extracted world whose entity files still match "
                "the C preimage.  `apply` requires `--allow-world-write --stopped-server-ack SERVER_IS_STOPPED` and "
                "a new D-drive backup root.  Keep that backup and its apply receipt until rollback is no longer needed.\n"
            )
            atomic_write_bytes(staging / "README.md", readme.encode("utf-8"))
            artifact_rows: list[str] = []
            for path in sorted(staging.rglob("*")):
                if path.is_file() and path.name != "ARTIFACTS.sha256":
                    artifact_rows.append(f"{sha256_file(path)} *{path.relative_to(staging).as_posix()}")
            atomic_write_bytes(staging / "ARTIFACTS.sha256", ("\n".join(artifact_rows) + "\n").encode("utf-8"))
            os.replace(staging, bundle_root)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    manifest, _plan = read_bundle(bundle_root)
    return {
        "schema": "protected-zone-entity-ota-build-result/v1",
        "generated_at_utc": utc_now(),
        "status": "PASS",
        "bundle_root": str(bundle_root),
        "changes": len(manifest["changes"]),
        "guard_files": len(manifest["guard_files"]),
        "entities": manifest["semantic_postconditions"]["post_entity_count"],
        "payload_drifts": manifest["semantic_postconditions"]["payload_drifts"],
        "world_modified": False,
    }


def verify_artifacts_sha(bundle_root: Path) -> None:
    manifest_path = bundle_root / "ARTIFACTS.sha256"
    if not manifest_path.is_file():
        raise EntityOtaError("ARTIFACTS.sha256 is missing")
    listed: set[str] = set()
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, marker_path = line.split(" ", 1)
        relative = marker_path[1:] if marker_path.startswith("*") else marker_path
        path = bundle_root / Path(relative)
        if not path.is_file():
            raise EntityOtaError(f"listed bundle artifact is missing: {relative}")
        if sha256_file(path) != digest:
            raise EntityOtaError(f"bundle artifact hash mismatch: {relative}")
        listed.add(relative.replace("\\", "/"))
    actual = {
        path.relative_to(bundle_root).as_posix()
        for path in bundle_root.rglob("*")
        if path.is_file() and path.name != "ARTIFACTS.sha256"
    }
    if listed != actual:
        raise EntityOtaError(
            f"bundle artifact manifest mismatch: unlisted={sorted(actual-listed)}, missing={sorted(listed-actual)}"
        )


def read_bundle(bundle_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle_root = bundle_root.resolve()
    manifest = json_load(bundle_root / "bundle.json")
    if manifest.get("schema") != SCHEMA_BUNDLE or manifest.get("status") != "VERIFIED_DETACHED_BUNDLE":
        raise EntityOtaError("bundle schema/status is invalid")
    plan_path = bundle_root / Path(str(manifest.get("plan_relative_path")))
    if not plan_path.is_file() or sha256_file(plan_path) != manifest.get("plan_sha256"):
        raise EntityOtaError("bundle plan is missing or changed")
    plan = json_load(plan_path)
    validate_plan(plan)
    if plan.get("operational_digest_sha256") != manifest.get("operational_digest_sha256"):
        raise EntityOtaError("bundle/plan operational digest mismatch")
    verify_artifacts_sha(bundle_root)
    guard_paths: set[str] = set()
    pre_files: dict[str, bytes | None] = {}
    for row in manifest.get("guard_files", []):
        relative = str(row.get("relative_path"))
        safe_bundle_relative(relative)
        if relative in guard_paths:
            raise EntityOtaError(f"duplicate guard path: {relative}")
        guard_paths.add(relative)
        if row.get("outside_pre_signature") != row.get("outside_post_signature"):
            raise EntityOtaError(f"outside-slot signature changed in bundle: {relative}")
        preimage_relative = row.get("preimage_relative_path")
        if row["pre"]["exists"]:
            expected = f"preimages/{relative}"
            if preimage_relative != expected:
                raise EntityOtaError(f"guard preimage path mismatch: {relative}")
            path = bundle_root / Path(expected)
            if not identity_equal(file_identity_path(path), row["pre"]):
                raise EntityOtaError(f"guard preimage identity mismatch: {relative}")
            pre_files[relative] = path.read_bytes()
        else:
            if preimage_relative is not None:
                raise EntityOtaError(f"missing guard preimage unexpectedly has a path: {relative}")
            pre_files[relative] = None
    if len(guard_paths) != EXPECTED_REGIONS:
        raise EntityOtaError(f"bundle guard file count {len(guard_paths)} != {EXPECTED_REGIONS}")
    change_paths: set[str] = set()
    for change in manifest.get("changes", []):
        relative = str(change.get("relative_path"))
        if relative not in guard_paths or relative in change_paths:
            raise EntityOtaError(f"invalid or duplicate change path: {relative}")
        change_paths.add(relative)
        payload_relative = change.get("payload_relative_path")
        if change["post"]["exists"]:
            expected = f"payload/{relative}"
            if payload_relative != expected or not identity_equal(
                file_identity_path(bundle_root / Path(expected)), change["post"]
            ):
                raise EntityOtaError(f"payload identity mismatch: {relative}")
        elif payload_relative is not None:
            raise EntityOtaError(f"deleted postimage unexpectedly has payload: {relative}")
        selected_slots = terrain_ota.selection_by_region()[tuple(int(v) for v in change["region"])]
        outside = frozenset(set(range(1024)) - set(selected_slots))
        if change["pre"]["exists"]:
            pre_image = terrain_ota.RegionImage.parse(
                pre_files[relative], f"bundle-pre::{relative}"
            )
        else:
            pre_image = terrain_ota.RegionImage()
        if change["post"]["exists"]:
            post_image = terrain_ota.RegionImage.parse(
                (bundle_root / Path(str(payload_relative))).read_bytes(), f"bundle-post::{relative}"
            )
        else:
            post_image = terrain_ota.RegionImage()
        if pre_image.signature(outside) != change["outside_pre_signature"]:
            raise EntityOtaError(f"bundle preimage outside signature mismatch: {relative}")
        if post_image.signature(outside) != change["outside_post_signature"]:
            raise EntityOtaError(f"bundle postimage outside signature mismatch: {relative}")
        if post_image.signature(selected_slots) != change["selected_post_signature"]:
            raise EntityOtaError(f"bundle selected post signature mismatch: {relative}")
    semantic = manifest.get("semantic_postconditions", {})
    if (
        semantic.get("pre_entity_count") != EXPECTED_ENTITIES
        or semantic.get("post_entity_count") != EXPECTED_ENTITIES
        or semantic.get("pre_uuid_sha256") != semantic.get("post_uuid_sha256")
        or semantic.get("pre_payload_map_sha256") != semantic.get("post_payload_map_sha256")
        or semantic.get("silent_deletions") != 0
        or semantic.get("payload_drifts") != 0
        or semantic.get("duplicate_uuids") != 0
    ):
        raise EntityOtaError(f"bundle semantic postconditions failed: {semantic}")
    post_files = dict(pre_files)
    for change in manifest.get("changes", []):
        relative = str(change["relative_path"])
        if change["post"]["exists"]:
            post_files[relative] = (bundle_root / Path(str(change["payload_relative_path"]))).read_bytes()
        else:
            post_files[relative] = None
    pre_dataset = load_current_dataset(ByteMapWorldSource(pre_files))
    post_dataset = load_current_dataset(ByteMapWorldSource(post_files))
    assignments = assignment_map(plan["assignments"])
    if set(assignments) != set(pre_dataset.entities) or set(assignments) != set(post_dataset.entities):
        raise EntityOtaError("bundle semantic reparse UUID set differs from plan")
    for entity_uuid, assignment in assignments.items():
        before = pre_dataset.entities[entity_uuid]
        after = post_dataset.entities[entity_uuid]
        if before.identifier != assignment["id"] or after.identifier != assignment["id"]:
            raise EntityOtaError(f"bundle semantic reparse id drift for {entity_uuid}")
        if before.payload_sha256 != assignment["payload_sha256"]:
            raise EntityOtaError(f"bundle preimage payload drift for {entity_uuid}")
        if after.payload_sha256 != assignment["payload_sha256"]:
            raise EntityOtaError(f"bundle postimage payload drift for {entity_uuid}")
        if any(abs(before.position[i] - float(assignment["old_pos"][i])) > 1.0e-9 for i in range(3)):
            raise EntityOtaError(f"bundle preimage position drift for {entity_uuid}")
        if any(abs(after.position[i] - float(assignment["new_pos"][i])) > 1.0e-9 for i in range(3)):
            raise EntityOtaError(f"bundle postimage position drift for {entity_uuid}")
    return manifest, plan


def target_path(world_root: Path, relative: str) -> Path:
    safe_bundle_relative(relative)
    path = world_root / Path(relative)
    if path.is_symlink():
        raise EntityOtaError(f"linked target file is refused: {path}")
    root = world_root.resolve()
    parent = path.parent.resolve()
    try:
        parent.relative_to(root)
    except ValueError as exc:
        raise EntityOtaError(f"target path escapes world root: {path}") from exc
    return path


def verify_target(bundle_root: Path, world_root: Path, state: str) -> dict[str, Any]:
    manifest, _plan = read_bundle(bundle_root)
    world_root = world_root.resolve()
    if not world_root.is_dir():
        raise EntityOtaError(f"target world root is missing: {world_root}")
    changes = {str(row["relative_path"]): row for row in manifest["changes"]}
    mismatches: list[dict[str, Any]] = []
    for guard in manifest["guard_files"]:
        relative = str(guard["relative_path"])
        expected = guard["pre"] if state == "pre" else guard["post"]
        actual = file_identity_path(target_path(world_root, relative))
        if not identity_equal(actual, expected):
            mismatches.append({"relative_path": relative, "expected": expected, "actual": actual})
            continue
        if state == "post" and relative in changes and expected["exists"]:
            data = target_path(world_root, relative).read_bytes()
            image = terrain_ota.RegionImage.parse(data, f"target::{relative}")
            selected = terrain_ota.selection_by_region()[tuple(int(v) for v in guard["region"])]
            outside = frozenset(set(range(1024)) - set(selected))
            if image.signature(selected) != guard["selected_post_signature"]:
                mismatches.append({"relative_path": relative, "reason": "selected-slot signature mismatch"})
            if image.signature(outside) != guard["outside_post_signature"]:
                mismatches.append({"relative_path": relative, "reason": "outside-slot signature mismatch"})
    return {
        "schema": SCHEMA_TARGET_VERIFY,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not mismatches else "BLOCKED",
        "state": state,
        "world_root": str(world_root),
        "checked_files": len(manifest["guard_files"]),
        "mismatches": mismatches,
        "world_modified": False,
    }


def require_world_write(allow: bool, stopped_ack: str | None) -> None:
    if not allow:
        raise EntityOtaError("world mutation refused: pass --allow-world-write explicitly")
    if stopped_ack != STOPPED_ACK:
        raise EntityOtaError(f"world mutation refused: --stopped-server-ack must equal {STOPPED_ACK}")


def paths_disjoint(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    try:
        left.relative_to(right)
        return False
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return False
    except ValueError:
        return True


def target_state(manifest: Mapping[str, Any], world_root: Path) -> str:
    pre_matches = 0
    post_matches = 0
    mismatches: list[str] = []
    for guard in manifest["guard_files"]:
        relative = str(guard["relative_path"])
        actual = file_identity_path(target_path(world_root, relative))
        pre = identity_equal(actual, guard["pre"])
        post = identity_equal(actual, guard["post"])
        pre_matches += int(pre)
        post_matches += int(post)
        if not pre and not post:
            mismatches.append(relative)
    total = len(manifest["guard_files"])
    if mismatches:
        raise EntityOtaError(f"target CAS mismatch for {len(mismatches)} files: {mismatches[:3]}")
    if pre_matches == total:
        return "pre"
    if post_matches == total:
        return "post"
    raise EntityOtaError("target is in a mixed pre/post entity state; no writes performed")


def apply_bundle(
    bundle_root: Path,
    world_root: Path,
    backup_root: Path,
    *,
    allow_world_write: bool,
    stopped_ack: str | None,
) -> dict[str, Any]:
    require_world_write(allow_world_write, stopped_ack)
    bundle_root = bundle_root.resolve()
    world_root = world_root.resolve()
    backup_root = backup_root.resolve()
    if not world_root.is_dir():
        raise EntityOtaError(f"target world root is missing: {world_root}")
    if backup_root.exists():
        raise EntityOtaError(f"backup root already exists: {backup_root}")
    if not paths_disjoint(world_root, backup_root) or not paths_disjoint(bundle_root, backup_root):
        raise EntityOtaError("backup root must be disjoint from world and bundle roots")
    manifest, _plan = read_bundle(bundle_root)
    state = target_state(manifest, world_root)
    if state == "post":
        verified = verify_target(bundle_root, world_root, "post")
        if verified["status"] != "PASS":
            raise EntityOtaError(f"postimage target failed verification: {verified['mismatches'][:3]}")
        return {
            "schema": SCHEMA_RECEIPT,
            "generated_at_utc": utc_now(),
            "status": "ALREADY_APPLIED_VERIFIED",
            "bundle_root": str(bundle_root),
            "world_root": str(world_root),
            "changes": len(manifest["changes"]),
            "postverify": verified,
        }
    preverify = verify_target(bundle_root, world_root, "pre")
    if preverify["status"] != "PASS":
        raise EntityOtaError(f"preimage CAS mismatch; no files written: {preverify['mismatches'][:3]}")
    backup_root.mkdir(parents=True)
    receipt_path = backup_root / "apply-receipt.json"
    entries: list[dict[str, Any]] = []
    for change in manifest["changes"]:
        relative = str(change["relative_path"])
        target = target_path(world_root, relative)
        backup_relative = f"preimage/{relative}" if change["pre"]["exists"] else None
        if backup_relative:
            backup = backup_root / Path(backup_relative)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            if not identity_equal(file_identity_path(backup), change["pre"]):
                raise EntityOtaError(f"transaction preimage verification failed: {relative}")
        entries.append(
            {
                "relative_path": relative,
                "pre": change["pre"],
                "post": change["post"],
                "backup_relative_path": backup_relative,
            }
        )
    receipt: dict[str, Any] = {
        "schema": SCHEMA_RECEIPT,
        "created_at_utc": utc_now(),
        "status": "PREPARED",
        "bundle_root": str(bundle_root),
        "bundle_manifest_sha256": sha256_file(bundle_root / "bundle.json"),
        "world_root": str(world_root),
        "backup_root": str(backup_root),
        "entries": entries,
        "applied_paths": [],
    }
    atomic_write_json(receipt_path, receipt)
    try:
        for change in manifest["changes"]:
            relative = str(change["relative_path"])
            target = target_path(world_root, relative)
            receipt["applied_paths"].append(relative)
            atomic_write_json(receipt_path, receipt)
            if change["post"]["exists"]:
                payload = bundle_root / Path(str(change["payload_relative_path"]))
                atomic_write_bytes(target, payload.read_bytes())
            elif target.exists():
                target.unlink()
            if not identity_equal(file_identity_path(target), change["post"]):
                raise EntityOtaError(f"postimage verification failed after write: {relative}")
        postverify = verify_target(bundle_root, world_root, "post")
        if postverify["status"] != "PASS":
            raise EntityOtaError(f"post-apply verification failed: {postverify['mismatches'][:3]}")
        receipt["status"] = "APPLIED_VERIFIED"
        receipt["completed_at_utc"] = utc_now()
        receipt["postverify"] = postverify
        atomic_write_json(receipt_path, receipt)
        return receipt
    except Exception as original:
        rollback_errors: list[str] = []
        for relative in reversed(receipt["applied_paths"]):
            entry = next(row for row in entries if row["relative_path"] == relative)
            target = target_path(world_root, relative)
            try:
                actual = file_identity_path(target)
                if identity_equal(actual, entry["pre"]):
                    continue
                if not identity_equal(actual, entry["post"]):
                    raise EntityOtaError("automatic rollback CAS mismatch")
                if entry["pre"]["exists"]:
                    backup = backup_root / Path(str(entry["backup_relative_path"]))
                    atomic_write_bytes(target, backup.read_bytes())
                elif target.exists():
                    target.unlink()
            except Exception as rollback_exc:  # pragma: no cover - catastrophic I/O
                rollback_errors.append(f"{relative}: {rollback_exc}")
        receipt["status"] = "AUTO_ROLLED_BACK" if not rollback_errors else "AUTO_ROLLBACK_FAILED"
        receipt["failure"] = f"{type(original).__name__}: {original}"
        receipt["rollback_errors"] = rollback_errors
        atomic_write_json(receipt_path, receipt)
        if rollback_errors:
            raise EntityOtaError(f"apply failed and automatic rollback was incomplete: {rollback_errors}") from original
        raise


def rollback_apply(
    receipt_path: Path,
    *,
    allow_world_write: bool,
    stopped_ack: str | None,
) -> dict[str, Any]:
    require_world_write(allow_world_write, stopped_ack)
    receipt_path = receipt_path.resolve()
    receipt = json_load(receipt_path)
    if receipt.get("schema") != SCHEMA_RECEIPT:
        raise EntityOtaError("apply receipt schema is invalid")
    if receipt.get("status") == "ROLLED_BACK_VERIFIED":
        return receipt
    if receipt.get("status") != "APPLIED_VERIFIED":
        raise EntityOtaError(f"receipt is not rollbackable: {receipt.get('status')}")
    bundle_root = Path(str(receipt["bundle_root"])).resolve()
    world_root = Path(str(receipt["world_root"])).resolve()
    backup_root = Path(str(receipt["backup_root"])).resolve()
    if sha256_file(bundle_root / "bundle.json") != receipt.get("bundle_manifest_sha256"):
        raise EntityOtaError("bundle manifest changed after apply")
    manifest, _plan = read_bundle(bundle_root)
    state = target_state(manifest, world_root)
    if state == "pre":
        result = {
            "schema": SCHEMA_RECEIPT,
            "generated_at_utc": utc_now(),
            "status": "ALREADY_ROLLED_BACK_VERIFIED",
            "world_root": str(world_root),
            "restored_entries": 0,
        }
        atomic_write_json(backup_root / "rollback-receipt.json", result)
        return result
    postverify = verify_target(bundle_root, world_root, "post")
    if postverify["status"] != "PASS":
        raise EntityOtaError(f"rollback refused because postimage was tampered: {postverify['mismatches'][:3]}")
    for entry in receipt["entries"]:
        relative = str(entry["relative_path"])
        if entry["pre"]["exists"]:
            backup = backup_root / Path(str(entry["backup_relative_path"]))
            if not identity_equal(file_identity_path(backup), entry["pre"]):
                raise EntityOtaError(f"rollback preimage is missing/tampered: {relative}")
    for entry in receipt["entries"]:
        relative = str(entry["relative_path"])
        target = target_path(world_root, relative)
        if entry["pre"]["exists"]:
            backup = backup_root / Path(str(entry["backup_relative_path"]))
            atomic_write_bytes(target, backup.read_bytes())
        elif target.exists():
            target.unlink()
    preverify = verify_target(bundle_root, world_root, "pre")
    if preverify["status"] != "PASS":  # pragma: no cover - catastrophic storage failure
        raise EntityOtaError(f"rollback writes completed but verification failed: {preverify['mismatches'][:3]}")
    result = {
        "schema": SCHEMA_RECEIPT,
        "generated_at_utc": utc_now(),
        "status": "ROLLED_BACK_VERIFIED",
        "world_root": str(world_root),
        "restored_entries": len(receipt["entries"]),
        "preverify": preverify,
    }
    atomic_write_json(backup_root / "rollback-receipt.json", result)
    return result


def print_result(value: Mapping[str, Any], output: Path | None = None) -> None:
    if output is not None:
        atomic_write_json(output.resolve(), value)
    keys = (
        "schema",
        "status",
        "bundle_root",
        "changes",
        "guard_files",
        "entities",
        "moved",
        "checked_files",
        "restored_entries",
    )
    print(json.dumps({key: value.get(key) for key in keys if key in value}, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan", help="read-only relocation and selected-slot reconstruction plan")
    plan.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    plan.add_argument("--current-world-prefix")
    plan.add_argument("--gate", type=Path, default=DEFAULT_GATE)
    plan.add_argument("--v-world", type=Path, default=DEFAULT_V_WORLD)
    plan.add_argument("--output", type=Path, required=True)

    build = commands.add_parser("build", help="write a detached entity OTA bundle")
    build.add_argument("--plan", type=Path, required=True)
    build.add_argument("--bundle-root", type=Path, required=True)
    build.add_argument("--output", type=Path)

    verify_bundle = commands.add_parser("verify-bundle", help="read-only detached bundle verification")
    verify_bundle.add_argument("--bundle-root", type=Path, required=True)
    verify_bundle.add_argument("--output", type=Path)

    verify_target_parser = commands.add_parser("verify-target", help="read-only target CAS verification")
    verify_target_parser.add_argument("--bundle-root", type=Path, required=True)
    verify_target_parser.add_argument("--world", type=Path, required=True)
    verify_target_parser.add_argument("--state", choices=("pre", "post"), required=True)
    verify_target_parser.add_argument("--output", type=Path)

    apply = commands.add_parser("apply", help="CAS apply to a stopped extracted world")
    apply.add_argument("--bundle-root", type=Path, required=True)
    apply.add_argument("--world", type=Path, required=True)
    apply.add_argument("--backup-root", type=Path, required=True)
    apply.add_argument("--allow-world-write", action="store_true")
    apply.add_argument("--stopped-server-ack")

    rollback = commands.add_parser("rollback", help="CAS rollback an applied transaction")
    rollback.add_argument("--apply-receipt", type=Path, required=True)
    rollback.add_argument("--allow-world-write", action="store_true")
    rollback.add_argument("--stopped-server-ack")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            with terrain_ota.open_source(args.current, args.current_world_prefix) as current:
                plan, _desired = create_plan(current, args.gate, args.v_world)
            print_result(plan, args.output)
        elif args.command == "build":
            print_result(build_bundle(args.plan, args.bundle_root), args.output)
        elif args.command == "verify-bundle":
            manifest, plan = read_bundle(args.bundle_root)
            result = {
                "schema": "protected-zone-entity-ota-bundle-verification/v1",
                "generated_at_utc": utc_now(),
                "status": "PASS",
                "bundle_root": str(args.bundle_root.resolve()),
                "changes": len(manifest["changes"]),
                "guard_files": len(manifest["guard_files"]),
                "entities": manifest["semantic_postconditions"]["post_entity_count"],
                "moved": plan["summary"]["moved"],
                "world_modified": False,
            }
            print_result(result, args.output)
        elif args.command == "verify-target":
            print_result(verify_target(args.bundle_root, args.world, args.state), args.output)
        elif args.command == "apply":
            print_result(
                apply_bundle(
                    args.bundle_root,
                    args.world,
                    args.backup_root,
                    allow_world_write=args.allow_world_write,
                    stopped_ack=args.stopped_server_ack,
                )
            )
        elif args.command == "rollback":
            print_result(
                rollback_apply(
                    args.apply_receipt,
                    allow_world_write=args.allow_world_write,
                    stopped_ack=args.stopped_server_ack,
                )
            )
        else:  # pragma: no cover
            raise EntityOtaError(f"unsupported command {args.command}")
        return 0
    except (EntityOtaError, terrain_ota.OtaError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
