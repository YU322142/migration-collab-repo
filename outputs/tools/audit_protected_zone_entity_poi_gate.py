#!/usr/bin/env python3
"""Read-only entity collision/support and POI replacement gate.

This tool never writes a Minecraft world, never modifies the source ZIP, and
never starts Java.  It binds the stopped-server object audit to a strict V
terrain reference, checks the 198 current entities at their preserved
positions, and proves the exact POI postcondition required by a donor-selected
slot merge.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import re
import struct
import zlib
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import nbtlib


SCHEMA_VERSION = 1
EXPECTED_ARCHIVE_SHA256 = "ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92"
EXPECTED_OBJECT_AUDIT_SHA256 = "3940CE6CB60FAC9DD37890C3AA74C47A8DBB4CCD7923E3657E0E8590CFADA2A7"
EXPECTED_DISPOSITION_SHA256 = "97E7B0AEF2460B632FDABA774498495F8AB691CF3D4CB428973D6EDDF70039C3"
EXPECTED_CHUNKS = 29_305
EXPECTED_REGIONS = 40
EXPECTED_ENTITIES = 198
EXPECTED_CURRENT_POI_RECORDS = 40
DATA_VERSION = 3955
MIN_Y = -64
MAX_Y = 479
MCA_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


ENTITY_DIMENSIONS: dict[str, tuple[float, float]] = {
    "minecraft:item": (0.25, 0.25),
    "minecraft:mooshroom": (0.90, 1.40),
    "minecraft:drowned": (0.60, 1.95),
    "minecraft:elder_guardian": (2.00, 2.00),
    "minecraft:falling_block": (0.98, 0.98),
    "minecraft:pig": (0.90, 0.90),
    "minecraft:parrot": (0.50, 0.90),
    "minecraft:chicken": (0.40, 0.70),
    "minecraft:panda": (1.30, 1.25),
    # Content Backport adds this 1.21.11 entity to the 1.21.1 runtime.  A
    # conservative two-block body is used because collision certainty matters
    # more than avoiding a false-positive review row.
    "minecraft:zombie_nautilus": (1.40, 1.40),
}

GROUND_REQUIRED = {
    "minecraft:mooshroom",
    "minecraft:pig",
    "minecraft:chicken",
    "minecraft:panda",
}
AQUATIC = {
    "minecraft:drowned",
    "minecraft:elder_guardian",
    "minecraft:zombie_nautilus",
}
FLYING = {"minecraft:parrot"}
PHYSICS_ONLY = {"minecraft:item", "minecraft:falling_block"}

AIR_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
FLUID_BLOCKS = {"minecraft:water", "minecraft:lava", "minecraft:bubble_column"}
PASSABLE_EXACT = {
    "minecraft:short_grass",
    "minecraft:tall_grass",
    "minecraft:fern",
    "minecraft:large_fern",
    "minecraft:dead_bush",
    "minecraft:sugar_cane",
    "minecraft:seagrass",
    "minecraft:tall_seagrass",
    "minecraft:kelp",
    "minecraft:kelp_plant",
    "minecraft:vine",
    "minecraft:cave_vines",
    "minecraft:cave_vines_plant",
    "minecraft:weeping_vines",
    "minecraft:weeping_vines_plant",
    "minecraft:twisting_vines",
    "minecraft:twisting_vines_plant",
    "minecraft:glow_lichen",
    "minecraft:sculk_vein",
    "minecraft:hanging_roots",
    "minecraft:spore_blossom",
    "minecraft:small_dripleaf",
    "minecraft:big_dripleaf_stem",
    "minecraft:torch",
    "minecraft:wall_torch",
    "minecraft:redstone_torch",
    "minecraft:redstone_wall_torch",
    "minecraft:soul_torch",
    "minecraft:soul_wall_torch",
    "minecraft:redstone_wire",
    "minecraft:tripwire",
    "minecraft:lever",
    "minecraft:ladder",
    "minecraft:cobweb",
    "minecraft:fire",
    "minecraft:soul_fire",
    "minecraft:nether_portal",
    "minecraft:end_portal",
    "minecraft:light",
    "minecraft:structure_void",
}
PASSABLE_SUFFIXES = (
    "_sapling",
    "_flower",
    "_tulip",
    "_mushroom",
    "_roots",
    "_sprouts",
    "_bush",
    "_coral_fan",
    "_wall_coral_fan",
    "_torch",
    "_wall_torch",
    "_button",
    "_sign",
    "_wall_sign",
    "_hanging_sign",
    "_banner",
    "_wall_banner",
    "_rail",
    "_carpet",
)
PARTIAL_SUFFIXES = (
    "_slab",
    "_stairs",
    "_fence",
    "_fence_gate",
    "_wall",
    "_door",
    "_trapdoor",
    "_pressure_plate",
    "_bed",
)
PARTIAL_EXACT = {
    "minecraft:snow",
    "minecraft:lily_pad",
    "minecraft:chest",
    "minecraft:trapped_chest",
    "minecraft:ender_chest",
    "minecraft:lectern",
    "minecraft:bell",
    "minecraft:grindstone",
    "minecraft:stonecutter",
    "minecraft:brewing_stand",
    "minecraft:composter",
    "minecraft:cauldron",
    "minecraft:water_cauldron",
    "minecraft:lava_cauldron",
    "minecraft:powder_snow_cauldron",
    "minecraft:chain",
    "minecraft:iron_bars",
    "minecraft:lightning_rod",
    "minecraft:pointed_dripstone",
    "minecraft:big_dripleaf",
    "minecraft:flower_pot",
}
HAZARD_BLOCKS = {
    "minecraft:lava",
    "minecraft:fire",
    "minecraft:soul_fire",
    "minecraft:cactus",
    "minecraft:magma_block",
    "minecraft:sweet_berry_bush",
    "minecraft:wither_rose",
    "minecraft:powder_snow",
    "minecraft:campfire",
    "minecraft:soul_campfire",
    "minecraft:pointed_dripstone",
}

POI_BLOCK_RULES: dict[str, set[str]] = {
    "minecraft:armorer": {"minecraft:blast_furnace"},
    "minecraft:butcher": {"minecraft:smoker"},
    "minecraft:cartographer": {"minecraft:cartography_table"},
    "minecraft:cleric": {"minecraft:brewing_stand"},
    "minecraft:farmer": {"minecraft:composter"},
    "minecraft:fisherman": {"minecraft:barrel"},
    "minecraft:fletcher": {"minecraft:fletching_table"},
    "minecraft:leatherworker": {
        "minecraft:cauldron",
        "minecraft:water_cauldron",
        "minecraft:lava_cauldron",
        "minecraft:powder_snow_cauldron",
    },
    "minecraft:librarian": {"minecraft:lectern"},
    "minecraft:mason": {"minecraft:stonecutter"},
    "minecraft:shepherd": {"minecraft:loom"},
    "minecraft:toolsmith": {"minecraft:smithing_table"},
    "minecraft:weaponsmith": {"minecraft:grindstone"},
    "minecraft:meeting": {"minecraft:bell"},
    "minecraft:bee_nest": {"minecraft:bee_nest"},
    "minecraft:beehive": {"minecraft:beehive"},
    "minecraft:nether_portal": {"minecraft:nether_portal"},
    "minecraft:lodestone": {"minecraft:lodestone"},
    "minecraft:lightning_rod": {"minecraft:lightning_rod"},
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def canonical_nbt_sha(root: Any) -> str:
    payload = json.dumps(plain(root), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def parse_mca_name(path: Path) -> tuple[int, int]:
    match = MCA_RE.fullmatch(path.name)
    if match is None:
        raise ValueError(f"invalid MCA filename: {path}")
    return int(match.group(1)), int(match.group(2))


def slot_for_chunk(chunk_x: int, chunk_z: int) -> int:
    return (chunk_x & 31) + (chunk_z & 31) * 32


def chunk_for_slot(region_x: int, region_z: int, slot: int) -> tuple[int, int]:
    return region_x * 32 + (slot & 31), region_z * 32 + (slot >> 5)


def location_table(path: Path) -> dict[int, tuple[int, int]]:
    with path.open("rb") as stream:
        locations = stream.read(4096)
    if len(locations) != 4096:
        raise ValueError(f"truncated MCA header: {path}")
    result: dict[int, tuple[int, int]] = {}
    for slot in range(1024):
        entry = locations[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if offset:
            if sectors == 0:
                raise ValueError(f"occupied MCA slot has zero sectors: {path} slot {slot}")
            result[slot] = (offset, sectors)
    return result


def read_chunk_record(path: Path, slot: int) -> tuple[bytes, int, bytes]:
    occupied = location_table(path)
    if slot not in occupied:
        raise KeyError(f"missing slot {slot}: {path}")
    offset, sectors = occupied[slot]
    with path.open("rb") as stream:
        stream.seek(offset * 4096)
        length_raw = stream.read(4)
        if len(length_raw) != 4:
            raise ValueError(f"truncated MCA record length: {path} slot {slot}")
        length = struct.unpack(">I", length_raw)[0]
        if length < 1 or length + 4 > sectors * 4096:
            raise ValueError(f"invalid MCA record length: {path} slot {slot}")
        record = length_raw + stream.read(length)
    if len(record) != length + 4:
        raise ValueError(f"truncated MCA record payload: {path} slot {slot}")
    compression = record[4]
    if compression & 0x80:
        raise ValueError(f"external .mcc record is forbidden: {path} slot {slot}")
    return record, compression, record[5:]


def decompress_nbt(compression: int, payload: bytes) -> Any:
    if compression == 1:
        raw = gzip.decompress(payload)
    elif compression == 2:
        raw = zlib.decompress(payload)
    elif compression == 3:
        raw = payload
    else:
        raise ValueError(f"unsupported MCA compression type {compression}")
    return nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def load_chunk(path: Path, slot: int) -> tuple[Any, str]:
    record, compression, payload = read_chunk_record(path, slot)
    return decompress_nbt(compression, payload), sha256_bytes(record)


def state_name(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(plain(value.get("Name", value.get("name", "minecraft:air"))))
    return "minecraft:air"


def state_properties(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    properties = plain(value.get("Properties", value.get("properties", {})))
    if not isinstance(properties, Mapping):
        return {}
    return {str(key): str(child) for key, child in properties.items()}


class VBlockIndex:
    def __init__(self, world: Path) -> None:
        self.world = world
        self._chunks: dict[tuple[int, int], dict[int, tuple[list[Any], list[int]]]] = {}
        self.parse_errors: list[dict[str, Any]] = []

    def load(self, chunk_x: int, chunk_z: int) -> dict[int, tuple[list[Any], list[int]]]:
        key = (chunk_x, chunk_z)
        if key in self._chunks:
            return self._chunks[key]
        region_x, region_z = chunk_x // 32, chunk_z // 32
        path = self.world / "region" / f"r.{region_x}.{region_z}.mca"
        slot = slot_for_chunk(chunk_x, chunk_z)
        root, _record_sha = load_chunk(path, slot)
        body = root.get("Level", root) if isinstance(root, Mapping) else {}
        sections: dict[int, tuple[list[Any], list[int]]] = {}
        raw_sections = body.get("sections", body.get("Sections", [])) if isinstance(body, Mapping) else []
        for section in raw_sections:
            if not isinstance(section, Mapping):
                continue
            section_y = int(plain(section.get("Y", -10_000)))
            states = section.get("block_states", section.get("BlockStates", {}))
            if not isinstance(states, Mapping):
                continue
            palette_raw = states.get("palette", states.get("Palette", []))
            palette = list(palette_raw) if isinstance(palette_raw, Sequence) else []
            data_raw = states.get("data", states.get("Data", []))
            # nbtlib.LongArray wraps a NumPy array and is iterable, but it does
            # not register as collections.abc.Sequence.
            try:
                data = [int(plain(value)) & 0xFFFFFFFFFFFFFFFF for value in data_raw]
            except TypeError:
                data = []
            if palette:
                sections[section_y] = (palette, data)
        self._chunks[key] = sections
        return sections

    def state(self, x: int, y: int, z: int) -> dict[str, Any]:
        if y < MIN_Y or y > MAX_Y:
            return {"name": "minecraft:void_air", "properties": {}}
        chunk_x, chunk_z = x // 16, z // 16
        sections = self.load(chunk_x, chunk_z)
        section_y = y // 16
        if section_y not in sections:
            return {"name": "minecraft:air", "properties": {}}
        palette, data = sections[section_y]
        if len(palette) == 1:
            selected = palette[0]
        else:
            bits = max(4, (len(palette) - 1).bit_length())
            values_per_long = 64 // bits
            local_index = (y & 15) * 256 + (z & 15) * 16 + (x & 15)
            long_index = local_index // values_per_long
            if long_index >= len(data):
                raise ValueError(
                    f"packed block-state data is short for chunk {chunk_x},{chunk_z} section {section_y}"
                )
            shift = (local_index % values_per_long) * bits
            palette_index = (data[long_index] >> shift) & ((1 << bits) - 1)
            if palette_index >= len(palette):
                raise ValueError(
                    f"block-state palette index {palette_index} >= {len(palette)} at {x},{y},{z}"
                )
            selected = palette[palette_index]
        return {"name": state_name(selected), "properties": state_properties(selected)}


def block_class(name: str) -> str:
    bare = name.split(":", 1)[-1]
    if name in AIR_BLOCKS:
        return "air"
    if name in FLUID_BLOCKS:
        return "fluid"
    if name in PASSABLE_EXACT or bare.endswith(PASSABLE_SUFFIXES):
        return "passable"
    if name in PARTIAL_EXACT or bare.endswith(PARTIAL_SUFFIXES):
        return "partial_collision"
    return "solid_or_unknown_collision"


def compact_state(position: tuple[int, int, int], state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "pos": list(position),
        "name": state["name"],
        "properties": state.get("properties", {}),
        "class": block_class(str(state["name"])),
        "hazard": str(state["name"]) in HAZARD_BLOCKS,
    }


def entity_aabb_blocks(pos: Sequence[float], width: float, height: float) -> list[tuple[int, int, int]]:
    epsilon = 1.0e-7
    min_x = math.floor(float(pos[0]) - width / 2 + epsilon)
    max_x = math.floor(float(pos[0]) + width / 2 - epsilon)
    min_y = math.floor(float(pos[1]) + epsilon)
    max_y = math.floor(float(pos[1]) + height - epsilon)
    min_z = math.floor(float(pos[2]) - width / 2 + epsilon)
    max_z = math.floor(float(pos[2]) + width / 2 - epsilon)
    return [
        (x, y, z)
        for y in range(min_y, max_y + 1)
        for z in range(min_z, max_z + 1)
        for x in range(min_x, max_x + 1)
    ]


def support_below(index: VBlockIndex, pos: Sequence[float], limit: int = 128) -> dict[str, Any]:
    x, z = math.floor(float(pos[0])), math.floor(float(pos[2]))
    start_y = math.floor(float(pos[1]) - 1.0e-7)
    fluid_rows: list[dict[str, Any]] = []
    for y in range(start_y, max(MIN_Y - 1, start_y - limit), -1):
        state = index.state(x, y, z)
        name = str(state["name"])
        classification = block_class(name)
        if classification == "fluid":
            if len(fluid_rows) < 8:
                fluid_rows.append(compact_state((x, y, z), state))
            continue
        if classification in {"solid_or_unknown_collision", "partial_collision"}:
            return {
                "found": True,
                "block": compact_state((x, y, z), state),
                "drop_distance": round(float(pos[1]) - (y + 1), 6),
                "searched_blocks": start_y - y + 1,
                "fluids_crossed": fluid_rows,
            }
    return {
        "found": False,
        "block": None,
        "drop_distance": None,
        "searched_blocks": min(limit, start_y - MIN_Y + 1),
        "fluids_crossed": fluid_rows,
    }


def audit_entity(index: VBlockIndex, record: Mapping[str, Any]) -> dict[str, Any]:
    identifier = str(record.get("id", "<missing>"))
    pos = record.get("pos")
    if not isinstance(pos, Sequence) or len(pos) < 3:
        return {
            "id": identifier,
            "uuid": record.get("uuid"),
            "pos": pos,
            "verdict": "BLOCKED_MISSING_POSITION",
            "hard_blockers": ["entity record has no usable position"],
            "review_reasons": [],
        }
    width, height = ENTITY_DIMENSIONS.get(identifier, (1.0, 2.0))
    hard: list[str] = []
    review: list[str] = []
    body_states: list[dict[str, Any]] = []
    try:
        for block_pos in entity_aabb_blocks(pos, width, height):
            state = index.state(*block_pos)
            row = compact_state(block_pos, state)
            if row["class"] != "air" or row["hazard"]:
                body_states.append(row)
        solid = [row for row in body_states if row["class"] == "solid_or_unknown_collision"]
        partial = [row for row in body_states if row["class"] == "partial_collision"]
        hazards = [row for row in body_states if row["hazard"]]
        if solid:
            hard.append(f"AABB intersects {len(solid)} solid-or-unknown V block(s)")
        if partial:
            review.append(f"AABB intersects {len(partial)} partial-shape V block(s); exact engine shape is required")
        if hazards:
            hard.append(f"AABB intersects {len(hazards)} hazardous V block(s)")

        center_x, center_z = math.floor(float(pos[0])), math.floor(float(pos[2]))
        water_samples: list[dict[str, Any]] = []
        for y in sorted({math.floor(float(pos[1])), math.floor(float(pos[1]) + height * 0.5)}):
            state = index.state(center_x, y, center_z)
            if state["name"] in {"minecraft:water", "minecraft:bubble_column"}:
                water_samples.append(compact_state((center_x, y, center_z), state))
        support = support_below(index, pos)

        if identifier in GROUND_REQUIRED:
            drop = support.get("drop_distance")
            if not support.get("found"):
                hard.append("ground-required entity has no support within 128 blocks")
            elif isinstance(drop, (int, float)) and drop > 3.5 and not water_samples:
                hard.append(f"ground-required entity would fall {drop:.3f} blocks onto V terrain")
            elif isinstance(drop, (int, float)) and drop > 0.75:
                review.append(f"ground-required entity has a {drop:.3f}-block support gap")
        elif identifier in AQUATIC:
            if not water_samples:
                review.append("aquatic entity has no water at center feet/body sample in V")
        elif identifier in PHYSICS_ONLY:
            drop = support.get("drop_distance")
            if not support.get("found"):
                review.append("physics entity has no support within 128 blocks")
            elif isinstance(drop, (int, float)) and drop > 20:
                review.append(f"physics entity will fall about {drop:.3f} blocks")
        elif identifier in FLYING:
            pass
        else:
            review.append("unknown entity mobility class was audited conservatively")
    except Exception as exc:  # noqa: BLE001 - gate must fail closed
        hard.append(f"V block lookup failed: {type(exc).__name__}: {exc}")
        support = None
        water_samples = []

    if hard:
        verdict = "BLOCKED"
    elif review:
        verdict = "REVIEW"
    else:
        verdict = "PASS"
    return {
        "id": identifier,
        "uuid": record.get("uuid"),
        "pos": [float(pos[0]), float(pos[1]), float(pos[2])],
        "source_chunk": record.get("source_chunk"),
        "actual_chunk": record.get("actual_chunk"),
        "flags": record.get("flags", []),
        "item_summary": record.get("item_summary", {}),
        "assumed_dimensions": {"width": width, "height": height},
        "body_non_air_or_hazard_blocks": body_states,
        "support": support,
        "water_samples": water_samples,
        "hard_blockers": hard,
        "review_reasons": review,
        "verdict": verdict,
    }


def poi_expected_match(poi_type: str, block_name: str) -> tuple[bool, str]:
    if poi_type == "minecraft:home":
        return block_name.endswith("_bed"), "any minecraft:*_bed"
    expected = POI_BLOCK_RULES.get(poi_type)
    if expected is None:
        return False, "unrecognized POI type"
    return block_name in expected, ",".join(sorted(expected))


def parse_poi_world(world: Path, index: VBlockIndex) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []
    failures: list[str] = []
    type_counts: Counter[str] = Counter()
    invalid_sections = 0
    data_versions: Counter[int] = Counter()
    seen_positions: Counter[tuple[int, int, int]] = Counter()
    poi_dir = world / "poi"
    for path in sorted(poi_dir.glob("r.*.*.mca")):
        region_x, region_z = parse_mca_name(path)
        for slot in sorted(location_table(path)):
            chunk_x, chunk_z = chunk_for_slot(region_x, region_z, slot)
            root, raw_sha = load_chunk(path, slot)
            body = root.get("Level", root) if isinstance(root, Mapping) else {}
            version = int(plain(body.get("DataVersion", root.get("DataVersion", -1))))
            data_versions[version] += 1
            sections = body.get("Sections", {}) if isinstance(body, Mapping) else {}
            slot_records: list[dict[str, Any]] = []
            if not isinstance(sections, Mapping):
                failures.append(f"POI chunk {chunk_x},{chunk_z} Sections is not a compound")
                sections = {}
            for section_key, section in sections.items():
                if not isinstance(section, Mapping):
                    failures.append(f"POI chunk {chunk_x},{chunk_z} section {section_key} is not a compound")
                    continue
                valid = int(plain(section.get("Valid", 0)))
                if valid != 1:
                    invalid_sections += 1
                raw_records = section.get("Records", [])
                if not isinstance(raw_records, Sequence):
                    failures.append(f"POI chunk {chunk_x},{chunk_z} section {section_key} Records is not a list")
                    continue
                for source_index, record in enumerate(raw_records):
                    value = plain(record)
                    if not isinstance(value, Mapping):
                        failures.append(f"POI chunk {chunk_x},{chunk_z} contains a non-compound record")
                        continue
                    pos = value.get("pos")
                    poi_type = str(value.get("type", "<missing>"))
                    free_tickets = value.get("free_tickets")
                    if not isinstance(pos, list) or len(pos) != 3:
                        failures.append(f"POI chunk {chunk_x},{chunk_z} contains an invalid position")
                        continue
                    x, y, z = (int(pos[0]), int(pos[1]), int(pos[2]))
                    actual_chunk = (x // 16, z // 16)
                    section_y = y // 16
                    try:
                        encoded_section_y = int(section_key)
                    except (TypeError, ValueError):
                        encoded_section_y = 10_000_000
                    state = index.state(x, y, z)
                    matches, expected = poi_expected_match(poi_type, str(state["name"]))
                    row_failures: list[str] = []
                    if actual_chunk != (chunk_x, chunk_z):
                        row_failures.append(f"record position belongs to chunk {actual_chunk[0]},{actual_chunk[1]}")
                    if encoded_section_y != section_y:
                        row_failures.append(f"section key {section_key} != position section {section_y}")
                    if not matches:
                        row_failures.append(f"V block {state['name']} does not match expected {expected}")
                    if not isinstance(free_tickets, int) or free_tickets < 0:
                        row_failures.append(f"invalid free_tickets {free_tickets!r}")
                    seen_positions[(x, y, z)] += 1
                    type_counts[poi_type] += 1
                    row = {
                        "type": poi_type,
                        "pos": [x, y, z],
                        "free_tickets": free_tickets,
                        "chunk": [chunk_x, chunk_z],
                        "section_y": section_y,
                        "source_section": str(section_key),
                        "source_index": source_index,
                        "v_block": state,
                        "expected_block_rule": expected,
                        "block_matches_type": matches,
                        "failures": row_failures,
                    }
                    slot_records.append(row)
                    records.append(row)
            slots.append(
                {
                    "chunk": [chunk_x, chunk_z],
                    "region": [region_x, region_z],
                    "slot": slot,
                    "source": str(path),
                    "raw_record_sha256": raw_sha,
                    "semantic_nbt_sha256": canonical_nbt_sha(root),
                    "record_count": len(slot_records),
                    "record_failures": sum(bool(row["failures"]) for row in slot_records),
                }
            )
    duplicate_positions = [list(pos) + [count] for pos, count in sorted(seen_positions.items()) if count > 1]
    row_failures = [row for row in records if row["failures"]]
    if invalid_sections:
        failures.append(f"POI sections with Valid != 1: {invalid_sections}")
    if row_failures:
        failures.append(f"POI records inconsistent with V terrain/coordinates: {len(row_failures)}")
    if duplicate_positions:
        failures.append(f"duplicate POI positions: {len(duplicate_positions)}")
    if data_versions != Counter({DATA_VERSION: len(slots)}):
        failures.append(f"POI DataVersion distribution drift: {dict(data_versions)}")
    return {
        "status": "PASS" if not failures else "BLOCKED",
        "failures": failures,
        "occupied_selected_slots": len(slots),
        "records": len(records),
        "type_counts": dict(sorted(type_counts.items())),
        "data_versions": dict(sorted(data_versions.items())),
        "invalid_sections": invalid_sections,
        "duplicate_positions": duplicate_positions,
        "record_failures": row_failures,
        "selected_slot_fingerprints": slots,
        "record_rows": records,
    }


def audit_current_poi_against_v(
    current_records: Sequence[Mapping[str, Any]],
    donor_rows: Sequence[Mapping[str, Any]],
    index: VBlockIndex,
) -> dict[str, Any]:
    donor_set = {(tuple(row["pos"]), row["type"]) for row in donor_rows}
    rows: list[dict[str, Any]] = []
    for record in current_records:
        pos = record.get("pos")
        if not isinstance(pos, Sequence) or len(pos) != 3:
            rows.append({"source_record": plain(record), "failures": ["invalid current POI position"]})
            continue
        x, y, z = int(pos[0]), int(pos[1]), int(pos[2])
        poi_type = str(record.get("type", "<missing>"))
        state = index.state(x, y, z)
        block_match, expected = poi_expected_match(poi_type, str(state["name"]))
        exists_in_donor = ((x, y, z), poi_type) in donor_set
        rows.append(
            {
                "type": poi_type,
                "pos": [x, y, z],
                "current_source": record.get("source"),
                "current_slot": record.get("slot"),
                "v_block": state,
                "expected_block_rule": expected,
                "v_block_matches_current_poi_type": block_match,
                "same_record_exists_in_v_donor": exists_in_donor,
                "disposition": "REPLACED_BY_V_DONOR" if not exists_in_donor else "IDENTICAL_V_RECORD_REMAINS",
            }
        )
    return {
        "records": len(rows),
        "identical_records_in_v_donor": sum(row.get("same_record_exists_in_v_donor", False) for row in rows),
        "records_replaced_or_removed": sum(not row.get("same_record_exists_in_v_donor", False) for row in rows),
        "current_records_whose_type_still_matches_v_block": sum(
            row.get("v_block_matches_current_poi_type", False) for row in rows
        ),
        "rows": rows,
    }


def markdown(report: Mapping[str, Any]) -> str:
    entity = report["entity_gate"]
    poi = report["poi_gate"]
    current_poi = poi["current_to_v_disposition"]
    lines = [
        "# 保护区实体碰撞 / 支撑与 POI 只读闸门（2026-08-15）",
        "",
        f"**总状态：{report['status']}**",
        "",
        "本闸门没有修改服务端 ZIP、C 世界或 V 世界，也没有启动 Java。它验证的是：在 29,305 个保护区槽位直接换成 V 地形后，继续逐字保留 C 的实体 MCA 是否安全，以及 POI 必须怎样随 V 一起替换。",
        "",
        "## 实体闸门",
        "",
        f"- 审计实体：{entity['entities']}（要求 {EXPECTED_ENTITIES}）",
        f"- PASS：{entity['verdict_counts'].get('PASS', 0)}",
        f"- REVIEW：{entity['verdict_counts'].get('REVIEW', 0)}",
        f"- BLOCKED：{entity['verdict_counts'].get('BLOCKED', 0)}",
        f"- 硬阻断实体：{entity['hard_blocker_entities']}；人工复核实体：{entity['review_entities']}",
        "",
    ]
    if entity["status"] == "PASS":
        lines.append("实体按 C 的 MCA 原字节保留可通过此静态闸门。")
    else:
        lines.extend(
            [
                "当前的“实体 MCA 原字节不动”策略不能直接通过。必须在以下二者中明确选择并另行验证：",
                "",
                "1. 保留实体 NBT 载荷但只改阻断实体的位置，并重新生成实体槽；或",
                "2. 放弃保护区内这些非玩家、非命名、非驯服实体，采用 V 的实体槽/空槽。",
                "",
                "在这个决定前，不应把地形 OTA 标记为可无人值守发布。",
            ]
        )
    lines.extend(
        [
            "",
            "## POI 闸门",
            "",
            f"- V 中占用的保护区 POI 槽：{poi['donor']['occupied_selected_slots']}",
            f"- V POI 记录：{poi['donor']['records']}",
            f"- V POI 类型/方块/坐标一致性：{poi['donor']['status']}",
            f"- C 的旧 POI：{current_poi['records']}；会被替换或删除：{current_poi['records_replaced_or_removed']}；与 V 完全相同：{current_poi['identical_records_in_v_donor']}",
            f"- donor-selected 后必须为空的保护区 POI 槽：{poi['expected_absent_selected_slots']}",
            "",
            "POI 的正确 OTA 规则是：保护区每个选中槽完全取 V；V 没有该槽时必须删除 C 的旧槽。区外槽保持 C。发布后要按 JSON 内的 `selected_slot_fingerprints` 逐槽核对。",
            "",
            "## 证据绑定",
            "",
            f"- C ZIP SHA-256：`{report['inputs']['source_archive']['sha256']}`",
            f"- 对象审计 SHA-256：`{report['inputs']['object_audit']['sha256']}`",
            f"- 对象处置 SHA-256：`{report['inputs']['object_disposition']['sha256']}`",
            f"- V strict audit：`{report['inputs']['v_strict_audit']['sha256']}`（{report['inputs']['v_strict_audit']['status']}）",
            "",
            "具体阻断实体、相交方块、支撑距离、V POI 槽指纹和旧 POI 去向均在同名 JSON 中。",
            "",
        ]
    )
    return "\n".join(lines)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    source_zip = args.source_zip.resolve()
    object_audit_path = args.object_audit.resolve()
    disposition_path = args.object_disposition.resolve()
    v_world = args.v_world.resolve()
    trim_path = args.v_trim_report.resolve()
    strict_audit_path = args.v_strict_audit.resolve()
    for path in (source_zip, object_audit_path, disposition_path, v_world, trim_path, strict_audit_path):
        if not path.exists():
            raise FileNotFoundError(path)

    source_sha = sha256_file(source_zip)
    object_sha = sha256_file(object_audit_path)
    disposition_sha = sha256_file(disposition_path)
    trim_sha = sha256_file(trim_path)
    strict_sha = sha256_file(strict_audit_path)
    input_failures: list[str] = []
    if source_sha != EXPECTED_ARCHIVE_SHA256:
        input_failures.append(f"source archive SHA drift: {source_sha}")
    if object_sha != EXPECTED_OBJECT_AUDIT_SHA256:
        input_failures.append(f"object audit SHA drift: {object_sha}")
    if disposition_sha != EXPECTED_DISPOSITION_SHA256:
        input_failures.append(f"object disposition SHA drift: {disposition_sha}")

    object_audit = json_load(object_audit_path)
    disposition = json_load(disposition_path)
    trim = json_load(trim_path)
    strict_audit = json_load(strict_audit_path)
    if object_audit.get("source", {}).get("sha256") != source_sha:
        input_failures.append("object audit is not bound to the current source ZIP SHA")
    if disposition.get("inputs", {}).get("source_archive_sha256_bound_by_raw_audit") != source_sha:
        input_failures.append("object disposition is not bound to the current source ZIP SHA")
    if trim.get("status") != "PASS":
        input_failures.append(f"V trim report is not PASS: {trim.get('status')}")
    if strict_audit.get("status") != "PASS":
        input_failures.append(f"V strict audit is not PASS: {strict_audit.get('status')}")
    target = strict_audit.get("target", {})
    if (target.get("chunks"), target.get("regions"), target.get("missing_terrain_chunks"), target.get("extra_terrain_chunks")) != (
        EXPECTED_CHUNKS,
        EXPECTED_REGIONS,
        0,
        0,
    ):
        input_failures.append(f"V strict target drift: {target}")

    v_file_hash_failures: list[dict[str, str]] = []
    for kind in ("region", "poi"):
        for row in strict_audit.get("mca", {}).get(kind, {}).get("manifest", []):
            path = Path(row["path"])
            actual = sha256_file(path)
            if actual != row.get("sha256"):
                v_file_hash_failures.append({"path": str(path), "expected": row.get("sha256"), "actual": actual})
    if v_file_hash_failures:
        input_failures.append(f"V MCA files changed after strict audit: {len(v_file_hash_failures)}")

    records = object_audit.get("entities", {}).get("records", [])
    if len(records) != EXPECTED_ENTITIES:
        input_failures.append(f"entity record count {len(records)} != {EXPECTED_ENTITIES}")
    current_poi_records = object_audit.get("poi", {}).get("records", [])
    if len(current_poi_records) != EXPECTED_CURRENT_POI_RECORDS:
        input_failures.append(f"current POI record count {len(current_poi_records)} != {EXPECTED_CURRENT_POI_RECORDS}")

    index = VBlockIndex(v_world)
    entity_rows = [audit_entity(index, record) for record in records]
    verdict_counts = Counter(row["verdict"] for row in entity_rows)
    entity_id_counts = Counter(row["id"] for row in entity_rows)
    hard_rows = [row for row in entity_rows if row["verdict"] == "BLOCKED"]
    review_rows = [row for row in entity_rows if row["verdict"] == "REVIEW"]
    hard_id_counts = Counter(row["id"] for row in hard_rows)
    review_id_counts = Counter(row["id"] for row in review_rows)

    donor_poi = parse_poi_world(v_world, index)
    current_to_v = audit_current_poi_against_v(current_poi_records, donor_poi["record_rows"], index)
    expected_absent = EXPECTED_CHUNKS - donor_poi["occupied_selected_slots"]
    if donor_poi["occupied_selected_slots"] != strict_audit.get("mca", {}).get("poi", {}).get("occupied_chunks"):
        donor_poi["failures"].append("POI occupied-slot count differs from V strict audit")
        donor_poi["status"] = "BLOCKED"

    entity_status = "PASS" if not hard_rows and not review_rows else "BLOCKED"
    entity_blocker = (
        f"byte-identical C entity preservation is unsafe without relocation/policy: "
        f"{len(hard_rows)} blocked, {len(review_rows)} review"
    )
    blocking_conditions = list(input_failures)
    if donor_poi["status"] != "PASS":
        blocking_conditions.append("V donor POI semantic gate failed")
    if entity_status != "PASS":
        blocking_conditions.append(entity_blocker)
    if input_failures:
        overall = "BLOCKED_INPUT_GATE"
    elif donor_poi["status"] != "PASS":
        overall = "BLOCKED_POI_GATE"
    elif entity_status != "PASS":
        overall = "BLOCKED_ENTITY_RELOCATION_OR_POLICY_REQUIRED"
    else:
        overall = "PASS"

    donor_poi_public = dict(donor_poi)
    donor_poi_public.pop("record_rows", None)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": overall,
        "operation": "protected-zone-entity-collision-support-and-poi-donor-selected-gate-readonly",
        "inputs": {
            "source_archive": {
                "path": str(source_zip),
                "bytes": source_zip.stat().st_size,
                "sha256": source_sha,
                "expected_sha256": EXPECTED_ARCHIVE_SHA256,
                "matches_expected": source_sha == EXPECTED_ARCHIVE_SHA256,
            },
            "object_audit": {
                "path": str(object_audit_path),
                "sha256": object_sha,
                "expected_sha256": EXPECTED_OBJECT_AUDIT_SHA256,
                "matches_expected": object_sha == EXPECTED_OBJECT_AUDIT_SHA256,
            },
            "object_disposition": {
                "path": str(disposition_path),
                "sha256": disposition_sha,
                "expected_sha256": EXPECTED_DISPOSITION_SHA256,
                "matches_expected": disposition_sha == EXPECTED_DISPOSITION_SHA256,
            },
            "v_world": str(v_world),
            "v_trim_report": {"path": str(trim_path), "sha256": trim_sha, "status": trim.get("status")},
            "v_strict_audit": {
                "path": str(strict_audit_path),
                "sha256": strict_sha,
                "status": strict_audit.get("status"),
            },
            "v_file_hash_failures": v_file_hash_failures,
        },
        "scope": {
            "dimension": "minecraft:overworld",
            "center": {"x": 10192, "z": -1574},
            "radius_blocks": 1536,
            "selected_chunks": EXPECTED_CHUNKS,
            "selected_regions": EXPECTED_REGIONS,
            "v_data_version": DATA_VERSION,
            "v_min_y": MIN_Y,
            "v_max_build_y": MAX_Y,
        },
        "input_gate_failures": input_failures,
        "blocking_conditions": blocking_conditions,
        "entity_gate": {
            "status": entity_status,
            "policy_under_test": "preserve all current C entity MCA bytes exactly while replacing selected terrain slots with V",
            "entities": len(entity_rows),
            "entity_id_counts": dict(sorted(entity_id_counts.items())),
            "verdict_counts": dict(sorted(verdict_counts.items())),
            "hard_blocker_entities": len(hard_rows),
            "review_entities": len(review_rows),
            "hard_blocker_id_counts": dict(sorted(hard_id_counts.items())),
            "review_id_counts": dict(sorted(review_id_counts.items())),
            "method": {
                "body": "conservative entity AABB over decoded V block states; full/unknown collision is hard-blocked, partial shapes require review",
                "support": "center-column nearest collision-bearing V block within 128 blocks",
                "ground_required_hard_limit_blocks": 3.5,
                "aquatic": "water sampled at center feet and half-height; dry placement is review, not automatically fatal",
                "limitations": [
                    "This is a static NBT/block-state gate, not a live NeoForge collision-shape simulation.",
                    "Partial block shapes, entity poses, baby scaling, and mod hooks require live clone verification after any relocation policy.",
                    "The zombie_nautilus dimensions are conservative because the entity is supplied by Content Backport.",
                ],
            },
            "blocked_rows": hard_rows,
            "review_rows": review_rows,
            "all_rows": entity_rows,
            "required_resolution_if_blocked": [
                "payload-preserving relocation of blocked/review entities followed by entity-slot rebuild and live clone test",
                "or explicit policy to discard selected current entities and use V/empty selected entity slots",
            ],
        },
        "poi_gate": {
            "status": donor_poi["status"],
            "policy": "for every selected chunk, take the V POI slot; if V has no slot, remove C's selected POI slot; preserve outside slots from C",
            "donor": donor_poi_public,
            "current_to_v_disposition": current_to_v,
            "expected_absent_selected_slots": expected_absent,
            "post_apply_assertions": [
                f"selected occupied POI chunk set is exactly the {donor_poi['occupied_selected_slots']} chunks listed in selected_slot_fingerprints",
                f"the other {expected_absent} selected POI slots are absent",
                "each occupied selected slot raw record and semantic NBT hash equals its V fingerprint",
                "every V POI record still points at its matching V block state",
                "outside-selected POI raw records/timestamps remain byte-identical to C",
            ],
        },
        "non_actions": {
            "source_archive_modified": False,
            "source_world_extracted": False,
            "v_world_modified": False,
            "java_started": False,
            "minecraft_world_written": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source-zip", type=Path, required=True)
    result.add_argument("--object-audit", type=Path, required=True)
    result.add_argument("--object-disposition", type=Path, required=True)
    result.add_argument("--v-world", type=Path, required=True)
    result.add_argument("--v-trim-report", type=Path, required=True)
    result.add_argument("--v-strict-audit", type=Path, required=True)
    result.add_argument("--output-json", type=Path, required=True)
    result.add_argument("--output-md", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = build_report(args)
    json_write(args.output_json, report)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown(report), encoding="utf-8")
    sha_path = args.output_json.with_suffix(".sha256")
    rows = []
    for path in (args.source_zip.resolve(), args.object_audit.resolve(), args.object_disposition.resolve(), args.output_json.resolve(), args.output_md.resolve(), Path(__file__).resolve()):
        rows.append(f"{sha256_file(path)} *{path}")
    sha_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "entity": report["entity_gate"]["status"],
                "poi": report["poi_gate"]["status"],
                "output_json": str(args.output_json.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
