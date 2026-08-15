from __future__ import annotations

"""Transactional object-level OTA repair for migrated Create storage contents.

This tool is deliberately narrower than a chunk transplant:

* it reads a hashed ledger of exact block-entity coordinates and typed NBT
  payloads extracted from the authoritative 1.21.11 world;
* it compare-and-sets only one audited content field in each live block entity;
* an entire multiblock group is skipped if any member is missing, has a
  different id/topology, has unknown content NBT, or is already non-empty;
* it snapshots every touched block entity and every touched live region file;
* it prepares same-volume temporary region files, performs a second preflight,
  atomically replaces each region, verifies postconditions, and writes an
  idempotent receipt;
* normal rollback is also compare-and-set and restores only the snapshotted
  content field.  Full-region backups exist solely for immediate recovery from
  an interrupted/failed apply, never as the routine rollback mechanism.

No Minecraft/Java process is launched and no client mod is required.  The
server must be stopped so ``session.lock`` can be acquired.
"""

import argparse
import base64
import contextlib
import copy
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
import tomllib
import zipfile
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable, Mapping, MutableMapping, Sequence

try:
    import nbtlib
except ImportError as exc:  # pragma: no cover
    raise SystemExit("nbtlib is required in the D: work environment") from exc


LEDGER_FORMAT = "create-storage-object-ota/v1"
RECEIPT_FORMAT = "create-storage-object-ota-receipt/v1"
SECTOR_BYTES = 4096
HEADER_BYTES = 8192
MAX_SECTORS_PER_CHUNK = 255
PACKAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REGION_NAME = re.compile(r"^r\.(-?[0-9]+)\.(-?[0-9]+)\.mca$")
MISSING = object()


class OtaError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def plain(value: Any) -> Any:
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, Mapping):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    return value


def safe_relative(value: str, *, suffix: str | None = None) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise OtaError("ledger path must be a non-empty string")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise OtaError(f"unsafe ledger path: {value!r}")
    if ":" in path.parts[0]:
        raise OtaError(f"drive-qualified ledger path is forbidden: {value!r}")
    if suffix is not None and path.suffix.lower() != suffix.lower():
        raise OtaError(f"ledger path must end in {suffix}: {value!r}")
    return path


def local_path(root: Path, relative: PurePosixPath) -> Path:
    return root.joinpath(*relative.parts)


def slot_for_chunk(chunk_x: int, chunk_z: int) -> int:
    return (chunk_x & 31) + (chunk_z & 31) * 32


def region_for_chunk(chunk_x: int, chunk_z: int) -> tuple[int, int]:
    return math.floor(chunk_x / 32), math.floor(chunk_z / 32)


def decompress_payload(kind: int, payload: bytes) -> bytes:
    compression = kind & 0x7F
    if kind & 0x80:
        raise OtaError("external .mcc storage chunks are not supported by the first OTA applicator")
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise OtaError(f"unsupported Anvil compression type {compression}")


def parse_nbt_file(raw: bytes, *, label: str) -> nbtlib.File:
    try:
        return nbtlib.File.parse(io.BytesIO(raw), byteorder="big")
    except Exception as exc:
        raise OtaError(f"cannot parse {label} NBT: {exc}") from exc


def serialize_nbt_file(value: nbtlib.File) -> bytes:
    output = io.BytesIO()
    value.write(output, byteorder="big")
    return output.getvalue()


def serialize_payload_tag(tag: Any) -> bytes:
    root = nbtlib.File({"Content": copy.deepcopy(tag)}, gzipped=False, byteorder="big", root_name="")
    return serialize_nbt_file(root)


def parse_payload(raw: bytes, *, label: str) -> Any:
    root = parse_nbt_file(raw, label=label)
    if "Content" not in root:
        raise OtaError(f"{label} payload root must contain Content")
    if set(root.keys()) != {"Content"}:
        raise OtaError(f"{label} payload root contains fields other than Content")
    return copy.deepcopy(root["Content"])


def content_hash(tag: Any) -> str:
    return sha256_bytes(serialize_payload_tag(tag))


def record_from_chunk(chunk: nbtlib.File) -> bytes:
    raw = serialize_nbt_file(chunk)
    compressed = zlib.compress(raw, level=6)
    return (len(compressed) + 1).to_bytes(4, "big") + b"\x02" + compressed


def validate_record(record: bytes) -> tuple[int, bytes]:
    if len(record) < 5:
        raise OtaError("chunk record is truncated")
    length = int.from_bytes(record[:4], "big")
    if length != len(record) - 4:
        raise OtaError(f"chunk record length mismatch: {length} != {len(record) - 4}")
    return record[4], decompress_payload(record[4], record[5:])


@dataclass
class ChunkImage:
    record: bytes
    chunk: nbtlib.File


def read_region_record(path: Path, slot: int) -> bytes | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(HEADER_BYTES)
            if len(header) < HEADER_BYTES:
                raise OtaError(f"region header is truncated: {path}")
            entry = header[slot * 4 : slot * 4 + 4]
            offset = int.from_bytes(entry[:3], "big")
            sectors = entry[3]
            if offset == 0:
                return None
            if offset < 2 or sectors == 0:
                raise OtaError(f"invalid region location at slot {slot}: {path}")
            handle.seek(offset * SECTOR_BYTES)
            length_bytes = handle.read(4)
            if len(length_bytes) != 4:
                raise OtaError(f"cannot read chunk length at slot {slot}: {path}")
            length = int.from_bytes(length_bytes, "big")
            if length < 1 or length + 4 > sectors * SECTOR_BYTES:
                raise OtaError(f"invalid chunk length {length} at slot {slot}: {path}")
            body = handle.read(length)
            if len(body) != length:
                raise OtaError(f"truncated chunk body at slot {slot}: {path}")
            record = length_bytes + body
            validate_record(record)
            return record
    except OSError as exc:
        raise OtaError(f"cannot read region {path}: {exc}") from exc


def read_chunk_image(path: Path, slot: int) -> ChunkImage | None:
    record = read_region_record(path, slot)
    if record is None:
        return None
    _, raw = validate_record(record)
    return ChunkImage(record, parse_nbt_file(raw, label=f"{path}:{slot}"))


def chunk_container(chunk: Mapping[str, Any]) -> Mapping[str, Any]:
    level = chunk.get("Level")
    return level if isinstance(level, Mapping) else chunk


def chunk_coordinates(chunk: Mapping[str, Any]) -> tuple[int | None, int | None]:
    container = chunk_container(chunk)
    x_pos = plain(container.get("xPos"))
    z_pos = plain(container.get("zPos"))
    return (int(x_pos) if isinstance(x_pos, int) else None, int(z_pos) if isinstance(z_pos, int) else None)


def block_entity_list(chunk: MutableMapping[str, Any]) -> Any:
    containers: list[MutableMapping[str, Any]] = [chunk]
    level = chunk.get("Level")
    if isinstance(level, MutableMapping):
        containers.append(level)
    for container in containers:
        for key in ("block_entities", "BlockEntities", "blockEntities", "TileEntities"):
            value = container.get(key)
            if isinstance(value, list):
                return value
    raise OtaError("chunk does not contain a recognized block-entity list")


def be_position(value: Mapping[str, Any]) -> tuple[int, int, int] | None:
    coordinates = tuple(plain(value.get(key)) for key in ("x", "y", "z"))
    if all(isinstance(item, int) for item in coordinates):
        return int(coordinates[0]), int(coordinates[1]), int(coordinates[2])
    return None


def find_block_entity(chunk: MutableMapping[str, Any], pos: tuple[int, int, int]) -> MutableMapping[str, Any] | None:
    for value in block_entity_list(chunk):
        if isinstance(value, MutableMapping) and be_position(value) == pos:
            return value
    return None


def normalized_block_state(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    name = plain(value.get("Name", value.get("name")))
    if not isinstance(name, str):
        return None
    properties_tag = value.get("Properties", value.get("properties", {}))
    if properties_tag is None:
        properties_tag = {}
    if not isinstance(properties_tag, Mapping):
        return None
    properties = {str(key): str(plain(child)) for key, child in properties_tag.items()}
    return {"Name": name, "Properties": dict(sorted(properties.items()))}


def block_state_at(chunk: Mapping[str, Any], pos: tuple[int, int, int]) -> dict[str, Any]:
    container = chunk_container(chunk)
    sections = container.get("sections", container.get("Sections"))
    if not isinstance(sections, list):
        raise OtaError("chunk has no recognized sections list")
    section_y = math.floor(pos[1] / 16)
    section: Mapping[str, Any] | None = None
    for candidate in sections:
        if isinstance(candidate, Mapping) and plain(candidate.get("Y")) == section_y:
            section = candidate
            break
    if section is None:
        raise OtaError(f"chunk has no section Y={section_y} for block {pos}")
    states = section.get("block_states", section.get("BlockStates"))
    if not isinstance(states, Mapping):
        raise OtaError(f"section Y={section_y} has no block_states compound")
    palette = states.get("palette", states.get("Palette"))
    if not isinstance(palette, list) or not palette:
        raise OtaError(f"section Y={section_y} has no block-state palette")
    local_x = pos[0] & 15
    local_y = pos[1] & 15
    local_z = pos[2] & 15
    block_index = (local_y << 8) | (local_z << 4) | local_x
    if len(palette) == 1:
        palette_index = 0
    else:
        bits = max(4, (len(palette) - 1).bit_length())
        data = states.get("data", states.get("Data"))
        if data is None:
            raise OtaError(f"section Y={section_y} palette needs packed data")
        longs = [int(plain(item)) & ((1 << 64) - 1) for item in data]
        values_per_long = 64 // bits
        padded_length = math.ceil(4096 / values_per_long)
        dense_length = math.ceil(4096 * bits / 64)
        mask = (1 << bits) - 1
        if len(longs) == padded_length:
            long_index = block_index // values_per_long
            shift = (block_index % values_per_long) * bits
            palette_index = (longs[long_index] >> shift) & mask
        elif len(longs) == dense_length:
            bit_index = block_index * bits
            long_index = bit_index // 64
            shift = bit_index % 64
            palette_index = (longs[long_index] >> shift) & mask
            if shift + bits > 64:
                if long_index + 1 >= len(longs):
                    raise OtaError("dense block-state value crosses a missing long boundary")
                palette_index |= (longs[long_index + 1] << (64 - shift)) & mask
        else:
            raise OtaError(
                f"section Y={section_y} block-state data length {len(longs)} is neither "
                f"padded {padded_length} nor dense {dense_length}"
            )
    if not 0 <= palette_index < len(palette):
        raise OtaError(f"block-state palette index {palette_index} is outside {len(palette)} entries")
    result = normalized_block_state(palette[palette_index])
    if result is None:
        raise OtaError(f"block-state palette entry {palette_index} is malformed")
    return result


def validate_expected_block_state(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    expected_name = expected.get("Name", expected.get("name"))
    if actual.get("Name") != expected_name:
        problems.append(f"block state Name: live={actual.get('Name')!r}, expected={expected_name!r}")
    expected_properties = expected.get("Properties", expected.get("properties", {}))
    if not isinstance(expected_properties, Mapping):
        problems.append("expected block-state Properties is not an object")
        return problems
    actual_properties = actual.get("Properties", {})
    for key, expected_value in expected_properties.items():
        live_value = actual_properties.get(str(key), MISSING)
        if live_value != str(expected_value):
            problems.append(
                f"block state property {key}: live={live_value!r}, expected={str(expected_value)!r}"
            )
    if expected.get("property_match") == "exact":
        normalized_expected = {str(key): str(value) for key, value in expected_properties.items()}
        if actual_properties != dict(sorted(normalized_expected.items())):
            problems.append(
                f"block state Properties exact mismatch: live={actual_properties!r}, expected={normalized_expected!r}"
            )
    return problems


PATH_SEGMENT = re.compile(r"^([^\[\]]+)((?:\[[0-9]+\])*)$")
PATH_INDEX = re.compile(r"\[([0-9]+)\]")


def dotted_tokens(path: str) -> list[str | int]:
    if not path:
        return []
    tokens: list[str | int] = []
    for segment in path.split("."):
        match = PATH_SEGMENT.fullmatch(segment)
        if match is None:
            raise OtaError(f"invalid content path: {path!r}")
        tokens.append(match.group(1))
        tokens.extend(int(value) for value in PATH_INDEX.findall(match.group(2)))
    return tokens


def dotted_get(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for token in dotted_tokens(path):
        if isinstance(token, str):
            if not isinstance(current, Mapping) or token not in current:
                return MISSING
            current = current[token]
        else:
            if not isinstance(current, list) or token >= len(current):
                return MISSING
            current = current[token]
    return current


def dotted_parent(value: MutableMapping[str, Any], path: str) -> tuple[Any, str | int]:
    tokens = dotted_tokens(path)
    if not tokens:
        raise OtaError(f"invalid content path: {path!r}")
    current: Any = value
    for token in tokens[:-1]:
        if isinstance(token, str):
            if not isinstance(current, MutableMapping):
                raise OtaError(f"content path parent is missing/not a compound: {path!r}")
            child = current.get(token)
        else:
            if not isinstance(current, list) or token >= len(current):
                raise OtaError(f"content path list index is missing/out of range: {path!r}")
            child = current[token]
        if not isinstance(child, (MutableMapping, list)):
            raise OtaError(f"content path parent is missing/not a container: {path!r}")
        current = child
    final = tokens[-1]
    if isinstance(final, str) and not isinstance(current, MutableMapping):
        raise OtaError(f"content path parent is not a compound: {path!r}")
    if isinstance(final, int) and (not isinstance(current, list) or final >= len(current)):
        raise OtaError(f"content path final list index is missing/out of range: {path!r}")
    return current, final


def item_handler_state(tag: Any) -> tuple[str, str | None]:
    if tag is MISSING:
        return "empty", None
    if not isinstance(tag, Mapping):
        return "unknown", "item handler content is not a compound"
    keys = set(str(key) for key in tag.keys())
    unknown = keys - {"Size", "Items"}
    if unknown:
        return "unknown", "item handler contains unknown fields: " + ", ".join(sorted(unknown))
    size = plain(tag.get("Size"))
    if size is not None and (not isinstance(size, int) or size < 0):
        return "unknown", f"item handler Size is invalid: {size!r}"
    items = tag.get("Items")
    if items is None:
        return "empty", None
    if not isinstance(items, list):
        return "unknown", "item handler Items is not a list"
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            return "unknown", f"item handler Items[{index}] is not a compound"
    return ("nonempty", None) if len(items) else ("empty", None)


def fluid_stack_state(tag: Any) -> tuple[str, str | None]:
    if tag is MISSING or tag is None:
        return "empty", None
    if not isinstance(tag, Mapping):
        return "unknown", "Fluid is not a compound"
    if not tag:
        return "empty", None
    identifier = plain(tag.get("id"))
    amount = plain(tag.get("amount"))
    if identifier is None and amount is None:
        return "empty", None
    if not isinstance(identifier, str):
        return "unknown", f"Fluid.id is invalid: {identifier!r}"
    if not isinstance(amount, int):
        return "unknown", f"Fluid.amount is invalid: {amount!r}"
    if amount <= 0 or identifier in {"", "minecraft:empty"}:
        return "empty", None
    return "nonempty", None


def fluid_tank_state(tag: Any) -> tuple[str, str | None]:
    if tag is MISSING:
        return "empty", None
    if not isinstance(tag, Mapping):
        return "unknown", "TankContent is not a compound"
    unknown = set(str(key) for key in tag.keys()) - {"Fluid"}
    if unknown:
        return "unknown", "TankContent contains unknown fields: " + ", ".join(sorted(unknown))
    return fluid_stack_state(tag.get("Fluid", MISSING))


def content_state(schema: str, tag: Any) -> tuple[str, str | None]:
    if schema == "neoforge_item_stack_handler":
        return item_handler_state(tag)
    if schema == "neoforge_fluid_tank":
        return fluid_tank_state(tag)
    if schema == "fluid_stack":
        return fluid_stack_state(tag)
    if schema == "empty_compound":
        if tag is MISSING:
            return "empty", None
        if isinstance(tag, Mapping):
            return ("empty", None) if not tag else ("nonempty", None)
        return "unknown", "content is not a compound"
    raise OtaError(f"unsupported content_schema {schema!r}")


def content_fluid_amount(schema: str, tag: Any) -> int | None:
    fluid = tag
    if schema == "neoforge_fluid_tank":
        if not isinstance(tag, Mapping):
            return None
        fluid = tag.get("Fluid")
    if schema not in {"neoforge_fluid_tank", "fluid_stack"} or not isinstance(fluid, Mapping):
        return None
    amount = plain(fluid.get("amount"))
    return int(amount) if isinstance(amount, int) and not isinstance(amount, bool) else None


def validate_target_capacity(member: "MemberSpec", payload: Any) -> str | None:
    if member.content_schema not in {"neoforge_fluid_tank", "fluid_stack"}:
        return None
    if member.target_max_capacity is None:
        return "fluid repair member is missing target_max_capacity"
    amount = content_fluid_amount(member.content_schema, payload)
    if amount is None:
        return "fluid payload has no integer amount"
    if amount > member.target_max_capacity:
        return f"fluid amount {amount} exceeds target_max_capacity {member.target_max_capacity}"
    return None


def legacy_dense_item_handler(tag: Any) -> tuple[Any | None, str | None]:
    if not isinstance(tag, list):
        return None, None
    if len(tag) > 20:
        return None, f"legacy dense vault list has {len(tag)} stacks, exceeding capacity 20"
    items: list[Any] = []
    for slot, source_item in enumerate(tag):
        if not isinstance(source_item, Mapping):
            return None, f"legacy dense vault Inventory[{slot}] is not a compound"
        if "Slot" in source_item:
            return None, f"legacy dense vault Inventory[{slot}] unexpectedly contains Slot"
        item = copy.deepcopy(source_item)
        item["Slot"] = nbtlib.Int(slot)
        items.append(item)
    target = nbtlib.Compound()
    target["Size"] = nbtlib.Int(20)
    target["Items"] = nbtlib.List[nbtlib.Compound](items)
    return target, None


def legacy_fluid_tank(block_entity: Mapping[str, Any], content_path: str) -> tuple[Any | None, tuple[str, ...], str | None]:
    target = dotted_get(block_entity, content_path)
    root_fluid = block_entity.get("Fluid", MISSING)
    if root_fluid is not MISSING:
        state, reason = fluid_stack_state(root_fluid)
        if state == "unknown":
            return None, (), f"legacy root Fluid is invalid: {reason}"
        if state == "nonempty":
            target_state, target_reason = fluid_tank_state(target)
            if target_state != "empty":
                return None, (), (
                    "both legacy root Fluid and target TankContent carry/obscure content: "
                    + (target_reason or target_state)
                )
            wrapped = nbtlib.Compound({"Fluid": copy.deepcopy(root_fluid)})
            return wrapped, ("Fluid",), None
    if isinstance(target, Mapping) and "id" in target and "amount" in target:
        state, reason = fluid_stack_state(target)
        if state == "unknown":
            return None, (), f"direct TankContent FluidStack is invalid: {reason}"
        if state == "nonempty":
            return nbtlib.Compound({"Fluid": copy.deepcopy(target)}), (), None
    return None, (), None


@dataclass(frozen=True)
class MemberDecision:
    action: str
    current_content: Any
    proposed_content: Any | None
    remove_paths: tuple[str, ...]
    reason: str | None


def decide_member(
    member: "MemberSpec",
    block_entity: Mapping[str, Any],
    authoritative_payload: Any | None,
) -> MemberDecision:
    current = dotted_get(block_entity, member.content_path)
    legacy: Any | None = None
    remove_paths: tuple[str, ...] = ()
    legacy_error: str | None = None
    if member.legacy_schema == "create_fly_dense_item_list":
        legacy, legacy_error = legacy_dense_item_handler(current)
    elif member.legacy_schema == "create_fly_root_or_direct_fluid":
        legacy, remove_paths, legacy_error = legacy_fluid_tank(block_entity, member.content_path)
    if legacy_error is not None:
        return MemberDecision("conflict", current, None, (), legacy_error)
    if legacy is not None:
        legacy_state, legacy_reason = content_state(member.content_schema, legacy)
        if legacy_state == "unknown":
            return MemberDecision("conflict", current, None, (), f"converted legacy content is invalid: {legacy_reason}")
        if legacy_state == "nonempty":
            capacity_problem = validate_target_capacity(member, legacy)
            if capacity_problem is not None:
                return MemberDecision("conflict", current, None, (), capacity_problem)
            if (
                member.expected_legacy_converted_sha256 is not None
                and content_hash(legacy) != member.expected_legacy_converted_sha256
            ):
                return MemberDecision(
                    "conflict",
                    current,
                    None,
                    (),
                    "legacy live content hash does not match the forensic CAS expectation",
                )
            # Preserve the exact current live payload.  This path is a schema
            # upgrade bound to the stopped world's preflight chunk hash; it is
            # intentionally not an overwrite from the authoritative source.
            return MemberDecision("convert_legacy", current, legacy, remove_paths, None)
        # An empty legacy encoding is semantically empty.  A source-nonempty
        # ledger entry may safely restore its authoritative target payload.
        if authoritative_payload is not None:
            return MemberDecision("restore_authoritative", current, authoritative_payload, remove_paths, None)
        return MemberDecision("verify_empty", current, None, remove_paths, None)

    state, reason = content_state(member.content_schema, current)
    if state == "unknown":
        return MemberDecision("conflict", current, None, (), f"unknown content: {reason}")
    if state == "nonempty":
        matches = authoritative_payload is not None and content_hash(current) == content_hash(authoritative_payload)
        return MemberDecision(
            "already_matches" if matches else "conflict",
            current,
            None,
            (),
            "live content already equals the authoritative payload" if matches else "live content is non-empty",
        )
    if authoritative_payload is None:
        return MemberDecision("verify_empty", current, None, (), None)
    capacity_problem = validate_target_capacity(member, authoritative_payload)
    if capacity_problem is not None:
        return MemberDecision("conflict", current, None, (), capacity_problem)
    return MemberDecision("restore_authoritative", current, authoritative_payload, (), None)


@dataclass(frozen=True)
class MemberSpec:
    dimension: str
    pos: tuple[int, int, int]
    block_entity_id: str
    region_path: PurePosixPath
    chunk_x: int
    chunk_z: int
    stable_fields: Mapping[str, Any]
    stable_absent: tuple[str, ...]
    expected_block_state: Mapping[str, Any]
    content_path: str
    content_schema: str
    legacy_schema: str | None
    target_max_capacity: int | None
    expected_legacy_converted_sha256: str | None
    payload_path: PurePosixPath | None
    payload_sha256: str | None

    @property
    def slot(self) -> int:
        return slot_for_chunk(self.chunk_x, self.chunk_z)

    @property
    def key(self) -> tuple[str, int, int, int]:
        return self.dimension, self.pos[0], self.pos[1], self.pos[2]


@dataclass(frozen=True)
class GroupSpec:
    group_id: str
    storage_kind: str
    source_nonempty: bool
    members: tuple[MemberSpec, ...]
    source_summary: Mapping[str, Any]
    relationship_sha256: str
    member_set_sha256: str


def member_relationship_record(member: MemberSpec) -> dict[str, Any]:
    """Return the canonical, non-content identity record for a member.

    The relationship signature deliberately contains block-state identity in
    addition to block-entity NBT.  A block-state palette is not represented in
    the block entity, so checking only ``stable_fields`` would allow a changed
    multiblock topology to pass CAS.  Keep this record deterministic and free
    of payload bytes so a ledger can be audited independently.
    """

    return {
        "dimension": member.dimension,
        "pos": list(member.pos),
        "block_entity_id": member.block_entity_id,
        "chunk": [member.chunk_x, member.chunk_z],
        "region_path": member.region_path.as_posix(),
        "expected_block_state": plain(member.expected_block_state),
        "stable_fields": plain(member.stable_fields),
        "stable_absent": sorted(member.stable_absent),
        "content_path": member.content_path,
        "content_schema": member.content_schema,
        "legacy_schema": member.legacy_schema,
        "target_max_capacity": member.target_max_capacity,
        "expected_legacy_converted_sha256": member.expected_legacy_converted_sha256,
    }


def relationship_payload(storage_kind: str, members: Sequence[MemberSpec]) -> dict[str, Any]:
    return {
        "storage_kind": storage_kind,
        "members": sorted(
            (member_relationship_record(member) for member in members),
            key=lambda item: (item["dimension"], tuple(item["pos"])),
        ),
    }


def relationship_sha256(storage_kind: str, members: Sequence[MemberSpec]) -> str:
    return sha256_bytes(canonical_json(relationship_payload(storage_kind, members)))


def member_set_sha256(members: Sequence[MemberSpec]) -> str:
    values = sorted(
        [(member.dimension, list(member.pos)) for member in members],
        key=lambda item: (item[0], tuple(item[1])),
    )
    return sha256_bytes(canonical_json({"members": values}))


class PackageReader:
    def __init__(self, path: Path):
        self.path = path
        self.archive: zipfile.ZipFile | None = None

    def __enter__(self) -> "PackageReader":
        if self.path.is_dir():
            return self
        if not self.path.is_file():
            raise OtaError(f"OTA package does not exist: {self.path}")
        try:
            self.archive = zipfile.ZipFile(self.path, "r")
        except zipfile.BadZipFile as exc:
            raise OtaError(f"OTA package is not a readable zip: {self.path}") from exc
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.archive is not None:
            self.archive.close()

    def read(self, relative: PurePosixPath | str) -> bytes:
        path = safe_relative(str(relative))
        if self.archive is not None:
            try:
                return self.archive.read(path.as_posix())
            except KeyError as exc:
                raise OtaError(f"package is missing {path}") from exc
        try:
            return local_path(self.path, path).read_bytes()
        except OSError as exc:
            raise OtaError(f"package cannot read {path}: {exc}") from exc


@dataclass(frozen=True)
class LoadedPackage:
    ledger: Mapping[str, Any]
    ledger_digest: str
    groups: tuple[GroupSpec, ...]
    payloads: Mapping[tuple[str, int, int, int], Any]


def normalize_member(value: Any) -> MemberSpec:
    if not isinstance(value, Mapping):
        raise OtaError("group member must be an object")
    dimension = value.get("dimension")
    position = value.get("pos")
    identifier = value.get("block_entity_id", value.get("id"))
    chunk = value.get("chunk")
    if not isinstance(dimension, str) or ":" not in dimension:
        raise OtaError("member dimension must be namespaced")
    if not isinstance(position, list) or len(position) != 3 or not all(isinstance(item, int) for item in position):
        raise OtaError("member pos must be [x,y,z] integers")
    if not isinstance(identifier, str) or ":" not in identifier:
        raise OtaError("member block_entity_id must be namespaced")
    if chunk is None:
        chunk = [math.floor(position[0] / 16), math.floor(position[2] / 16)]
    if not isinstance(chunk, list) or len(chunk) != 2 or not all(isinstance(item, int) for item in chunk):
        raise OtaError("member chunk must be [x,z] integers")
    chunk_x, chunk_z = int(chunk[0]), int(chunk[1])
    if chunk_x != math.floor(position[0] / 16) or chunk_z != math.floor(position[2] / 16):
        raise OtaError(f"member chunk does not contain position {position}")
    region_path = safe_relative(value.get("region_path"), suffix=".mca")
    match = REGION_NAME.fullmatch(region_path.name)
    expected_region = region_for_chunk(chunk_x, chunk_z)
    if match is None or (int(match.group(1)), int(match.group(2))) != expected_region:
        raise OtaError(f"member region_path does not match chunk {chunk_x},{chunk_z}")
    stable_fields = value.get("stable_fields", {})
    stable_absent = value.get("stable_absent", [])
    if not isinstance(stable_fields, Mapping):
        raise OtaError("member stable_fields must be an object")
    if not isinstance(stable_absent, list) or not all(isinstance(item, str) and item for item in stable_absent):
        raise OtaError("member stable_absent must be a string list")
    expected_block_state = value.get("expected_block_state", value.get("block_state"))
    if not isinstance(expected_block_state, Mapping):
        raise OtaError("member expected_block_state is required")
    expected_name = expected_block_state.get("Name", expected_block_state.get("name"))
    if not isinstance(expected_name, str) or ":" not in expected_name:
        raise OtaError("member expected_block_state needs a namespaced Name")
    expected_properties = expected_block_state.get("Properties", expected_block_state.get("properties", {}))
    if not isinstance(expected_properties, Mapping):
        raise OtaError("member expected_block_state Properties must be an object")
    normalized_expected_state = {
        "Name": expected_name,
        "Properties": {str(key): str(child) for key, child in expected_properties.items()},
        "property_match": expected_block_state.get("property_match", "subset"),
    }
    if normalized_expected_state["property_match"] not in {"subset", "exact"}:
        raise OtaError("expected_block_state property_match must be subset or exact")
    content_path = value.get("content_path")
    content_schema = value.get("content_schema")
    if not isinstance(content_path, str) or not content_path:
        raise OtaError("member content_path is required")
    if content_schema not in {
        "neoforge_item_stack_handler",
        "neoforge_fluid_tank",
        "fluid_stack",
        "empty_compound",
    }:
        raise OtaError(f"unsupported member content_schema {content_schema!r}")
    legacy_schema = value.get("legacy_schema")
    if legacy_schema is None:
        if identifier == "create:item_vault" and content_schema == "neoforge_item_stack_handler":
            legacy_schema = "create_fly_dense_item_list"
        elif identifier == "create:fluid_tank" and content_schema == "neoforge_fluid_tank":
            legacy_schema = "create_fly_root_or_direct_fluid"
    if legacy_schema not in {None, "create_fly_dense_item_list", "create_fly_root_or_direct_fluid"}:
        raise OtaError(f"unsupported legacy_schema {legacy_schema!r}")
    target_max_capacity = value.get("target_max_capacity")
    if target_max_capacity is not None and (
        not isinstance(target_max_capacity, int) or isinstance(target_max_capacity, bool) or target_max_capacity <= 0
    ):
        raise OtaError("target_max_capacity must be a positive integer")
    expected_legacy_converted_sha256 = value.get("expected_legacy_converted_sha256")
    if expected_legacy_converted_sha256 is not None and (
        not isinstance(expected_legacy_converted_sha256, str)
        or SHA256.fullmatch(expected_legacy_converted_sha256) is None
    ):
        raise OtaError("expected_legacy_converted_sha256 must be lowercase SHA-256")
    payload_value = value.get("payload")
    payload_hash = value.get("payload_sha256")
    payload_path: PurePosixPath | None = None
    if payload_value is not None:
        payload_path = safe_relative(payload_value, suffix=".nbt")
        if not isinstance(payload_hash, str) or SHA256.fullmatch(payload_hash) is None:
            raise OtaError("repair member payload_sha256 must be lowercase SHA-256")
    elif payload_hash is not None:
        raise OtaError("payload_sha256 is present without payload")
    return MemberSpec(
        dimension,
        (int(position[0]), int(position[1]), int(position[2])),
        identifier,
        region_path,
        chunk_x,
        chunk_z,
        dict(stable_fields),
        tuple(stable_absent),
        normalized_expected_state,
        content_path,
        content_schema,
        legacy_schema,
        target_max_capacity,
        expected_legacy_converted_sha256,
        payload_path,
        payload_hash,
    )


def load_package(path: Path) -> LoadedPackage:
    with PackageReader(path) as reader:
        raw_ledger = reader.read("ledger.json")
        digest_text = reader.read("ledger.sha256").decode("ascii", "strict").strip().lower()
        if SHA256.fullmatch(digest_text) is None:
            raise OtaError("ledger.sha256 is invalid")
        digest = sha256_bytes(raw_ledger)
        if digest != digest_text:
            raise OtaError(f"ledger hash mismatch: expected {digest_text}, got {digest}")
        try:
            ledger = json.loads(raw_ledger.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OtaError(f"ledger.json is invalid: {exc}") from exc
        if not isinstance(ledger, dict) or ledger.get("format") != LEDGER_FORMAT:
            raise OtaError(f"ledger format must be {LEDGER_FORMAT}")
        package_id = ledger.get("package_id")
        if not isinstance(package_id, str) or PACKAGE_ID.fullmatch(package_id) is None:
            raise OtaError("ledger package_id is invalid")
        raw_groups = ledger.get("groups")
        if not isinstance(raw_groups, list) or not raw_groups:
            raise OtaError("ledger groups must be a non-empty list")
        groups: list[GroupSpec] = []
        group_ids: set[str] = set()
        member_keys: set[tuple[str, int, int, int]] = set()
        payloads: dict[tuple[str, int, int, int], Any] = {}
        for raw_group in raw_groups:
            if not isinstance(raw_group, Mapping):
                raise OtaError("ledger group must be an object")
            group_id = raw_group.get("group_id", raw_group.get("key"))
            storage_kind = raw_group.get("storage_kind")
            source_nonempty = raw_group.get("source_nonempty")
            if not isinstance(group_id, str) or not group_id or group_id in group_ids:
                raise OtaError(f"duplicate/invalid group_id: {group_id!r}")
            group_ids.add(group_id)
            if not isinstance(storage_kind, str) or not storage_kind:
                raise OtaError(f"group {group_id} storage_kind is invalid")
            if source_nonempty is not True:
                raise OtaError(f"group {group_id} is not explicitly source_nonempty=true")
            raw_members = raw_group.get("members", raw_group.get("group_members"))
            if not isinstance(raw_members, list) or not raw_members:
                raise OtaError(f"group {group_id} has no members")
            members = tuple(normalize_member(member) for member in raw_members)
            if not any(member.payload_path is not None for member in members):
                raise OtaError(f"group {group_id} has no source content payload")
            computed_relationship = relationship_sha256(storage_kind, members)
            declared_relationship = raw_group.get(
                "relationship_sha256",
                raw_group.get("relationship_hash", raw_group.get("group_relationship_sha256")),
            )
            if not isinstance(declared_relationship, str) or SHA256.fullmatch(declared_relationship) is None:
                raise OtaError(
                    f"group {group_id} must declare relationship_sha256; "
                    "re-finalize the ledger after adding block-state identity"
                )
            if declared_relationship != computed_relationship:
                raise OtaError(
                    f"group {group_id} relationship hash mismatch: "
                    f"declared {declared_relationship}, computed {computed_relationship}"
                )
            computed_member_set = member_set_sha256(members)
            declared_member_set = raw_group.get("member_set_sha256")
            if declared_member_set is not None:
                if not isinstance(declared_member_set, str) or SHA256.fullmatch(declared_member_set) is None:
                    raise OtaError(f"group {group_id} member_set_sha256 is invalid")
                if declared_member_set != computed_member_set:
                    raise OtaError(
                        f"group {group_id} member_set_sha256 mismatch: "
                        f"declared {declared_member_set}, computed {computed_member_set}"
                    )
            for member in members:
                if member.key in member_keys:
                    raise OtaError(f"block entity appears in multiple groups: {member.key}")
                member_keys.add(member.key)
                if member.payload_path is None:
                    continue
                raw_payload = reader.read(member.payload_path)
                if sha256_bytes(raw_payload) != member.payload_sha256:
                    raise OtaError(f"payload hash mismatch for {group_id} member {member.pos}")
                payload = parse_payload(raw_payload, label=f"{group_id}:{member.pos}")
                state, reason = content_state(member.content_schema, payload)
                if state != "nonempty":
                    raise OtaError(
                        f"source payload for {group_id} member {member.pos} is {state}: {reason or 'empty'}"
                    )
                capacity_problem = validate_target_capacity(member, payload)
                if capacity_problem is not None:
                    raise OtaError(f"source payload for {group_id} member {member.pos}: {capacity_problem}")
                payloads[member.key] = payload
            groups.append(
                GroupSpec(
                    group_id,
                    storage_kind,
                    True,
                    members,
                    dict(raw_group.get("source_summary", {})),
                    declared_relationship,
                    computed_member_set,
                )
            )
        return LoadedPackage(ledger, digest, tuple(groups), payloads)


def parse_level_dat(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise OtaError(f"level.dat is missing: {path}")
    try:
        root = plain(nbtlib.load(path))
    except Exception as exc:
        raise OtaError(f"cannot parse {path}: {exc}") from exc
    data = root.get("Data", root) if isinstance(root, dict) else {}
    worldgen = data.get("WorldGenSettings", {}) if isinstance(data, dict) else {}
    result: dict[str, Any] = {
        "level_name": data.get("LevelName") if isinstance(data, dict) else None,
        "data_version": root.get("DataVersion") if isinstance(root, dict) else None,
        "seed": worldgen.get("seed") if isinstance(worldgen, dict) else None,
    }
    if result["data_version"] is None and isinstance(data, dict):
        result["data_version"] = data.get("DataVersion")
    if isinstance(data, dict):
        for key in ("WorldUUIDMost", "WorldUUIDLeast"):
            if key in data:
                result[key] = data[key]
    return result


def validate_world_identity(world: Path, expected: Any) -> dict[str, Any]:
    if not isinstance(expected, Mapping) or not expected:
        raise OtaError("ledger world_identity must be a non-empty object")
    actual = parse_level_dat(world / "level.dat")
    mismatches: list[str] = []
    for key, expected_value in expected.items():
        if expected_value is None:
            continue
        if actual.get(key, MISSING) != expected_value:
            mismatches.append(f"{key}: live={actual.get(key, MISSING)!r}, expected={expected_value!r}")
    if mismatches:
        raise OtaError("world identity mismatch: " + "; ".join(mismatches))
    return actual


def validate_create_server_config(
    server_root: Path,
    package_or_receipt: Mapping[str, Any],
    *,
    has_item_vaults: bool,
) -> dict[str, Any]:
    config_path = server_root / "config" / "create-server.toml"
    if not config_path.is_file():
        raise OtaError(f"Create server config is missing: {config_path}")
    try:
        with config_path.open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise OtaError(f"cannot parse {config_path}: {exc}") from exc
    logistics = config.get("logistics", {})
    fluids = config.get("fluids", {})
    actual = {
        "logistics.vaultCapacity": logistics.get("vaultCapacity") if isinstance(logistics, Mapping) else None,
        "fluids.fluidTankCapacity": fluids.get("fluidTankCapacity") if isinstance(fluids, Mapping) else None,
    }
    required = package_or_receipt.get("server_config_requirements", {})
    if not isinstance(required, Mapping):
        raise OtaError("server_config_requirements must be an object")
    requirements = dict(required)
    if has_item_vaults:
        requirements.setdefault("logistics.vaultCapacity", 20)
    mismatches = []
    for key, expected in requirements.items():
        if key not in actual:
            raise OtaError(f"unsupported server config requirement: {key}")
        if actual[key] != expected:
            mismatches.append(f"{key}: live={actual[key]!r}, required={expected!r}")
    if mismatches:
        raise OtaError("Create server config mismatch: " + "; ".join(mismatches))
    return {"path": str(config_path), "values": actual, "requirements": requirements}


@contextlib.contextmanager
def world_lock_probe(world: Path, *, allow_missing: bool = False):
    lock_path = world / "session.lock"
    if not lock_path.exists():
        if allow_missing:
            yield None
            return
        raise OtaError(f"session.lock is missing: {lock_path}")
    handle: BinaryIO | None = None
    try:
        handle = lock_path.open("r+b")
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise OtaError("world is locked; stop the server before OTA") from exc
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise OtaError("world is locked; stop the server before OTA") from exc
        yield handle
    finally:
        if handle is not None:
            with contextlib.suppress(OSError):
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def region_allocations(data: bytes) -> tuple[list[tuple[int, int]], list[bool]]:
    if len(data) < HEADER_BYTES:
        raise OtaError("region file is shorter than the header")
    sector_count = max(2, math.ceil(len(data) / SECTOR_BYTES))
    used = [False] * sector_count
    used[0] = used[1] = True
    allocations = [(0, 0)] * 1024
    for slot in range(1024):
        entry = data[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        count = entry[3]
        allocations[slot] = (offset, count)
        if offset == 0:
            if count:
                raise OtaError(f"slot {slot} has sectors without an offset")
            continue
        if offset < 2 or count == 0 or offset + count > sector_count:
            raise OtaError(f"slot {slot} allocation is invalid: {offset}+{count}")
        for sector in range(offset, offset + count):
            if used[sector]:
                raise OtaError(f"region sector {sector} is referenced more than once")
            used[sector] = True
    return allocations, used


def find_free_run(used: list[bool], count: int) -> int:
    start = 2
    length = 0
    for index in range(2, len(used)):
        if used[index]:
            start = index + 1
            length = 0
        else:
            if length == 0:
                start = index
            length += 1
            if length >= count:
                return start
    start = len(used)
    used.extend([False] * count)
    return start


def patch_region_bytes(original: bytes, replacements: Mapping[int, bytes]) -> bytes:
    data = bytearray(original)
    allocations, used = region_allocations(original)
    for slot in replacements:
        old_offset, old_count = allocations[slot]
        if old_offset:
            for sector in range(old_offset, old_offset + old_count):
                used[sector] = False
    timestamp = int(time.time())
    for slot in sorted(replacements):
        record = replacements[slot]
        validate_record(record)
        needed = math.ceil(len(record) / SECTOR_BYTES)
        if needed < 1 or needed > MAX_SECTORS_PER_CHUNK:
            raise OtaError(f"updated live chunk at slot {slot} needs {needed} sectors")
        offset = find_free_run(used, needed)
        for sector in range(offset, offset + needed):
            used[sector] = True
        end = (offset + needed) * SECTOR_BYTES
        if len(data) < end:
            data.extend(b"\x00" * (end - len(data)))
        begin = offset * SECTOR_BYTES
        data[begin : begin + len(record)] = record
        data[begin + len(record) : end] = b"\x00" * (end - begin - len(record))
        data[slot * 4 : slot * 4 + 4] = offset.to_bytes(3, "big") + bytes([needed])
        stamp = SECTOR_BYTES + slot * 4
        data[stamp : stamp + 4] = timestamp.to_bytes(4, "big")
    return bytes(data)


def write_fsync(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def prepare_region(path: Path, replacements: Mapping[int, bytes], suffix: str) -> Path:
    original = path.read_bytes()
    patched = patch_region_bytes(original, replacements)
    temp = path.with_name(path.name + suffix)
    if temp.exists():
        raise OtaError(f"stale OTA temporary file exists: {temp}")
    write_fsync(temp, patched)
    for slot, expected in replacements.items():
        actual = read_region_record(temp, slot)
        if actual is None or sha256_bytes(actual) != sha256_bytes(expected):
            with contextlib.suppress(FileNotFoundError):
                temp.unlink()
            raise OtaError(f"prepared region verification failed: {path}:{slot}")
    return temp


def atomic_restore_file(source: Path, target: Path) -> None:
    with tempfile.NamedTemporaryFile(prefix=target.name + ".restore-", suffix=".tmp", dir=target.parent, delete=False) as handle:
        temp = Path(handle.name)
    try:
        shutil.copy2(source, temp)
        os.replace(temp, target)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()


@dataclass
class LiveMember:
    spec: MemberSpec
    region: Path
    chunk_key: tuple[Path, int]
    block_entity: MutableMapping[str, Any]
    content: Any
    content_status: str
    content_reason: str | None
    action: str
    proposed_content: Any | None
    remove_paths: tuple[str, ...]


@dataclass
class Preflight:
    eligible: list[GroupSpec]
    conflicts: list[dict[str, Any]]
    chunks: dict[tuple[Path, int], ChunkImage]
    members: dict[tuple[str, int, int, int], LiveMember]
    chunk_hashes: dict[tuple[Path, int], str]


def validate_stable_fields(member: MemberSpec, block_entity: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    for path, expected in member.stable_fields.items():
        actual_tag = dotted_get(block_entity, path)
        actual = MISSING if actual_tag is MISSING else plain(actual_tag)
        if actual != expected:
            problems.append(f"stable field {path}: live={actual!r}, expected={expected!r}")
    for path in member.stable_absent:
        if dotted_get(block_entity, path) is not MISSING:
            problems.append(f"stable field {path} must be absent")
    return problems


def preflight(world: Path, package: LoadedPackage) -> Preflight:
    chunks: dict[tuple[Path, int], ChunkImage] = {}
    members: dict[tuple[str, int, int, int], LiveMember] = {}
    chunk_hashes: dict[tuple[Path, int], str] = {}
    eligible: list[GroupSpec] = []
    conflicts: list[dict[str, Any]] = []
    for group in package.groups:
        reasons: list[dict[str, Any]] = []
        group_members: list[LiveMember] = []
        # The signature is checked again at execution time (not just while
        # loading the package) so a hand-edited in-memory ledger cannot weaken
        # the group lock.  This also documents exactly which identity is being
        # compared for a multiblock group.
        if relationship_sha256(group.storage_kind, group.members) != group.relationship_sha256:
            conflicts.append(
                {
                    "group_id": group.group_id,
                    "storage_kind": group.storage_kind,
                    "action": "skip",
                    "reasons": [{"reason": "ledger relationship signature is invalid"}],
                    "source_summary": group.source_summary,
                }
            )
            continue
        for spec in group.members:
            region = local_path(world, spec.region_path)
            chunk_key = (region, spec.slot)
            if not region.is_file():
                reasons.append({"member": list(spec.pos), "reason": f"region missing: {region}"})
                continue
            if chunk_key not in chunks:
                image = read_chunk_image(region, spec.slot)
                if image is None:
                    reasons.append({"member": list(spec.pos), "reason": "live chunk is absent"})
                    continue
                coords = chunk_coordinates(image.chunk)
                if coords != (spec.chunk_x, spec.chunk_z):
                    reasons.append(
                        {"member": list(spec.pos), "reason": f"chunk NBT coordinates are {coords}"}
                    )
                    continue
                chunks[chunk_key] = image
                chunk_hashes[chunk_key] = sha256_bytes(image.record)
            image = chunks.get(chunk_key)
            if image is None:
                continue
            block_entity = find_block_entity(image.chunk, spec.pos)
            if block_entity is None:
                reasons.append({"member": list(spec.pos), "reason": "block entity is missing"})
                continue
            actual_id = plain(block_entity.get("id"))
            if actual_id != spec.block_entity_id:
                reasons.append(
                    {
                        "member": list(spec.pos),
                        "reason": f"block entity id is {actual_id!r}, expected {spec.block_entity_id!r}",
                    }
                )
                continue
            stable_problems = validate_stable_fields(spec, block_entity)
            if stable_problems:
                reasons.extend({"member": list(spec.pos), "reason": reason} for reason in stable_problems)
                continue
            try:
                actual_block_state = block_state_at(image.chunk, spec.pos)
            except OtaError as exc:
                reasons.append({"member": list(spec.pos), "reason": f"block-state decode failed: {exc}"})
                continue
            state_problems = validate_expected_block_state(spec.expected_block_state, actual_block_state)
            if state_problems:
                reasons.extend(
                    {"member": list(spec.pos), "reason": reason} for reason in state_problems
                )
                continue
            authoritative = package.payloads.get(spec.key)
            decision = decide_member(spec, block_entity, authoritative)
            status, reason = content_state(spec.content_schema, decision.current_content)
            if decision.action == "convert_legacy":
                status, reason = "legacy_nonempty", None
            live = LiveMember(
                spec,
                region,
                chunk_key,
                block_entity,
                decision.current_content,
                status,
                reason,
                decision.action,
                decision.proposed_content,
                decision.remove_paths,
            )
            group_members.append(live)
            members[spec.key] = live
            if decision.action in {"conflict", "already_matches"}:
                reasons.append(
                    {
                        "member": list(spec.pos),
                        "reason": decision.reason,
                        "content_status": status,
                        "action": decision.action,
                    }
                )
        if len(group_members) != len(group.members) and not reasons:
            reasons.append({"reason": "not every ledger member was resolved"})
        if reasons:
            conflicts.append(
                {
                    "group_id": group.group_id,
                    "storage_kind": group.storage_kind,
                    "action": "skip",
                    "reasons": reasons,
                    "source_summary": group.source_summary,
                }
            )
        else:
            eligible.append(group)
    return Preflight(eligible, conflicts, chunks, members, chunk_hashes)


def receipt_location(world: Path, package: LoadedPackage) -> Path:
    package_id = package.ledger["package_id"]
    return world / ".create-storage-ota" / "receipts" / f"{package_id}-{package.ledger_digest[:16]}.json"


def report_output(path: Path | None, value: Mapping[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path is None:
        print(encoded, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
        print(path)


def require_confirmation(value: str | None, digest: str, flag: str = "--confirm") -> None:
    expected = digest[:16]
    if value != expected:
        raise OtaError(f"{flag} must equal ledger digest prefix {expected}")


def snapshot_block_entity(path: Path, block_entity: Mapping[str, Any]) -> str:
    root = nbtlib.File({"BlockEntity": copy.deepcopy(block_entity)}, gzipped=False, byteorder="big", root_name="")
    raw = serialize_nbt_file(root)
    write_fsync(path, raw)
    return sha256_bytes(raw)


def _remove_dotted(block_entity: MutableMapping[str, Any], path: str) -> None:
    parent, key = dotted_parent(block_entity, path)
    if isinstance(parent, MutableMapping) and isinstance(key, str):
        parent.pop(key, None)
        return
    raise OtaError(f"refusing to remove a list element from content path: {path!r}")


def apply_payload(
    block_entity: MutableMapping[str, Any],
    member: MemberSpec,
    payload: Any,
    remove_paths: Sequence[str] = (),
) -> None:
    parent, key = dotted_parent(block_entity, member.content_path)
    parent[key] = copy.deepcopy(payload)
    for path in remove_paths:
        if path == member.content_path:
            raise OtaError(f"remove path equals content path for {member.key}: {path}")
        _remove_dotted(block_entity, path)


def restore_snapshot_content(block_entity: MutableMapping[str, Any], member: MemberSpec, snapshot: Mapping[str, Any]) -> None:
    snapshot_content = dotted_get(snapshot, member.content_path)
    parent, key = dotted_parent(block_entity, member.content_path)
    if snapshot_content is MISSING:
        if isinstance(parent, MutableMapping) and isinstance(key, str):
            parent.pop(key, None)
        else:
            raise OtaError(f"refusing to remove a list element from content path: {member.content_path!r}")
    else:
        parent[key] = copy.deepcopy(snapshot_content)


def restore_snapshot_fields(
    block_entity: MutableMapping[str, Any],
    member: MemberSpec,
    snapshot: Mapping[str, Any],
    remove_paths: Sequence[str],
) -> None:
    """Restore content and every legacy path removed by the OTA transaction.

    The whole BE snapshot is retained, but rollback still writes only the
    audited paths.  This is what keeps unrelated live edits intact while
    restoring a root ``Fluid`` field removed during schema conversion.
    """

    restore_snapshot_content(block_entity, member, snapshot)
    for path in remove_paths:
        value = dotted_get(snapshot, path)
        if value is MISSING:
            _remove_dotted(block_entity, path)
        else:
            parent, key = dotted_parent(block_entity, path)
            parent[key] = copy.deepcopy(value)


def finalize_command(args: argparse.Namespace) -> int:
    draft = json.loads(args.draft.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise OtaError("draft ledger must be an object")
    draft["format"] = LEDGER_FORMAT
    package_id = draft.get("package_id")
    if not isinstance(package_id, str) or PACKAGE_ID.fullmatch(package_id) is None:
        raise OtaError("draft package_id is invalid")
    if args.output.exists():
        raise OtaError(f"output already exists: {args.output}")
    groups = draft.get("groups")
    if not isinstance(groups, list):
        raise OtaError("draft groups must be a list")
    for group in groups:
        members = group.get("members", group.get("group_members", []))
        for member in members:
            embedded = member.pop("payload_nbt_base64", None)
            if embedded is None:
                continue
            raw = base64.b64decode(embedded, validate=True)
            parse_payload(raw, label=f"draft:{group.get('group_id')}:{member.get('pos')}")
            digest = sha256_bytes(raw)
            relative = PurePosixPath("payloads") / f"{digest}.nbt"
            member["payload"] = relative.as_posix()
            member["payload_sha256"] = digest
            member.setdefault("_embedded_payload_bytes", raw)
    staging = Path(tempfile.mkdtemp(prefix="create-storage-object-ota-", dir=args.temp_root))
    try:
        for group in groups:
            members = group.get("members", group.get("group_members", []))
            for member in members:
                raw = member.pop("_embedded_payload_bytes", None)
                if raw is None:
                    source = member.get("payload")
                    if source is None:
                        continue
                    source_path = local_path(args.payload_root, safe_relative(source, suffix=".nbt"))
                    raw = source_path.read_bytes()
                    member["payload_sha256"] = sha256_bytes(raw)
                destination = local_path(staging, safe_relative(member["payload"], suffix=".nbt"))
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
        # Normalize and sign the multiblock relationship after payload paths
        # and hashes have been materialized.  A draft may provide a signature
        # from an independent forensic scanner; accepting it only when it
        # equals our canonical identity prevents a stale/BE-only signature from
        # bypassing block-state validation.
        for group in groups:
            members_raw = group.get("members", group.get("group_members", []))
            if not isinstance(members_raw, list) or not members_raw:
                raise OtaError(f"group {group.get('group_id', group.get('key'))!r} has no members")
            storage_kind = group.get("storage_kind")
            if not isinstance(storage_kind, str) or not storage_kind:
                raise OtaError("draft group storage_kind is required")
            normalized_members = tuple(normalize_member(member) for member in members_raw)
            computed_relationship = relationship_sha256(storage_kind, normalized_members)
            declared_relationship = group.get(
                "relationship_sha256",
                group.get("relationship_hash", group.get("group_relationship_sha256")),
            )
            if declared_relationship is not None and declared_relationship != computed_relationship:
                raise OtaError(
                    f"draft group {group.get('group_id', group.get('key'))!r} relationship hash mismatch: "
                    f"declared {declared_relationship}, computed {computed_relationship}"
                )
            group["relationship_sha256"] = computed_relationship
            group["member_set_sha256"] = member_set_sha256(normalized_members)
        raw_ledger = canonical_json(draft)
        (staging / "ledger.json").write_bytes(raw_ledger)
        (staging / "ledger.sha256").write_text(sha256_bytes(raw_ledger) + "\n", encoding="ascii")
        if args.output.suffix.lower() == ".zip":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(args.output, "x") as archive:
                for path in sorted(staging.rglob("*"), key=lambda item: item.relative_to(staging).as_posix()):
                    if not path.is_file():
                        continue
                    info = zipfile.ZipInfo(path.relative_to(staging).as_posix(), (1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_STORED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, path.read_bytes())
        else:
            shutil.copytree(staging, args.output)
        loaded = load_package(args.output)
        report_output(
            args.report,
            {
                "status": "finalized",
                "package": str(args.output),
                "package_id": package_id,
                "ledger_sha256": loaded.ledger_digest,
                "confirmation": loaded.ledger_digest[:16],
                "groups": len(loaded.groups),
                "members": sum(len(group.members) for group in loaded.groups),
                "repair_members": len(loaded.payloads),
            },
        )
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def verify_command(args: argparse.Namespace) -> int:
    package = load_package(args.package)
    report_output(
        args.report,
        {
            "status": "verified",
            "package_id": package.ledger["package_id"],
            "ledger_sha256": package.ledger_digest,
            "confirmation": package.ledger_digest[:16],
            "groups": len(package.groups),
            "members": sum(len(group.members) for group in package.groups),
            "repair_members": len(package.payloads),
        },
    )
    return 0


def dry_run_command(args: argparse.Namespace) -> int:
    package = load_package(args.package)
    server_root = args.server_root or args.world.parent
    with world_lock_probe(args.world, allow_missing=args.allow_missing_session_lock):
        identity = validate_world_identity(args.world, package.ledger.get("world_identity"))
        server_config = validate_create_server_config(
            server_root,
            package.ledger,
            has_item_vaults=any(group.storage_kind == "create:item_vault" for group in package.groups),
        )
        result = preflight(args.world, package)
        receipt = receipt_location(args.world, package)
        action_counts: dict[str, int] = defaultdict(int)
        for live in result.members.values():
            action_counts[live.action] += 1
        report = {
            "status": "dry-run-ok" if result.eligible else "no-eligible-groups",
            "package_id": package.ledger["package_id"],
            "ledger_sha256": package.ledger_digest,
            "confirmation": package.ledger_digest[:16],
            "world": str(args.world),
            "world_identity": identity,
            "server_config": server_config,
            "receipt_exists": receipt.exists(),
            "eligible_groups": [group.group_id for group in result.eligible],
            "eligible_group_count": len(result.eligible),
            "conflict_group_count": len(result.conflicts),
            "conflicts": result.conflicts,
            "action_counts": dict(sorted(action_counts.items())),
            "would_modify_block_entities": sum(
                1
                for group in result.eligible
                for member in group.members
                if result.members[member.key].proposed_content is not None
            ),
            "would_modify_chunks": len(
                {
                    (member.region_path.as_posix(), member.slot)
                    for group in result.eligible
                    for member in group.members
                    if result.members[member.key].proposed_content is not None
                }
            ),
        }
        report_output(args.report, report)
        return 0


def apply_command(args: argparse.Namespace) -> int:
    package = load_package(args.package)
    server_root = args.server_root or args.world.parent
    require_confirmation(args.confirm, package.ledger_digest)
    receipt = receipt_location(args.world, package)
    if receipt.exists():
        raise OtaError(f"idempotent receipt already exists; refusing second apply: {receipt}")
    with world_lock_probe(args.world, allow_missing=args.allow_missing_session_lock):
        identity = validate_world_identity(args.world, package.ledger.get("world_identity"))
        server_config = validate_create_server_config(
            server_root,
            package.ledger,
            has_item_vaults=any(group.storage_kind == "create:item_vault" for group in package.groups),
        )
        first = preflight(args.world, package)
        if args.require_zero_conflicts and first.conflicts:
            report_output(
                args.report,
                {
                    "status": "blocked",
                    "reason": "--require-zero-conflicts was set",
                    "conflicts": first.conflicts,
                },
            )
            return 2
        if not first.eligible:
            report_output(
                args.report,
                {"status": "no-op", "reason": "no groups passed compare-and-set", "conflicts": first.conflicts},
            )
            return 0

        timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        backup_root = args.backup_root / f"{package.ledger['package_id']}-{package.ledger_digest[:16]}-{timestamp}"
        if backup_root.exists():
            raise OtaError(f"backup path already exists: {backup_root}")
        (backup_root / "regions").mkdir(parents=True)
        (backup_root / "block-entities").mkdir(parents=True)

        touched_regions: dict[Path, Path] = {}
        member_snapshots: list[dict[str, Any]] = []
        for group in first.eligible:
            for spec in group.members:
                live = first.members[spec.key]
                # ``convert_legacy`` members have no authoritative payload by
                # design: their current live bytes are only being re-enveloped
                # into the target schema.  They still need the same snapshot,
                # region lock and rollback treatment as source restores.
                if live.proposed_content is None:
                    continue
                try:
                    relative_region = live.region.resolve().relative_to(args.world.resolve())
                except ValueError as exc:
                    raise OtaError(f"region escaped world root: {live.region}") from exc
                if live.region not in touched_regions:
                    region_backup = backup_root / "regions" / relative_region
                    region_backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(live.region, region_backup)
                    if sha256_file(live.region) != sha256_file(region_backup):
                        raise OtaError(f"full-region backup hash mismatch: {live.region}")
                    touched_regions[live.region] = region_backup
                snapshot_path = (
                    backup_root
                    / "block-entities"
                    / spec.dimension.replace(":", "__").replace("/", "_")
                    / f"{spec.pos[0]}.{spec.pos[1]}.{spec.pos[2]}.nbt"
                )
                snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                snapshot_sha = snapshot_block_entity(snapshot_path, live.block_entity)
                payload = live.proposed_content
                member_snapshots.append(
                    {
                        "group_id": group.group_id,
                        "dimension": spec.dimension,
                        "pos": list(spec.pos),
                        "block_entity_id": spec.block_entity_id,
                        "region_path": spec.region_path.as_posix(),
                        "chunk": [spec.chunk_x, spec.chunk_z],
                        "slot": spec.slot,
                        "stable_fields": spec.stable_fields,
                        "stable_absent": list(spec.stable_absent),
                        "expected_block_state": spec.expected_block_state,
                        "content_path": spec.content_path,
                        "content_schema": spec.content_schema,
                        "legacy_schema": spec.legacy_schema,
                        "target_max_capacity": spec.target_max_capacity,
                        "expected_legacy_converted_sha256": spec.expected_legacy_converted_sha256,
                        "action": live.action,
                        "remove_paths": list(live.remove_paths),
                        "snapshot_path": str(snapshot_path),
                        "snapshot_sha256": snapshot_sha,
                        "pre_content_sha256": None if live.content is MISSING else content_hash(live.content),
                        "post_content_sha256": content_hash(payload),
                        "post_removed_paths": list(live.remove_paths),
                    }
                )

        # Second preflight after every backup/snapshot.  The stopped world must
        # remain byte-identical at each touched chunk before we prepare writes.
        second = preflight(args.world, package)
        second_eligible = {group.group_id for group in second.eligible}
        first_eligible = {group.group_id for group in first.eligible}
        if second_eligible != first_eligible:
            raise OtaError("second preflight eligibility differs from the first; aborting before writes")
        for key, expected_hash in first.chunk_hashes.items():
            if second.chunk_hashes.get(key) != expected_hash:
                raise OtaError(f"live chunk changed between preflights: {key[0]}:{key[1]}")

        modified_chunks: dict[tuple[Path, int], ChunkImage] = {
            key: ChunkImage(image.record, copy.deepcopy(image.chunk)) for key, image in second.chunks.items()
        }
        post_member_hashes: dict[tuple[str, int, int, int], str] = {}
        for group in second.eligible:
            for spec in group.members:
                live = second.members[spec.key]
                if live.proposed_content is None:
                    continue
                image = modified_chunks[live.chunk_key]
                block_entity = find_block_entity(image.chunk, spec.pos)
                if block_entity is None:
                    raise OtaError(f"block entity vanished in prepared image: {spec.key}")
                payload = live.proposed_content
                apply_payload(block_entity, spec, payload, live.remove_paths)
                actual = dotted_get(block_entity, spec.content_path)
                if content_hash(actual) != content_hash(payload):
                    raise OtaError(f"prepared content postcondition failed: {spec.key}")
                for path in live.remove_paths:
                    if dotted_get(block_entity, path) is not MISSING:
                        raise OtaError(f"prepared legacy-field removal failed: {spec.key}:{path}")
                post_member_hashes[spec.key] = content_hash(payload)

        replacements_by_region: dict[Path, dict[int, bytes]] = defaultdict(dict)
        changed_chunk_keys: set[tuple[Path, int]] = set()
        for group in second.eligible:
            for spec in group.members:
                if second.members[spec.key].proposed_content is None:
                    continue
                changed_chunk_keys.add(second.members[spec.key].chunk_key)
        for key in sorted(changed_chunk_keys, key=lambda item: (str(item[0]).lower(), item[1])):
            region, slot = key
            replacements_by_region[region][slot] = record_from_chunk(modified_chunks[key].chunk)

        prepared: dict[Path, Path] = {}
        replaced: list[Path] = []
        try:
            for region, replacements in sorted(replacements_by_region.items(), key=lambda item: str(item[0]).lower()):
                prepared[region] = prepare_region(
                    region,
                    replacements,
                    suffix=f".object-ota-{package.ledger_digest[:12]}.tmp",
                )
            for region, temp in prepared.items():
                os.replace(temp, region)
                replaced.append(region)
            final = preflight(args.world, package)
            final_conflicts = {row["group_id"]: row for row in final.conflicts}
            for group in second.eligible:
                # A successful group is now intentionally non-empty, so the
                # normal preflight reports it as a non-empty conflict.  Verify
                # exact payload hashes instead of expecting eligibility.
                for spec in group.members:
                    # Schema-only legacy re-encodes have no package payload
                    # path, but they are still real mutations and must be
                    # checked after the atomic region swap.
                    if second.members[spec.key].proposed_content is None:
                        continue
                    region = local_path(args.world, spec.region_path)
                    image = read_chunk_image(region, spec.slot)
                    if image is None:
                        raise OtaError(f"post-apply chunk missing: {spec.key}")
                    block_entity = find_block_entity(image.chunk, spec.pos)
                    if block_entity is None:
                        raise OtaError(f"post-apply block entity missing: {spec.key}")
                    actual = dotted_get(block_entity, spec.content_path)
                    if actual is MISSING or content_hash(actual) != post_member_hashes[spec.key]:
                        raise OtaError(f"post-apply content hash mismatch: {spec.key}")
                    remove_paths = second.members[spec.key].remove_paths
                    for path in remove_paths:
                        if dotted_get(block_entity, path) is not MISSING:
                            raise OtaError(f"post-apply legacy field still present: {spec.key}:{path}")
        except Exception:
            for region in reversed(replaced):
                atomic_restore_file(touched_regions[region], region)
            raise
        finally:
            for temp in prepared.values():
                with contextlib.suppress(FileNotFoundError):
                    temp.unlink()

        receipt_payload = {
            "format": RECEIPT_FORMAT,
            "status": "applied",
            "applied_utc": utc_now(),
            "package_id": package.ledger["package_id"],
            "ledger_sha256": package.ledger_digest,
            "world": str(args.world.resolve()),
            "world_identity": identity,
            "server_config": server_config,
            "server_config_requirements": package.ledger.get("server_config_requirements", {}),
            "has_item_vaults": any(group.storage_kind == "create:item_vault" for group in package.groups),
            "backup_root": str(backup_root),
            "regions": [
                {
                    "region_path": str(region.resolve().relative_to(args.world.resolve())).replace("\\", "/"),
                    "backup_path": str(backup),
                    "backup_sha256": sha256_file(backup),
                    "post_apply_region_sha256": sha256_file(region),
                }
                for region, backup in sorted(touched_regions.items(), key=lambda item: str(item[0]).lower())
            ],
            "members": member_snapshots,
            "applied_groups": [group.group_id for group in second.eligible],
            "skipped_conflicts": first.conflicts,
        }
        receipt.parent.mkdir(parents=True, exist_ok=True)
        write_fsync(receipt, canonical_json(receipt_payload))
        report_output(
            args.report,
            {
                "status": "applied",
                "ledger_sha256": package.ledger_digest,
                "receipt": str(receipt),
                "backup_root": str(backup_root),
                "applied_group_count": len(second.eligible),
                "skipped_conflict_count": len(first.conflicts),
                "modified_block_entities": len(member_snapshots),
                "modified_chunks": len(changed_chunk_keys),
                "modified_regions": len(replacements_by_region),
                "conflicts": first.conflicts,
            },
        )
        return 0


def load_receipt(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OtaError(f"cannot read receipt {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("format") != RECEIPT_FORMAT:
        raise OtaError(f"receipt format is not {RECEIPT_FORMAT}")
    digest = value.get("ledger_sha256")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        raise OtaError("receipt ledger_sha256 is invalid")
    return value


def receipt_member_spec(row: Mapping[str, Any]) -> MemberSpec:
    value = {
        "dimension": row.get("dimension"),
        "pos": row.get("pos"),
        "block_entity_id": row.get("block_entity_id"),
        "region_path": row.get("region_path"),
        "chunk": row.get("chunk"),
        "stable_fields": row.get("stable_fields", {}),
        "stable_absent": row.get("stable_absent", []),
        "expected_block_state": row.get("expected_block_state"),
        "content_path": row.get("content_path"),
        "content_schema": row.get("content_schema"),
        "legacy_schema": row.get("legacy_schema"),
        "target_max_capacity": row.get("target_max_capacity"),
        "expected_legacy_converted_sha256": row.get("expected_legacy_converted_sha256"),
    }
    return normalize_member(value)


def rollback_command(args: argparse.Namespace) -> int:
    receipt = load_receipt(args.receipt)
    digest = receipt["ledger_sha256"]
    require_confirmation(args.confirm, digest)
    expected_world = Path(receipt.get("world", ""))
    server_root = args.server_root or args.world.parent
    if expected_world.resolve() != args.world.resolve():
        raise OtaError(f"receipt belongs to {expected_world}, not {args.world}")
    rows = receipt.get("members")
    if not isinstance(rows, list) or not rows:
        raise OtaError("receipt has no block-entity snapshots")
    with world_lock_probe(args.world, allow_missing=args.allow_missing_session_lock):
        validate_world_identity(args.world, receipt.get("world_identity"))
        validate_create_server_config(
            server_root,
            receipt,
            has_item_vaults=bool(receipt.get("has_item_vaults", False)),
        )
        by_group: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            if not isinstance(row, Mapping):
                raise OtaError("receipt member row is invalid")
            by_group[str(row.get("group_id"))].append(row)
        conflicts: list[dict[str, Any]] = []
        eligible_groups: list[str] = []
        chunks: dict[tuple[Path, int], ChunkImage] = {}
        specs: dict[tuple[str, int, int, int], MemberSpec] = {}
        snapshots: dict[tuple[str, int, int, int], Mapping[str, Any]] = {}
        for group_id, group_rows in by_group.items():
            reasons: list[dict[str, Any]] = []
            for row in group_rows:
                spec = receipt_member_spec(row)
                specs[spec.key] = spec
                region = local_path(args.world, spec.region_path)
                key = (region, spec.slot)
                if key not in chunks:
                    image = read_chunk_image(region, spec.slot)
                    if image is None:
                        reasons.append({"member": list(spec.pos), "reason": "live chunk missing"})
                        continue
                    chunks[key] = image
                block_entity = find_block_entity(chunks[key].chunk, spec.pos)
                if block_entity is None or plain(block_entity.get("id")) != spec.block_entity_id:
                    reasons.append({"member": list(spec.pos), "reason": "block entity identity changed"})
                    continue
                stable = validate_stable_fields(spec, block_entity)
                if stable:
                    reasons.extend({"member": list(spec.pos), "reason": reason} for reason in stable)
                    continue
                try:
                    actual_state = block_state_at(chunks[key].chunk, spec.pos)
                except OtaError as exc:
                    reasons.append({"member": list(spec.pos), "reason": f"block-state decode failed: {exc}"})
                    continue
                state_problems = validate_expected_block_state(spec.expected_block_state, actual_state)
                if state_problems:
                    reasons.extend({"member": list(spec.pos), "reason": reason} for reason in state_problems)
                    continue
                current = dotted_get(block_entity, spec.content_path)
                if current is MISSING or content_hash(current) != row.get("post_content_sha256"):
                    reasons.append(
                        {"member": list(spec.pos), "reason": "content changed after OTA; rollback CAS refused"}
                    )
                    continue
                remove_paths = row.get("post_removed_paths", row.get("remove_paths", []))
                if not isinstance(remove_paths, list) or not all(isinstance(path, str) and path for path in remove_paths):
                    raise OtaError(f"receipt remove_paths is invalid for {spec.key}")
                lingering = [path for path in remove_paths if dotted_get(block_entity, path) is not MISSING]
                if lingering:
                    reasons.append(
                        {
                            "member": list(spec.pos),
                            "reason": "legacy fields changed after OTA; rollback CAS refused",
                            "paths": lingering,
                        }
                    )
                    continue
                snapshot_path = Path(str(row.get("snapshot_path", "")))
                if not snapshot_path.is_file() or sha256_file(snapshot_path) != row.get("snapshot_sha256"):
                    raise OtaError(f"snapshot missing or hash mismatch: {snapshot_path}")
                root = parse_nbt_file(snapshot_path.read_bytes(), label=str(snapshot_path))
                snapshot_be = root.get("BlockEntity")
                if not isinstance(snapshot_be, Mapping):
                    raise OtaError(f"snapshot has no BlockEntity compound: {snapshot_path}")
                snapshots[spec.key] = snapshot_be
            if reasons:
                conflicts.append({"group_id": group_id, "action": "skip", "reasons": reasons})
            else:
                eligible_groups.append(group_id)
        if args.require_zero_conflicts and conflicts:
            report_output(args.report, {"status": "blocked", "conflicts": conflicts})
            return 2
        if not eligible_groups:
            report_output(args.report, {"status": "no-op", "conflicts": conflicts})
            return 0

        changed_keys: set[tuple[Path, int]] = set()
        for group_id in eligible_groups:
            for row in by_group[group_id]:
                spec = specs[(row["dimension"], row["pos"][0], row["pos"][1], row["pos"][2])]
                region = local_path(args.world, spec.region_path)
                key = (region, spec.slot)
                block_entity = find_block_entity(chunks[key].chunk, spec.pos)
                if block_entity is None:
                    raise OtaError(f"rollback block entity vanished: {spec.key}")
                remove_paths = row.get("remove_paths", row.get("post_removed_paths", []))
                restore_snapshot_fields(block_entity, spec, snapshots[spec.key], remove_paths)
                changed_keys.add(key)

        replacements: dict[Path, dict[int, bytes]] = defaultdict(dict)
        for region, slot in changed_keys:
            replacements[region][slot] = record_from_chunk(chunks[(region, slot)].chunk)
        timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        safety_root = args.rollback_backup_root / f"pre-rollback-{digest[:16]}-{timestamp}"
        safety_root.mkdir(parents=True)
        originals: dict[Path, Path] = {}
        prepared: dict[Path, Path] = {}
        replaced: list[Path] = []
        try:
            for region, region_replacements in sorted(replacements.items(), key=lambda item: str(item[0]).lower()):
                relative = region.resolve().relative_to(args.world.resolve())
                backup = safety_root / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(region, backup)
                originals[region] = backup
                prepared[region] = prepare_region(region, region_replacements, f".rollback-{digest[:12]}.tmp")
            for region, temp in prepared.items():
                os.replace(temp, region)
                replaced.append(region)
        except Exception:
            for region in reversed(replaced):
                atomic_restore_file(originals[region], region)
            raise
        finally:
            for temp in prepared.values():
                with contextlib.suppress(FileNotFoundError):
                    temp.unlink()
        rollback_receipt = args.receipt.with_name(args.receipt.stem + f".rollback-{timestamp}.json")
        write_fsync(
            rollback_receipt,
            canonical_json(
                {
                    "format": RECEIPT_FORMAT,
                    "status": "rolled-back",
                    "rolled_back_utc": utc_now(),
                    "source_receipt": str(args.receipt),
                    "ledger_sha256": digest,
                    "world": str(args.world.resolve()),
                    "eligible_groups": eligible_groups,
                    "skipped_conflicts": conflicts,
                    "safety_backup_root": str(safety_root),
                }
            ),
        )
        report_output(
            args.report,
            {
                "status": "rolled-back",
                "rollback_receipt": str(rollback_receipt),
                "restored_group_count": len(eligible_groups),
                "skipped_conflict_count": len(conflicts),
                "modified_chunks": len(changed_keys),
                "conflicts": conflicts,
            },
        )
        return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    finalize = sub.add_parser("finalize", help="hash typed payloads and build a deterministic OTA zip/directory")
    finalize.add_argument("--draft", type=Path, required=True)
    finalize.add_argument("--payload-root", type=Path, default=Path("."))
    finalize.add_argument("--output", type=Path, required=True)
    finalize.add_argument("--temp-root", type=Path, default=Path("D:/Trans"))
    finalize.add_argument("--report", type=Path)
    finalize.set_defaults(func=finalize_command)

    verify = sub.add_parser("verify", help="verify ledger, hashes, typed payloads, and source-nonempty invariant")
    verify.add_argument("--package", type=Path, required=True)
    verify.add_argument("--report", type=Path)
    verify.set_defaults(func=verify_command)

    dry = sub.add_parser("dry-run", help="run object/group compare-and-set against a stopped world")
    dry.add_argument("--package", type=Path, required=True)
    dry.add_argument("--world", type=Path, required=True)
    dry.add_argument("--server-root", type=Path, help="server root containing config/create-server.toml")
    dry.add_argument("--allow-missing-session-lock", action="store_true")
    dry.add_argument("--report", type=Path)
    dry.set_defaults(func=dry_run_command)

    apply = sub.add_parser("apply", help="transactionally set only eligible empty block-entity content fields")
    apply.add_argument("--package", type=Path, required=True)
    apply.add_argument("--world", type=Path, required=True)
    apply.add_argument("--server-root", type=Path, help="server root containing config/create-server.toml")
    apply.add_argument("--backup-root", type=Path, required=True, help="D: backup root")
    apply.add_argument("--confirm", required=True, help="first 16 hex digits printed by verify/dry-run")
    apply.add_argument("--require-zero-conflicts", action="store_true")
    apply.add_argument("--allow-missing-session-lock", action="store_true")
    apply.add_argument("--report", type=Path)
    apply.set_defaults(func=apply_command)

    rollback = sub.add_parser("rollback", help="CAS-restore only snapshotted content fields")
    rollback.add_argument("--receipt", type=Path, required=True)
    rollback.add_argument("--world", type=Path, required=True)
    rollback.add_argument("--server-root", type=Path, help="server root containing config/create-server.toml")
    rollback.add_argument("--rollback-backup-root", type=Path, required=True, help="D: rollback safety backup root")
    rollback.add_argument("--confirm", required=True)
    rollback.add_argument("--require-zero-conflicts", action="store_true")
    rollback.add_argument("--allow-missing-session-lock", action="store_true")
    rollback.add_argument("--report", type=Path)
    rollback.set_defaults(func=rollback_command)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.func(args))
    except OtaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
