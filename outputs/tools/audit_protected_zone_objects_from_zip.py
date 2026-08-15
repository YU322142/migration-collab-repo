#!/usr/bin/env python3
"""Read-only object audit for protected Overworld chunks stored in a server ZIP.

The archive is never extracted as a world.  Only the selected MCA members are
streamed, one at a time, into an auto-deleted temporary file on the requested
drive.  No Java process is started and no NBT is modified.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import re
import shutil
import struct
import tempfile
import uuid
import zipfile
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, BinaryIO, Iterator

import nbtlib


REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
MCA_KINDS = ("region", "entities", "poi")
OVERWORLD_NAMES = {"minecraft:overworld", "overworld", "0", 0}

VANILLA_CONTAINER_IDS = {
    "minecraft:barrel",
    "minecraft:blast_furnace",
    "minecraft:brewing_stand",
    "minecraft:chest",
    "minecraft:crafter",
    "minecraft:dispenser",
    "minecraft:dropper",
    "minecraft:furnace",
    "minecraft:hopper",
    "minecraft:smoker",
    "minecraft:trapped_chest",
}
VANILLA_DATA_IDS = {
    "minecraft:beacon",
    "minecraft:beehive",
    "minecraft:brushable_block",
    "minecraft:calibrated_sculk_sensor",
    "minecraft:campfire",
    "minecraft:command_block",
    "minecraft:comparator",
    "minecraft:conduit",
    "minecraft:decorated_pot",
    "minecraft:end_gateway",
    "minecraft:end_portal",
    "minecraft:enchanting_table",
    "minecraft:jigsaw",
    "minecraft:jukebox",
    "minecraft:lectern",
    "minecraft:mob_spawner",
    "minecraft:sculk_catalyst",
    "minecraft:sculk_sensor",
    "minecraft:sculk_shrieker",
    "minecraft:sign",
    "minecraft:skull",
    "minecraft:structure_block",
    "minecraft:trial_spawner",
    "minecraft:vault",
}
TAMEABLE_ENTITY_IDS = {
    "minecraft:allay",
    "minecraft:cat",
    "minecraft:donkey",
    "minecraft:horse",
    "minecraft:llama",
    "minecraft:mule",
    "minecraft:parrot",
    "minecraft:skeleton_horse",
    "minecraft:trader_llama",
    "minecraft:wolf",
    "minecraft:zombie_horse",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


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


def bounded_text(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    unpacked = plain(value)
    if isinstance(unpacked, str):
        text = unpacked
    else:
        text = json.dumps(unpacked, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text) > limit:
        return text[:limit] + f"…[truncated; chars={len(text)}; sha256={sha256_bytes(text.encode('utf-8'))}]"
    return text


def selected_chunks(center_x: int, center_z: int, radius: int) -> list[tuple[int, int]]:
    """Chunks with at least one discrete integer block inside/on the circle."""

    rows: list[tuple[int, int]] = []
    min_chunk_x = (center_x - radius) // 16 - 1
    max_chunk_x = (center_x + radius) // 16 + 1
    min_chunk_z = (center_z - radius) // 16 - 1
    max_chunk_z = (center_z + radius) // 16 + 1
    radius_squared = radius * radius
    for chunk_x in range(min_chunk_x, max_chunk_x + 1):
        block_min_x = chunk_x * 16
        block_max_x = block_min_x + 15
        delta_x = (
            0
            if block_min_x <= center_x <= block_max_x
            else min(abs(center_x - block_min_x), abs(center_x - block_max_x))
        )
        for chunk_z in range(min_chunk_z, max_chunk_z + 1):
            block_min_z = chunk_z * 16
            block_max_z = block_min_z + 15
            delta_z = (
                0
                if block_min_z <= center_z <= block_max_z
                else min(abs(center_z - block_min_z), abs(center_z - block_max_z))
            )
            if delta_x * delta_x + delta_z * delta_z <= radius_squared:
                rows.append((chunk_x, chunk_z))
    return rows


def exact_circle(x: float, z: float, center_x: int, center_z: int, radius: int) -> bool:
    return (x - center_x) ** 2 + (z - center_z) ** 2 <= radius**2


def chunk_of(x: float, z: float) -> tuple[int, int]:
    return math.floor(x / 16), math.floor(z / 16)


def slot_for_chunk(chunk_x: int, chunk_z: int) -> int:
    return (chunk_x & 31) + (chunk_z & 31) * 32


def parse_uuid(value: Any) -> str | None:
    value = plain(value)
    try:
        if isinstance(value, str):
            return str(uuid.UUID(value))
        if isinstance(value, list) and len(value) == 4:
            number = 0
            for part in value:
                number = (number << 32) | (int(part) & 0xFFFFFFFF)
            return str(uuid.UUID(int=number))
    except (ValueError, TypeError, AttributeError):
        return None
    return None


def uuid_from_compound(value: Mapping[str, Any]) -> str | None:
    direct = parse_uuid(value.get("UUID"))
    if direct:
        return direct
    if "UUIDMost" in value and "UUIDLeast" in value:
        try:
            high = int(plain(value["UUIDMost"])) & 0xFFFFFFFFFFFFFFFF
            low = int(plain(value["UUIDLeast"])) & 0xFFFFFFFFFFFFFFFF
            return str(uuid.UUID(int=(high << 64) | low))
        except (ValueError, TypeError, AttributeError):
            return None
    return None


def decompress(payload: bytes, compression: int) -> bytes:
    kind = compression & 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    if kind == 4:
        try:
            import lz4.block  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValueError("LZ4-compressed MCA chunk requires the lz4 Python package") from exc
        return lz4.block.decompress(payload)
    raise ValueError(f"unsupported MCA compression type {kind}")


def parse_nbt_bytes(payload: bytes, standalone: bool = False) -> Any:
    errors: list[str] = []
    candidates: list[bytes]
    if standalone:
        try:
            candidates = [gzip.decompress(payload), payload]
        except Exception as exc:
            errors.append(f"gzip: {type(exc).__name__}: {exc}")
            candidates = [payload]
    else:
        candidates = [payload]
    for raw in candidates:
        try:
            return nbtlib.File.parse(io.BytesIO(raw), byteorder="big")
        except Exception as exc:
            errors.append(f"nbt: {type(exc).__name__}: {exc}")
    raise ValueError("; ".join(errors))


def load_json_member(archive: zipfile.ZipFile, name: str) -> Any:
    try:
        return json.loads(archive.read(name).decode("utf-8-sig"))
    except KeyError:
        return None


def world_prefix(archive: zipfile.ZipFile) -> str:
    matches = [name[: -len("level.dat")] for name in archive.namelist() if name.endswith("/world/level.dat")]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one live world/level.dat, found {matches}")
    return matches[0]


def copy_member_to_temp(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    temp_root: Path,
) -> BinaryIO:
    handle = tempfile.TemporaryFile(mode="w+b", dir=temp_root)
    with archive.open(info, "r") as source:
        shutil.copyfileobj(source, handle, length=4 * 1024 * 1024)
    handle.seek(0)
    return handle


def iter_selected_region_chunks(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    kind: str,
    selected: set[tuple[int, int]],
    prefix: str,
    temp_root: Path,
) -> Iterator[tuple[int, int, int, int, Any]]:
    """Yield region x/z, slot, compression, and NBT for selected occupied slots."""

    match = REGION_RE.fullmatch(Path(info.filename).name)
    if match is None:
        raise ValueError(f"invalid MCA filename: {info.filename}")
    region_x, region_z = int(match.group(1)), int(match.group(2))
    with copy_member_to_temp(archive, info, temp_root) as handle:
        locations = handle.read(4096)
        if len(locations) != 4096:
            raise ValueError("truncated MCA location table")
        for slot in range(1024):
            chunk_x = region_x * 32 + (slot & 31)
            chunk_z = region_z * 32 + (slot >> 5)
            if (chunk_x, chunk_z) not in selected:
                continue
            entry = locations[slot * 4 : (slot + 1) * 4]
            offset = int.from_bytes(entry[:3], "big")
            sectors = entry[3]
            if offset == 0:
                continue
            handle.seek(offset * 4096)
            length_raw = handle.read(4)
            if len(length_raw) != 4:
                raise ValueError(f"slot {slot} has truncated length")
            length = struct.unpack(">I", length_raw)[0]
            compression_raw = handle.read(1)
            if length < 1 or len(compression_raw) != 1:
                raise ValueError(f"slot {slot} has invalid chunk header")
            compression = compression_raw[0]
            if sectors and length + 4 > sectors * 4096:
                raise ValueError(f"slot {slot} chunk length exceeds allocated sectors")
            if compression & 0x80:
                external_name = f"{prefix}{kind}/c.{chunk_x}.{chunk_z}.mcc"
                try:
                    payload = archive.read(external_name)
                except KeyError as exc:
                    raise ValueError(f"slot {slot} references missing external member {external_name}") from exc
            else:
                payload = handle.read(length - 1)
                if len(payload) != length - 1:
                    raise ValueError(f"slot {slot} has truncated payload")
            root = parse_nbt_bytes(decompress(payload, compression))
            yield region_x, region_z, slot, compression & 0x7F, root


def chunk_body(root: Any) -> Mapping[str, Any]:
    if isinstance(root, Mapping) and isinstance(root.get("Level"), Mapping):
        return root["Level"]
    if isinstance(root, Mapping):
        return root
    return {}


def first_list(body: Mapping[str, Any], *names: str) -> list[Any]:
    for name in names:
        value = body.get(name)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return list(value)
    return []


def walk(value: Any, path: tuple[str, ...] = (), budget: int = 100_000) -> Iterator[tuple[tuple[str, ...], Any]]:
    stack: list[tuple[tuple[str, ...], Any]] = [(path, value)]
    seen = 0
    while stack and seen < budget:
        current_path, current = stack.pop()
        seen += 1
        yield current_path, current
        if isinstance(current, Mapping):
            for key, child in reversed(list(current.items())):
                stack.append((current_path + (str(key),), child))
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            for index in range(len(current) - 1, -1, -1):
                stack.append((current_path + (f"[{index}]",), current[index]))


def item_stack_summary(value: Any) -> dict[str, Any]:
    ids: collections.Counter[str] = collections.Counter()
    stacks = 0
    total = 0
    for _path, node in walk(value):
        if not isinstance(node, Mapping):
            continue
        identifier = plain(node.get("id", node.get("Id")))
        count = plain(node.get("count", node.get("Count")))
        if not isinstance(identifier, str) or ":" not in identifier or count is None:
            continue
        try:
            amount = int(count)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        stacks += 1
        total += amount
        ids[identifier] += amount
    return {
        "nonempty_stacks": stacks,
        "total_item_count": total,
        "item_id_totals": dict(sorted(ids.items())),
    }


def fluid_summary(value: Any) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path, node in walk(value):
        if not isinstance(node, Mapping):
            continue
        path_text = ".".join(path).lower()
        fluid_value: Any = None
        for key in ("FluidName", "fluid_name", "Fluid", "fluid"):
            if key in node:
                fluid_value = plain(node[key])
                break
        if isinstance(fluid_value, Mapping):
            fluid_value = fluid_value.get("id", fluid_value.get("Name", fluid_value.get("name")))
        if fluid_value is None and ("fluid" in path_text or "tank" in path_text):
            candidate = plain(node.get("id", node.get("Name", node.get("name"))))
            if isinstance(candidate, str) and ":" in candidate:
                fluid_value = candidate
        if not isinstance(fluid_value, str) or ":" not in fluid_value:
            continue
        amount_value = None
        for key in ("Amount", "amount"):
            if key in node:
                amount_value = plain(node[key])
                break
        try:
            amount = int(amount_value)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            rows.append({"path": ".".join(path), "fluid": fluid_value, "amount": amount})
    unique = {(row["path"], row["fluid"], row["amount"]): row for row in rows}
    result = sorted(unique.values(), key=lambda row: (row["path"], row["fluid"], row["amount"]))
    return {"nonempty_tanks": len(result), "rows": result[:50], "truncated": len(result) > 50}


def key_paths(value: Any, predicates: tuple[str, ...]) -> list[str]:
    needles = tuple(needle.lower() for needle in predicates)
    rows: list[str] = []
    for path, _node in walk(value):
        if not path:
            continue
        key = path[-1].lower()
        if any(needle in key for needle in needles):
            rows.append(".".join(path))
    return sorted(set(rows))[:100]


def owner_refs(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    needles = ("owner", "trusted", "love_cause", "angry_at", "leash")
    for path, node in walk(value):
        if not path or not any(needle in path[-1].lower() for needle in needles):
            continue
        unpacked = plain(node)
        if isinstance(unpacked, (Mapping, list)):
            rendered = bounded_text(unpacked, 300)
        elif isinstance(unpacked, (str, int)):
            rendered = str(unpacked)
        else:
            continue
        rows.append({"path": ".".join(path), "value": rendered})
    deduped = {(row["path"], row["value"]): row for row in rows}
    return sorted(deduped.values(), key=lambda row: (row["path"], row["value"] or ""))[:50]


def boolish(value: Any) -> bool:
    unpacked = plain(value)
    return bool(unpacked) and unpacked not in ("0", "false", "False")


def position(value: Mapping[str, Any]) -> list[float] | None:
    raw = plain(value.get("Pos"))
    if isinstance(raw, list) and len(raw) >= 3:
        try:
            return [float(raw[0]), float(raw[1]), float(raw[2])]
        except (TypeError, ValueError):
            pass
    if all(axis in value for axis in ("x", "y", "z")):
        try:
            return [float(plain(value["x"])), float(plain(value["y"])), float(plain(value["z"]))]
        except (TypeError, ValueError):
            pass
    return None


def entity_record(
    entity: Any,
    chunk_x: int,
    chunk_z: int,
    source: str,
    slot: int,
    path: str,
    center_x: int,
    center_z: int,
    radius: int,
) -> dict[str, Any]:
    value = plain(entity)
    if not isinstance(value, Mapping):
        return {
            "id": "<non-compound>",
            "source": source,
            "slot": slot,
            "source_chunk": [chunk_x, chunk_z],
            "path": path,
            "risk": "HIGH",
        }
    identifier = str(value.get("id", "<missing>"))
    pos = position(value)
    actual_chunk = list(chunk_of(pos[0], pos[2])) if pos else None
    custom_name = bounded_text(value.get("CustomName", value.get("custom_name")), 500)
    refs = owner_refs(value)
    items = item_stack_summary(value)
    is_maid = identifier.startswith("touhou_little_maid:") or "maid" in identifier.lower()
    is_vehicle = any(
        token in identifier.lower()
        for token in ("boat", "minecart", "contraption", "carriage", "vehicle", "airship", "train")
    )
    is_villager = identifier in {"minecraft:villager", "minecraft:wandering_trader"}
    is_tamed = boolish(value.get("Tame", value.get("tame", False))) or bool(refs) or identifier in TAMEABLE_ENTITY_IDS and "Owner" in value
    persistent = boolish(value.get("PersistenceRequired", value.get("persistent", False)))
    has_passengers = bool(value.get("Passengers"))
    has_inventory = items["nonempty_stacks"] > 0
    flags: list[str] = []
    for enabled, label in (
        (is_maid, "maid"),
        (is_vehicle, "vehicle"),
        (is_villager, "villager"),
        (is_tamed, "tamed_or_owned"),
        (custom_name is not None, "custom_named"),
        (has_inventory, "carries_items"),
        (persistent, "persistent"),
        (has_passengers, "has_passengers"),
        (bool(refs), "player_reference"),
        (not identifier.startswith("minecraft:"), "modded"),
    ):
        if enabled:
            flags.append(label)
    if any(flag in flags for flag in ("maid", "vehicle", "villager", "tamed_or_owned", "custom_named", "carries_items", "player_reference")):
        risk = "CRITICAL"
    elif "modded" in flags or "persistent" in flags or "has_passengers" in flags:
        risk = "HIGH"
    else:
        risk = "MEDIUM"
    return {
        "id": identifier,
        "uuid": uuid_from_compound(value),
        "pos": pos,
        "actual_chunk": actual_chunk,
        "source_chunk": [chunk_x, chunk_z],
        "inside_exact_circle": exact_circle(pos[0], pos[2], center_x, center_z, radius) if pos else None,
        "custom_name": custom_name,
        "owner_or_player_refs": refs,
        "item_summary": items,
        "flags": flags,
        "risk": risk,
        "source": source,
        "slot": slot,
        "path": path,
    }


def flatten_entities(values: Sequence[Any], prefix: str = "Entities") -> Iterator[tuple[str, Any]]:
    stack: list[tuple[str, Any]] = [(f"{prefix}[{index}]", value) for index, value in reversed(list(enumerate(values)))]
    while stack:
        path, value = stack.pop()
        yield path, value
        if isinstance(value, Mapping):
            passengers = value.get("Passengers")
            if isinstance(passengers, Sequence) and not isinstance(passengers, (str, bytes, bytearray)):
                for index in range(len(passengers) - 1, -1, -1):
                    stack.append((f"{path}.Passengers[{index}]", passengers[index]))


def block_entity_record(
    block_entity: Any,
    chunk_x: int,
    chunk_z: int,
    source: str,
    slot: int,
    index: int,
    center_x: int,
    center_z: int,
    radius: int,
) -> dict[str, Any]:
    value = plain(block_entity)
    if not isinstance(value, Mapping):
        return {
            "id": "<non-compound>",
            "source_chunk": [chunk_x, chunk_z],
            "source": source,
            "slot": slot,
            "index": index,
            "risk": "CRITICAL",
        }
    identifier = str(value.get("id", "<missing>"))
    pos_raw = position(value)
    pos = [int(axis) for axis in pos_raw] if pos_raw else None
    actual_chunk = list(chunk_of(pos[0], pos[2])) if pos else None
    items = item_stack_summary(value)
    fluids = fluid_summary(value)
    custom_name = bounded_text(value.get("CustomName", value.get("custom_name", value.get("Name"))), 500)
    refs = owner_refs(value)
    text_paths = key_paths(value, ("text", "message", "book", "command"))
    computer_paths = key_paths(value, ("computerid", "computer_id"))
    energy_paths = key_paths(value, ("energy", "power", "stress"))
    inventory_paths = key_paths(value, ("inventory", "items", "content", "filter"))
    loot_paths = key_paths(value, ("loottable", "loot_table"))
    modded = not identifier.startswith("minecraft:")
    container = identifier in VANILLA_CONTAINER_IDS or bool(inventory_paths) or items["nonempty_stacks"] > 0
    data_bearing = (
        container
        or fluids["nonempty_tanks"] > 0
        or bool(computer_paths)
        or bool(text_paths)
        or bool(refs)
        or custom_name is not None
        or identifier in VANILLA_DATA_IDS
        or modded
    )
    flags: list[str] = []
    for enabled, label in (
        (modded, "modded"),
        (container, "container_or_inventory"),
        (items["nonempty_stacks"] > 0, "nonempty_items"),
        (fluids["nonempty_tanks"] > 0, "nonempty_fluids"),
        (bool(computer_paths), "computer"),
        (bool(text_paths), "text_book_or_command"),
        (bool(refs), "owner_or_player_reference"),
        (custom_name is not None, "custom_named"),
        (bool(energy_paths), "machine_energy_or_power"),
        (bool(loot_paths), "loot_table"),
        (identifier in VANILLA_DATA_IDS, "vanilla_data_block"),
    ):
        if enabled:
            flags.append(label)
    if any(
        flag in flags
        for flag in (
            "nonempty_items",
            "nonempty_fluids",
            "computer",
            "text_book_or_command",
            "owner_or_player_reference",
            "custom_named",
        )
    ):
        risk = "CRITICAL"
    elif data_bearing:
        risk = "HIGH"
    else:
        risk = "MEDIUM"
    if risk == "CRITICAL":
        suggestion = "SALVAGE_OR_RELOCATE_WITH_SUPPORTING_BLOCKS_BEFORE_V_REPLACEMENT"
    elif risk == "HIGH":
        suggestion = "REVIEW_THEN_RECREATE_FROM_V_OR_PRESERVE_AS_EXPLICIT_SMALL_EXCEPTION"
    else:
        suggestion = "ALLOW_V_REPLACEMENT_ONLY_IF_LOSS_IS_INTENTIONAL"
    return {
        "id": identifier,
        "pos": pos,
        "actual_chunk": actual_chunk,
        "source_chunk": [chunk_x, chunk_z],
        "inside_exact_circle": exact_circle(pos[0], pos[2], center_x, center_z, radius) if pos else None,
        "custom_name": custom_name,
        "owner_or_player_refs": refs,
        "item_summary": items,
        "fluid_summary": fluids,
        "interesting_paths": {
            "inventory_or_filter": inventory_paths,
            "computer": computer_paths,
            "text_book_or_command": text_paths,
            "energy_or_power": energy_paths,
            "loot_table": loot_paths,
        },
        "top_level_keys": sorted(str(key) for key in value.keys()),
        "flags": flags,
        "risk": risk,
        "suggestion": suggestion,
        "source": source,
        "slot": slot,
        "index": index,
    }


def poi_records(root: Any) -> list[dict[str, Any]]:
    body = chunk_body(root)
    sections = body.get("Sections", body.get("sections", {}))
    rows: list[dict[str, Any]] = []
    if not isinstance(sections, Mapping):
        return rows
    for section_y, section in sections.items():
        if not isinstance(section, Mapping):
            continue
        records = section.get("Records", section.get("records", []))
        if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
            continue
        for index, record in enumerate(records):
            value = plain(record)
            if not isinstance(value, Mapping):
                continue
            pos = value.get("pos", value.get("Pos"))
            if isinstance(pos, list) and len(pos) == 3:
                try:
                    pos = [int(axis) for axis in pos]
                except (TypeError, ValueError):
                    pos = None
            else:
                pos = None
            rows.append(
                {
                    "section_y": int(section_y),
                    "index": index,
                    "type": value.get("type", value.get("Type")),
                    "pos": pos,
                    "free_tickets": value.get("free_tickets", value.get("FreeTickets")),
                }
            )
    return rows


def player_audit(
    archive: zipfile.ZipFile,
    prefix: str,
    selected: set[tuple[int, int]],
    center_x: int,
    center_z: int,
    radius: int,
) -> dict[str, Any]:
    root_prefix = prefix[: -len("world/")]
    cache = load_json_member(archive, root_prefix + "usercache.json") or []
    ops = load_json_member(archive, root_prefix + "ops.json") or []
    whitelist = load_json_member(archive, root_prefix + "whitelist.json") or []
    names: dict[str, str] = {}
    for row in list(cache) + list(ops) + list(whitelist):
        if isinstance(row, Mapping) and row.get("uuid") and row.get("name"):
            try:
                names[str(uuid.UUID(str(row["uuid"])))] = str(row["name"])
            except ValueError:
                pass
    op_ids = {str(row.get("uuid")) for row in ops if isinstance(row, Mapping)}
    whitelist_ids = {str(row.get("uuid")) for row in whitelist if isinstance(row, Mapping)}

    current_members = sorted(
        (
            info
            for info in archive.infolist()
            if info.filename.startswith(prefix + "playerdata/") and info.filename.endswith(".dat")
        ),
        key=lambda info: info.filename,
    )
    old_members = [
        info
        for info in archive.infolist()
        if info.filename.startswith(prefix + "playerdata/") and info.filename.endswith(".dat_old")
    ]
    affected: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    dimensions: collections.Counter[str] = collections.Counter()
    current_inside_count = 0
    spawn_inside_count = 0
    for info in current_members:
        file_uuid = Path(info.filename).stem
        try:
            canonical_uuid = str(uuid.UUID(file_uuid))
        except ValueError:
            canonical_uuid = file_uuid
        try:
            root = parse_nbt_bytes(archive.read(info), standalone=True)
            data = plain(root)
        except Exception as exc:
            parse_errors.append({"member": info.filename, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if not isinstance(data, Mapping):
            parse_errors.append({"member": info.filename, "error": "root is not a compound"})
            continue
        dimension = plain(data.get("Dimension", "minecraft:overworld"))
        dimensions[str(dimension)] += 1
        pos = position(data)
        current: dict[str, Any] | None = None
        if pos:
            current_chunk = chunk_of(pos[0], pos[2])
            current = {
                "dimension": dimension,
                "pos": pos,
                "chunk": list(current_chunk),
                "inside_selected_chunk_set": dimension in OVERWORLD_NAMES and current_chunk in selected,
                "inside_exact_circle": dimension in OVERWORLD_NAMES and exact_circle(pos[0], pos[2], center_x, center_z, radius),
            }
        spawn: dict[str, Any] | None = None
        if "SpawnX" in data and "SpawnZ" in data:
            try:
                spawn_x = int(data["SpawnX"])
                spawn_y = int(data.get("SpawnY", 0))
                spawn_z = int(data["SpawnZ"])
                spawn_dimension = plain(data.get("SpawnDimension", "minecraft:overworld"))
                spawn_chunk = chunk_of(spawn_x, spawn_z)
                spawn = {
                    "dimension": spawn_dimension,
                    "pos": [spawn_x, spawn_y, spawn_z],
                    "chunk": list(spawn_chunk),
                    "inside_selected_chunk_set": spawn_dimension in OVERWORLD_NAMES and spawn_chunk in selected,
                    "inside_exact_circle": spawn_dimension in OVERWORLD_NAMES and exact_circle(spawn_x, spawn_z, center_x, center_z, radius),
                    "forced": bool(data.get("SpawnForced", False)),
                }
            except (TypeError, ValueError):
                spawn = {"parse_error": "SpawnX/Y/Z are not integers"}
        current_inside = bool(current and current.get("inside_selected_chunk_set"))
        spawn_inside = bool(spawn and spawn.get("inside_selected_chunk_set"))
        current_inside_count += int(current_inside)
        spawn_inside_count += int(spawn_inside)
        if current_inside or spawn_inside:
            affected.append(
                {
                    "uuid": canonical_uuid,
                    "name": names.get(canonical_uuid),
                    "is_op": canonical_uuid in op_ids,
                    "is_whitelisted": canonical_uuid in whitelist_ids,
                    "current": current,
                    "spawn": spawn,
                    "health": plain(data.get("Health")),
                    "game_type": plain(data.get("playerGameType")),
                    "member": info.filename,
                }
            )
    return {
        "current_dat_files": len(current_members),
        "dat_old_files": len(old_members),
        "parsed_current_dat_files": len(current_members) - len(parse_errors),
        "parse_errors": parse_errors,
        "dimension_counts": dict(sorted(dimensions.items())),
        "current_positions_inside_selected_chunks": current_inside_count,
        "spawn_positions_inside_selected_chunks": spawn_inside_count,
        "affected_players": sorted(affected, key=lambda row: (row.get("name") or "", row["uuid"])),
        "name_sources": {
            "usercache_entries": len(cache),
            "ops_entries": len(ops),
            "whitelist_entries": len(whitelist),
        },
    }


def top_counter(counter: collections.Counter[str], limit: int | None = None) -> dict[str, int]:
    rows = sorted(counter.items(), key=lambda row: (-row[1], row[0]))
    if limit is not None:
        rows = rows[:limit]
    return dict(rows)


def audit_archive(
    archive_path: Path,
    temp_root: Path,
    center_x: int,
    center_z: int,
    radius: int,
    expected_sha256: str | None,
) -> dict[str, Any]:
    selected_list = selected_chunks(center_x, center_z, radius)
    selected = set(selected_list)
    regions = sorted({(x // 32, z // 32) for x, z in selected})
    if len(selected) != 29_305 or len(regions) != 40:
        raise ValueError(f"selection invariant failed: chunks={len(selected)}, regions={len(regions)}")

    source_sha256 = sha256_file(archive_path)
    expected_ok = expected_sha256 is None or source_sha256 == expected_sha256.upper()
    parse_errors: list[dict[str, Any]] = []
    temp_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as archive:
        prefix = world_prefix(archive)
        info_by_name = {info.filename: info for info in archive.infolist()}
        players = player_audit(archive, prefix, selected, center_x, center_z, radius)

        entities: list[dict[str, Any]] = []
        block_entities: list[dict[str, Any]] = []
        pois: list[dict[str, Any]] = []
        per_kind: dict[str, Any] = {}

        for kind in MCA_KINDS:
            files_present = 0
            zero_length_files = 0
            file_bytes = 0
            occupied_chunks = 0
            parsed_chunks = 0
            compression_types: collections.Counter[str] = collections.Counter()
            for region_x, region_z in regions:
                member = f"{prefix}{kind}/r.{region_x}.{region_z}.mca"
                info = info_by_name.get(member)
                if info is None:
                    continue
                files_present += 1
                file_bytes += info.file_size
                if info.file_size == 0:
                    # Some runtimes leave a zero-byte region placeholder.  It
                    # has no header and semantically contains zero occupied
                    # slots, so it is not a corrupt/truncated MCA.
                    zero_length_files += 1
                    continue
                try:
                    for rx, rz, slot, compression, root in iter_selected_region_chunks(
                        archive, info, kind, selected, prefix, temp_root
                    ):
                        occupied_chunks += 1
                        parsed_chunks += 1
                        compression_types[str(compression)] += 1
                        chunk_x = rx * 32 + (slot & 31)
                        chunk_z = rz * 32 + (slot >> 5)
                        source = f"{kind}/r.{rx}.{rz}.mca"
                        body = chunk_body(root)
                        if kind == "entities":
                            raw_entities = first_list(body, "Entities", "entities")
                            for entity_path, entity in flatten_entities(raw_entities):
                                entities.append(
                                    entity_record(
                                        entity,
                                        chunk_x,
                                        chunk_z,
                                        source,
                                        slot,
                                        entity_path,
                                        center_x,
                                        center_z,
                                        radius,
                                    )
                                )
                        elif kind == "region":
                            raw_block_entities = first_list(
                                body,
                                "block_entities",
                                "BlockEntities",
                                "blockEntities",
                                "TileEntities",
                            )
                            for index, block_entity in enumerate(raw_block_entities):
                                block_entities.append(
                                    block_entity_record(
                                        block_entity,
                                        chunk_x,
                                        chunk_z,
                                        source,
                                        slot,
                                        index,
                                        center_x,
                                        center_z,
                                        radius,
                                    )
                                )
                        else:
                            for record in poi_records(root):
                                pos = record.get("pos")
                                record.update(
                                    {
                                        "source": source,
                                        "slot": slot,
                                        "source_chunk": [chunk_x, chunk_z],
                                        "inside_exact_circle": exact_circle(pos[0], pos[2], center_x, center_z, radius)
                                        if pos
                                        else None,
                                    }
                                )
                                pois.append(record)
                except Exception as exc:
                    parse_errors.append(
                        {
                            "kind": kind,
                            "member": member,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
            per_kind[kind] = {
                "candidate_region_files_present": files_present,
                "zero_length_region_placeholders": zero_length_files,
                "candidate_region_file_bytes": file_bytes,
                "occupied_selected_chunk_slots": occupied_chunks,
                "parsed_selected_chunk_slots": parsed_chunks,
                "compression_types": dict(sorted(compression_types.items())),
            }

    entity_ids = collections.Counter(row["id"] for row in entities)
    entity_risks = collections.Counter(row["risk"] for row in entities)
    entity_flags = collections.Counter(flag for row in entities for flag in row.get("flags", []))
    be_ids = collections.Counter(row["id"] for row in block_entities)
    be_risks = collections.Counter(row["risk"] for row in block_entities)
    be_flags = collections.Counter(flag for row in block_entities for flag in row.get("flags", []))
    poi_types = collections.Counter(str(row.get("type")) for row in pois)

    affected_player_chunks: set[tuple[int, int]] = set()
    for row in players["affected_players"]:
        for key in ("current", "spawn"):
            point = row.get(key)
            if isinstance(point, Mapping) and point.get("inside_selected_chunk_set") and point.get("chunk"):
                affected_player_chunks.add(tuple(point["chunk"]))
    critical_entity_chunks = {
        tuple(row["source_chunk"]) for row in entities if row["risk"] == "CRITICAL"
    }
    block_entity_chunks = {tuple(row["source_chunk"]) for row in block_entities}
    poi_chunks = {tuple(row["source_chunk"]) for row in pois}
    attention_chunks = affected_player_chunks | critical_entity_chunks | block_entity_chunks | poi_chunks

    blockers: list[dict[str, Any]] = []
    if not expected_ok:
        blockers.append(
            {
                "reason": "source archive SHA256 mismatch",
                "expected": expected_sha256,
                "actual": source_sha256,
            }
        )
    if parse_errors or players["parse_errors"]:
        blockers.append(
            {
                "reason": "NBT/MCA parse errors",
                "region_errors": len(parse_errors),
                "player_errors": len(players["parse_errors"]),
            }
        )
    if block_entities:
        blockers.append(
            {
                "reason": "blind terrain-slot replacement would delete current block entities",
                "count": len(block_entities),
                "critical": be_risks.get("CRITICAL", 0),
            }
        )
    if players["current_positions_inside_selected_chunks"]:
        blockers.append(
            {
                "reason": "offline players currently stand in chunks whose terrain will be replaced",
                "count": players["current_positions_inside_selected_chunks"],
            }
        )
    if entities:
        blockers.append(
            {
                "reason": "preserved entities require post-V collision/support validation",
                "count": len(entities),
                "critical": entity_risks.get("CRITICAL", 0),
            }
        )
    if pois:
        blockers.append(
            {
                "reason": "current POI records must not be retained blindly against replacement blocks",
                "count": len(pois),
            }
        )

    return {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "status": "PASS_FOR_BLIND_DIRECT_REPLACEMENT" if not blockers else "DIRECT_REPLACEMENT_REQUIRES_SAFETY_EXCEPTIONS",
        "operation": "protected-zone-important-object-audit-from-stopped-server-zip-readonly",
        "source": {
            "archive": str(archive_path.resolve()),
            "bytes": archive_path.stat().st_size,
            "last_write_utc": dt.datetime.fromtimestamp(archive_path.stat().st_mtime, dt.timezone.utc).isoformat(timespec="seconds"),
            "sha256": source_sha256,
            "expected_sha256": expected_sha256.upper() if expected_sha256 else None,
            "expected_sha256_matches": expected_ok,
            "world_prefix": prefix,
        },
        "scope": {
            "dimension": "minecraft:overworld",
            "center": {"x": center_x, "z": center_z},
            "radius_blocks": radius,
            "selection_rule": "A chunk is selected when at least one discrete integer block in its closed 16x16 square lies inside or on the circle.",
            "selected_chunks": len(selected),
            "selected_regions": len(regions),
            "selected_region_coordinates": [list(row) for row in regions],
        },
        "mca": per_kind,
        "players": players,
        "entities": {
            "total_in_selected_chunk_slots_including_nested_passengers": len(entities),
            "risk_counts": top_counter(entity_risks),
            "flag_counts": top_counter(entity_flags),
            "id_counts": top_counter(entity_ids),
            "records": sorted(
                entities,
                key=lambda row: (
                    {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}.get(row["risk"], 9),
                    row["id"],
                    row.get("pos") or [],
                ),
            ),
        },
        "block_entities": {
            "total_in_selected_chunk_slots": len(block_entities),
            "risk_counts": top_counter(be_risks),
            "flag_counts": top_counter(be_flags),
            "id_counts": top_counter(be_ids),
            "records": sorted(
                block_entities,
                key=lambda row: (
                    {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}.get(row["risk"], 9),
                    row["id"],
                    row.get("pos") or [],
                ),
            ),
        },
        "poi": {
            "total_records": len(pois),
            "type_counts": top_counter(poi_types),
            "records": sorted(pois, key=lambda row: (str(row.get("type")), row.get("pos") or [])),
        },
        "attention_chunks": {
            "count": len(attention_chunks),
            "chunks": [list(row) for row in sorted(attention_chunks)],
            "with_affected_player_position_or_spawn": len(affected_player_chunks),
            "with_critical_entities": len(critical_entity_chunks),
            "with_block_entities": len(block_entity_chunks),
            "with_poi": len(poi_chunks),
        },
        "parse_errors": parse_errors,
        "decision": {
            "user_authorization": "Direct protected terrain/biome replacement is authorized, but this audit does not infer authorization to destroy important objects.",
            "blind_whole_region_copy": "FORBIDDEN: the 40 MCA files include slots outside the selected circle.",
            "terrain_region_policy": "Build each output MCA from C and replace only selected chunk slots with V. For approved salvage exceptions, reapply the minimal supporting blocks plus block-entity NBT after V, or relocate the object.",
            "entity_region_policy": "Keep C entities MCA byte-identical. After V exists, collision-test every preserved entity/player position and relocate only unsafe records with a receipt.",
            "poi_policy": "Do not preserve stale C POI records against V blocks. Use V POI or rebuild POI from final blocks; reconcile surviving villager memories/job sites.",
            "player_policy": "Before first boot, validate current/spawn positions against V surface and collision. Relocate unsafe current positions; clear/rebuild invalid bed/anchor spawn points.",
            "rollback_policy": "Bind every changed selected slot to its C preimage hash and retain the stopped C archive until clone validation and public OTA acceptance are complete.",
        },
        "blockers_to_unattended_apply": blockers,
        "non_actions": {
            "archive_modified": False,
            "world_extracted": False,
            "java_started": False,
            "temporary_region_files_persisted": False,
        },
    }


def markdown(report: Mapping[str, Any], json_path: Path, json_sha256: str) -> str:
    players = report["players"]
    entities = report["entities"]
    block_entities = report["block_entities"]
    poi = report["poi"]
    mca = report["mca"]
    lines = [
        "# 保护区重要对象只读审计（当前公测停服快照）",
        "",
        f"- 生成时间（UTC）：`{report['generated_at_utc']}`",
        f"- 状态：`{report['status']}`",
        f"- 源 ZIP：`{report['source']['archive']}`",
        f"- 源 ZIP SHA-256：`{report['source']['sha256']}`",
        f"- JSON：`{json_path.resolve()}`",
        f"- JSON SHA-256：`{json_sha256}`",
        "- 行为：只读；未展开整个世界；未启动 Java；未修改任何 NBT/MCA。",
        "",
        "## 范围与结论",
        "",
        f"审计中心为 `(10192, -1574)`、半径 `1536`，按“区块 16×16 离散方块中至少一个点与圆相交”的规则严格选中 `{report['scope']['selected_chunks']}` 个区块、`{report['scope']['selected_regions']}` 个 region。",
        "",
        "用户已经授权直接覆盖保护区的群系与地形；但当前快照中仍存在需要先处理的重要对象。因此，授权有效，但不能把它实现成不做例外审计的盲覆盖。",
        "",
        "## 数据概览",
        "",
        "| 类别 | 区内占用 chunk 槽 | 记录数 | 处理结论 |",
        "|---|---:|---:|---|",
        f"| terrain region | {mca['region']['occupied_selected_chunk_slots']:,} | {block_entities['total_in_selected_chunk_slots']:,} 个 block entity | V 替换选中槽；重要对象先迁走或做最小例外 |",
        f"| entities | {mca['entities']['occupied_selected_chunk_slots']:,} | {entities['total_in_selected_chunk_slots_including_nested_passengers']:,} 个实体 | 保持 C 的 entities MCA；生成 V 后做碰撞/承托检查 |",
        f"| POI | {mca['poi']['occupied_selected_chunk_slots']:,} | {poi['total_records']:,} 条 POI | 不保留过期 C POI；按最终方块重建/采用 V |",
        f"| playerdata | — | {len(players['affected_players']):,} 名玩家当前位置或出生点受影响 | 首启前校验并按需安全迁位/重建出生点 |",
        "",
        f"地形槽中已有 `{mca['region']['occupied_selected_chunk_slots']:,}` 个，剩余 `{report['scope']['selected_chunks'] - mca['region']['occupied_selected_chunk_slots']:,}` 个当前为空。只有前者属于破坏性替换，后者是填入 V。",
        "",
        "## 玩家",
        "",
        f"- 当前 `.dat`：{players['current_dat_files']}；成功解析：{players['parsed_current_dat_files']}；`.dat_old`：{players['dat_old_files']}。",
        f"- 当前落在选中区块：{players['current_positions_inside_selected_chunks']}。",
        f"- 出生点落在选中区块：{players['spawn_positions_inside_selected_chunks']}。",
        "",
    ]
    if players["affected_players"]:
        lines.extend(["| 玩家 | UUID | 当前坐标 | 出生点 | OP |", "|---|---|---|---|---|"])
        for row in players["affected_players"]:
            current = row.get("current")
            spawn = row.get("spawn")
            current_text = json.dumps(current.get("pos"), ensure_ascii=False) if isinstance(current, Mapping) and current.get("inside_selected_chunk_set") else "—"
            spawn_text = json.dumps(spawn.get("pos"), ensure_ascii=False) if isinstance(spawn, Mapping) and spawn.get("inside_selected_chunk_set") else "—"
            lines.append(f"| {row.get('name') or '未解析名称'} | `{row['uuid']}` | `{current_text}` | `{spawn_text}` | {'是' if row['is_op'] else '否'} |")
    else:
        lines.append("没有玩家当前位置或出生点落在选中区块内。")
    lines.extend(
        [
            "",
            "## 实体",
            "",
            f"- 风险统计：`{json.dumps(entities['risk_counts'], ensure_ascii=False, sort_keys=True)}`",
            f"- 特征统计：`{json.dumps(entities['flag_counts'], ensure_ascii=False, sort_keys=True)}`",
            "- 所有实体的紧凑坐标清单均在 JSON 的 `entities.records`；其中女仆、命名/驯服/有主人实体、村民、载具、携带物品实体列为 CRITICAL。",
            "- 这里的 CRITICAL 不表示实体数据会被 region 覆盖删除；它表示必须在 V 生成后检查新方块是否让实体窒息、悬空、卡入固体或失去承托。",
            "",
            "实体 ID 计数（前 30 项）：",
            "",
        ]
    )
    for identifier, count in list(entities["id_counts"].items())[:30]:
        lines.append(f"- `{identifier}`：{count}")
    lines.extend(
        [
            "",
            "## 方块实体",
            "",
            f"- 风险统计：`{json.dumps(block_entities['risk_counts'], ensure_ascii=False, sort_keys=True)}`",
            f"- 特征统计：`{json.dumps(block_entities['flag_counts'], ensure_ascii=False, sort_keys=True)}`",
            "- 所有方块实体的坐标、物品/液体摘要、关键路径和建议均在 JSON 的 `block_entities.records`。",
            "- 直接把 terrain chunk 换成 V 会删除其中全部现有 block entity。CRITICAL 对象必须先迁走，或在 V 后连同最小支撑方块一起精确恢复；仅复制 NBT 而不恢复对应方块状态是无效且危险的。",
            "",
            "方块实体 ID 计数（前 40 项）：",
            "",
        ]
    )
    for identifier, count in list(block_entities["id_counts"].items())[:40]:
        lines.append(f"- `{identifier}`：{count}")
    lines.extend(
        [
            "",
            "## POI",
            "",
            f"- POI 类型：`{json.dumps(poi['type_counts'], ensure_ascii=False, sort_keys=True)}`",
            "- POI 必须与最终 V 方块一致，因此不能保留当前 C 的旧记录。若 entities 中保留了村民，还要在克隆服确认其 Brain 中的职业站点/床位记忆与重建后的 POI 一致。",
            "",
            "## 可执行覆盖规则",
            "",
            "1. 绝不能整文件复制 V 的 40 个 region：这些 MCA 同时含有圆外槽位。输出必须以 C 为底，只替换严格选中的 chunk 槽。",
            "2. `region`：选中槽以 V 为准；审核通过的少量重要对象在 V 后迁移/恢复最小方块结构与 block-entity NBT。",
            "3. `entities`：C 原样保留；V 完成后逐坐标做碰撞、液体、地面承托和高度检查，仅迁移不安全对象并记录收据。",
            "4. `poi`：采用 V 或从最终方块重建；不要把 C 的旧 POI 原样拼回去。",
            "5. `playerdata`：首启前检查当前位置和床/重生锚；危险坐标先迁到已验证安全点。",
            "6. 每个修改槽保存 C 的 preimage hash；在克隆服完成结构、实体、登录与回滚验证后再制作 OTA。",
            "",
            f"需关注的并集区块共 `{report['attention_chunks']['count']}` 个，完整坐标见 JSON 的 `attention_chunks.chunks`。",
            "",
            "## 当前未执行",
            "",
            "没有写入存档、没有生成 V、没有启动客户端/服务端、没有制作或发布 OTA。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--temp-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--sha256-manifest", type=Path, required=True)
    parser.add_argument("--center-x", type=int, default=10_192)
    parser.add_argument("--center-z", type=int, default=-1_574)
    parser.add_argument("--radius", type=int, default=1_536)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()

    report = audit_archive(
        args.archive.resolve(),
        args.temp_root.resolve(),
        args.center_x,
        args.center_z,
        args.radius,
        args.expected_sha256,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    args.output_json.write_bytes(payload)
    json_hash = sha256_bytes(payload)
    md_payload = (markdown(report, args.output_json, json_hash) + "\n").encode("utf-8")
    args.output_md.write_bytes(md_payload)
    md_hash = sha256_bytes(md_payload)
    manifest = (
        f"{report['source']['sha256']} *{args.archive.resolve()}\n"
        f"{json_hash} *{args.output_json.resolve()}\n"
        f"{md_hash} *{args.output_md.resolve()}\n"
    )
    args.sha256_manifest.write_text(manifest, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "source_sha256_matches": report["source"]["expected_sha256_matches"],
                "mca": report["mca"],
                "affected_players": len(report["players"]["affected_players"]),
                "entities": report["entities"]["total_in_selected_chunk_slots_including_nested_passengers"],
                "block_entities": report["block_entities"]["total_in_selected_chunk_slots"],
                "poi": report["poi"]["total_records"],
                "attention_chunks": report["attention_chunks"]["count"],
                "parse_errors": len(report["parse_errors"]) + len(report["players"]["parse_errors"]),
                "output_json": str(args.output_json.resolve()),
                "output_md": str(args.output_md.resolve()),
                "sha256_manifest": str(args.sha256_manifest.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["source"]["expected_sha256_matches"] and not report["parse_errors"] and not report["players"]["parse_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
