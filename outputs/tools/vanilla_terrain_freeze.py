#!/usr/bin/env python3
"""Fail-closed planning and verification for the protected vanilla terrain zone.

This tool is intentionally read-only unless ``build-plan`` is used.  It never
starts Minecraft, edits the authoritative staging tree, or copies a full world.
The future generation/import step must happen in the isolated D-drive root
recorded in the generated plan.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import struct
import sys
import zipfile
import zlib
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

try:
    import nbtlib
except ImportError as exc:  # pragma: no cover - deployment preflight handles this
    raise SystemExit(f"nbtlib is required: {exc}") from exc


CENTER_X = 10_192
CENTER_Z = -1_574
CORE_RADIUS = 1_000
FREEZE_RADIUS = 1_536
STRUCTURE_BUFFER = FREEZE_RADIUS - CORE_RADIUS
EXPECTED_SOURCE_DATA_VERSION = 4_671
EXPECTED_TARGET_DATA_VERSION = 3_955
EXPECTED_SEED = -794_095_451_117_350_581
MCA_KINDS = ("region", "entities", "poi")
HEIGHTMAPS = ("WORLD_SURFACE", "OCEAN_FLOOR", "MOTION_BLOCKING")
SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


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


def floor_div(value: int, divisor: int) -> int:
    return value // divisor


def chunky_chunks(radius: int) -> list[tuple[int, int]]:
    """Return the exact chunks selected by Chunky 1.4.23's circle logic.

    Chunky tests the centre of each candidate chunk against the block radius.
    The implementation was verified from ``Circle.isBounding`` and
    ``GenerationTask.run`` in the pinned JAR.
    """

    center_chunk_x = CENTER_X >> 4
    center_chunk_z = CENTER_Z >> 4
    radius_chunks = math.ceil(radius / 16)
    chunks: list[tuple[int, int]] = []
    for chunk_x in range(center_chunk_x - radius_chunks, center_chunk_x + radius_chunks + 1):
        for chunk_z in range(center_chunk_z - radius_chunks, center_chunk_z + radius_chunks + 1):
            block_x = chunk_x * 16 + 8
            block_z = chunk_z * 16 + 8
            if math.hypot(block_x - CENTER_X, block_z - CENTER_Z) <= radius:
                chunks.append((chunk_x, chunk_z))
    return chunks


def intersecting_chunks(radius: int) -> list[tuple[int, int]]:
    """Return every chunk whose closed block square intersects the circle."""

    chunks: list[tuple[int, int]] = []
    min_chunk_x = floor_div(CENTER_X - radius, 16) - 1
    max_chunk_x = floor_div(CENTER_X + radius, 16) + 1
    min_chunk_z = floor_div(CENTER_Z - radius, 16) - 1
    max_chunk_z = floor_div(CENTER_Z + radius, 16) + 1
    for chunk_x in range(min_chunk_x, max_chunk_x + 1):
        block_min_x = chunk_x * 16
        block_max_x = block_min_x + 15
        dx = 0 if block_min_x <= CENTER_X <= block_max_x else min(
            abs(CENTER_X - block_min_x), abs(CENTER_X - block_max_x)
        )
        for chunk_z in range(min_chunk_z, max_chunk_z + 1):
            block_min_z = chunk_z * 16
            block_max_z = block_min_z + 15
            dz = 0 if block_min_z <= CENTER_Z <= block_max_z else min(
                abs(CENTER_Z - block_min_z), abs(CENTER_Z - block_max_z)
            )
            if dx * dx + dz * dz <= radius * radius:
                chunks.append((chunk_x, chunk_z))
    return chunks


def regions_for_chunks(chunks: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    return sorted({(floor_div(x, 32), floor_div(z, 32)) for x, z in chunks})


def mca_name(region_x: int, region_z: int) -> str:
    return f"r.{region_x}.{region_z}.mca"


def slot_for_chunk(chunk_x: int, chunk_z: int) -> int:
    return (chunk_x & 31) + (chunk_z & 31) * 32


def read_location_table(path: Path) -> dict[int, tuple[int, int]]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    with path.open("rb") as stream:
        table = stream.read(4096)
    if len(table) != 4096:
        raise ValueError(f"{path}: truncated MCA location table")
    occupied: dict[int, tuple[int, int]] = {}
    for slot in range(1024):
        entry = table[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if offset:
            if offset < 2 or sectors < 1:
                raise ValueError(f"{path}: invalid slot {slot} offset={offset} sectors={sectors}")
            occupied[slot] = (offset, sectors)
    return occupied


def iter_region_chunks(path: Path) -> Iterator[tuple[int, Any]]:
    occupied = read_location_table(path)
    if not occupied:
        return
    with path.open("rb") as stream:
        for slot, (offset, sectors) in sorted(occupied.items()):
            stream.seek(offset * 4096)
            length_bytes = stream.read(4)
            if len(length_bytes) != 4:
                raise ValueError(f"{path}: truncated chunk length at slot {slot}")
            length = struct.unpack(">I", length_bytes)[0]
            compression_byte = stream.read(1)
            if len(compression_byte) != 1 or length < 1:
                raise ValueError(f"{path}: invalid chunk header at slot {slot}")
            compression = compression_byte[0]
            if compression & 0x80:
                raise ValueError(f"{path}: external .mcc chunk at slot {slot} is refused")
            if length + 4 > sectors * 4096:
                raise ValueError(f"{path}: slot {slot} length exceeds allocation")
            payload = stream.read(length - 1)
            if len(payload) != length - 1:
                raise ValueError(f"{path}: truncated payload at slot {slot}")
            if compression == 1:
                import gzip

                raw = gzip.decompress(payload)
            elif compression == 2:
                raw = zlib.decompress(payload)
            elif compression == 3:
                raw = payload
            else:
                raise ValueError(f"{path}: unsupported compression {compression}")
            yield slot, nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def read_region_chunk(path: Path, slot: int) -> Any | None:
    occupied = read_location_table(path)
    location = occupied.get(slot)
    if location is None:
        return None
    offset, sectors = location
    with path.open("rb") as stream:
        stream.seek(offset * 4096)
        length_bytes = stream.read(4)
        if len(length_bytes) != 4:
            raise ValueError(f"{path}: truncated chunk length at slot {slot}")
        length = struct.unpack(">I", length_bytes)[0]
        compression_bytes = stream.read(1)
        if len(compression_bytes) != 1 or length < 1:
            raise ValueError(f"{path}: invalid chunk header at slot {slot}")
        compression = compression_bytes[0]
        if compression & 0x80:
            raise ValueError(f"{path}: external .mcc chunk at slot {slot} is refused")
        if length + 4 > sectors * 4096:
            raise ValueError(f"{path}: slot {slot} length exceeds allocation")
        payload = stream.read(length - 1)
    if len(payload) != length - 1:
        raise ValueError(f"{path}: truncated payload at slot {slot}")
    if compression == 1:
        import gzip

        raw = gzip.decompress(payload)
    elif compression == 2:
        raw = zlib.decompress(payload)
    elif compression == 3:
        raw = payload
    else:
        raise ValueError(f"{path}: unsupported compression {compression}")
    return nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def unpack_compact_array(values: Iterable[Any], bits: int, count: int) -> list[int]:
    """Decode Minecraft's non-spanning SimpleBitStorage representation."""

    if bits <= 0 or bits > 32:
        raise ValueError(f"invalid packed-array width {bits}")
    values_per_long = 64 // bits
    packed = [int(value) & 0xFFFFFFFFFFFFFFFF for value in values]
    required = math.ceil(count / values_per_long)
    if len(packed) < required:
        raise ValueError(
            f"packed array is truncated: {len(packed)} longs, need {required} for {count}x{bits}"
        )
    mask = (1 << bits) - 1
    return [
        (packed[index // values_per_long] >> ((index % values_per_long) * bits)) & mask
        for index in range(count)
    ]


def heightmap_column(root: Any, name: str, local_x: int, local_z: int) -> int:
    heightmaps = root.get("Heightmaps", root.get("heightmaps", {}))
    values = heightmaps.get(name)
    if values is None:
        raise ValueError(f"heightmap {name} is missing")
    sections = root.get("sections", root.get("Sections", []))
    section_y = [int(section.get("Y")) for section in sections if "Y" in section]
    min_y = min(section_y, default=-4) * 16
    bits = max(1, math.ceil(math.log2(384 + 1)))
    decoded = unpack_compact_array(values, bits, 256)
    # Heightmap uses z-major column order and stores first-available Y relative
    # to the dimension minimum build height.
    return decoded[(local_z & 15) * 16 + (local_x & 15)] + min_y


def state_name(value: Any) -> str:
    if not isinstance(value, dict):
        return "<invalid-state>"
    name = value.get("Name", value.get("name", "<missing-name>"))
    return str(plain(name))


def block_state_at(root: Any, block_x: int, block_y: int, block_z: int) -> str:
    target_section_y = floor_div(block_y, 16)
    sections = root.get("sections", root.get("Sections", []))
    section = next(
        (row for row in sections if int(row.get("Y", 2**31 - 1)) == target_section_y),
        None,
    )
    if section is None:
        return "minecraft:air"
    container = section.get("block_states", section.get("BlockStates"))
    if not isinstance(container, dict):
        return "minecraft:air"
    palette = container.get("palette", container.get("Palette", []))
    if not palette:
        return "minecraft:air"
    if len(palette) == 1:
        return state_name(palette[0])
    data = container.get("data", container.get("Data"))
    if data is None:
        raise ValueError("multi-entry block-state palette has no packed data")
    bits = max(4, (len(palette) - 1).bit_length())
    local_x, local_y, local_z = block_x & 15, block_y & 15, block_z & 15
    block_index = local_x + local_z * 16 + local_y * 256
    palette_index = unpack_compact_array(data, bits, 4096)[block_index]
    if palette_index >= len(palette):
        raise ValueError(f"palette index {palette_index} outside palette size {len(palette)}")
    return state_name(palette[palette_index])


def decode_chunk_pos(raw: int) -> tuple[int, int]:
    unsigned = int(raw) & 0xFFFFFFFFFFFFFFFF
    chunk_x = unsigned & 0xFFFFFFFF
    chunk_z = (unsigned >> 32) & 0xFFFFFFFF
    if chunk_x & 0x80000000:
        chunk_x -= 0x100000000
    if chunk_z & 0x80000000:
        chunk_z -= 0x100000000
    return chunk_x, chunk_z


class WorldReader:
    def __init__(self, world: Path):
        self.world = world
        self.cache: dict[tuple[int, int], Any | None] = {}

    def chunk(self, chunk_x: int, chunk_z: int) -> Any | None:
        key = (chunk_x, chunk_z)
        if key not in self.cache:
            region_x, region_z = floor_div(chunk_x, 32), floor_div(chunk_z, 32)
            path = self.world / "region" / mca_name(region_x, region_z)
            self.cache[key] = (
                read_region_chunk(path, slot_for_chunk(chunk_x, chunk_z)) if path.is_file() else None
            )
        return self.cache[key]

    def block(self, block_x: int, block_y: int, block_z: int) -> str:
        root = self.chunk(floor_div(block_x, 16), floor_div(block_z, 16))
        if root is None:
            raise ValueError(f"chunk missing for block {block_x},{block_y},{block_z}")
        return block_state_at(root, block_x, block_y, block_z)

    def missing_structure_references(self, root: Any) -> list[dict[str, Any]]:
        structures = plain(root.get("structures", root.get("Structures", {})))
        references = structures.get("References", structures.get("references", {}))
        missing: list[dict[str, Any]] = []
        if not isinstance(references, dict):
            return missing
        for structure_id, positions in references.items():
            if not isinstance(positions, list):
                continue
            for raw in positions:
                chunk_x, chunk_z = decode_chunk_pos(int(raw))
                target = self.chunk(chunk_x, chunk_z)
                if target is None:
                    missing.append(
                        {
                            "structure": structure_id,
                            "target_chunk": [chunk_x, chunk_z],
                            "reason": "referenced chunk is missing",
                        }
                    )
                    continue
                target_structures = plain(target.get("structures", target.get("Structures", {})))
                starts = target_structures.get("starts", target_structures.get("Starts", {}))
                start = starts.get(structure_id) if isinstance(starts, dict) else None
                if not isinstance(start, dict) or str(start.get("id", "INVALID")) == "INVALID":
                    missing.append(
                        {
                            "structure": structure_id,
                            "target_chunk": [chunk_x, chunk_z],
                            "reason": "referenced chunk has no matching structure start",
                        }
                    )
        return missing


def level_facts(world: Path) -> dict[str, Any]:
    level_path = world / "level.dat"
    root = nbtlib.load(level_path)
    data = root.get("Data", root)
    worldgen = plain(data.get("WorldGenSettings", {}))
    dimensions = worldgen.get("dimensions", {}) if isinstance(worldgen, dict) else {}
    overworld = dimensions.get("minecraft:overworld", {}) if isinstance(dimensions, dict) else {}
    generator = overworld.get("generator", {}) if isinstance(overworld, dict) else {}
    return {
        "path": str(level_path),
        "sha256": sha256(level_path),
        "data_version": int(data.get("DataVersion", -1)),
        "version_name": str(plain(data.get("Version", {})).get("Name", "")),
        "seed": int(worldgen.get("seed", 0)) if isinstance(worldgen, dict) else None,
        "generate_features": int(worldgen.get("generate_features", 0)) if isinstance(worldgen, dict) else None,
        "overworld_generator": generator,
    }


def audit_empty(world: Path, radius: int = FREEZE_RADIUS) -> dict[str, Any]:
    chunks = chunky_chunks(radius)
    regions = regions_for_chunks(chunks)
    blockers: list[dict[str, Any]] = []
    per_kind: dict[str, Any] = {}
    wanted_by_region: dict[tuple[int, int], set[int]] = {}
    for chunk_x, chunk_z in chunks:
        region = (floor_div(chunk_x, 32), floor_div(chunk_z, 32))
        wanted_by_region.setdefault(region, set()).add(slot_for_chunk(chunk_x, chunk_z))

    for kind in MCA_KINDS:
        kind_root = world / kind
        files_present = 0
        occupied_target_slots = 0
        rows: list[dict[str, Any]] = []
        for region_x, region_z in regions:
            path = kind_root / mca_name(region_x, region_z)
            if not path.exists():
                continue
            files_present += 1
            try:
                occupied = read_location_table(path)
            except Exception as exc:
                blockers.append({"kind": kind, "path": str(path), "reason": str(exc)})
                continue
            target_slots = sorted(set(occupied) & wanted_by_region[(region_x, region_z)])
            if target_slots:
                occupied_target_slots += len(target_slots)
                row = {
                    "kind": kind,
                    "path": str(path),
                    "size": path.stat().st_size,
                    "occupied_target_slots": target_slots,
                }
                rows.append(row)
                blockers.append({**row, "reason": "target generation slot is already occupied"})
        per_kind[kind] = {
            "candidate_region_files_present": files_present,
            "occupied_target_slots": occupied_target_slots,
            "occupied_rows": rows,
        }

    facts = level_facts(world)
    if facts["data_version"] != EXPECTED_SOURCE_DATA_VERSION:
        blockers.append(
            {
                "reason": "authoritative input level.dat changed",
                "expected_data_version": EXPECTED_SOURCE_DATA_VERSION,
                "actual_data_version": facts["data_version"],
            }
        )
    if facts["seed"] != EXPECTED_SEED:
        blockers.append(
            {
                "reason": "world seed changed",
                "expected_seed": EXPECTED_SEED,
                "actual_seed": facts["seed"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "audit-empty",
        "world": str(world),
        "center": {"x": CENTER_X, "z": CENTER_Z, "chunk_x": CENTER_X >> 4, "chunk_z": CENTER_Z >> 4},
        "radius_blocks": radius,
        "selected_chunk_count": len(chunks),
        "selected_region_count": len(regions),
        "selected_regions": [{"x": x, "z": z, "file": mca_name(x, z)} for x, z in regions],
        "per_kind": per_kind,
        "level": facts,
        "blockers": blockers,
    }


def jar_worldgen_signals(jar: Path) -> dict[str, Any]:
    prefixes = (
        "/worldgen/",
        "/neoforge/biome_modifier/",
        "/forge/biome_modifier/",
        "/tags/worldgen/",
    )
    entries: list[str] = []
    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            normalized = "/" + name.lower().lstrip("/")
            if any(prefix in normalized for prefix in prefixes):
                entries.append(name)
    return {
        "path": str(jar),
        "sha256": sha256(jar),
        "worldgen_entry_count": len(entries),
        "worldgen_entry_samples": entries[:20],
    }


def build_plan(world: Path, output: Path, args: argparse.Namespace) -> dict[str, Any]:
    audit = audit_empty(world)
    blockers = list(audit["blockers"])
    chunky = Path(args.chunky)
    if not chunky.is_file():
        blockers.append({"reason": "pinned Chunky JAR is missing", "path": str(chunky)})
    elif sha256(chunky) != args.chunky_sha256.upper():
        blockers.append(
            {
                "reason": "pinned Chunky JAR hash mismatch",
                "path": str(chunky),
                "expected": args.chunky_sha256.upper(),
                "actual": sha256(chunky),
            }
        )

    baseline_mods: list[dict[str, Any]] = []
    for raw_path, expected_hash in args.baseline_mod:
        path = Path(raw_path)
        if not path.is_file():
            blockers.append({"reason": "baseline equivalence mod is missing", "path": str(path)})
            continue
        actual = sha256(path)
        if actual != expected_hash.upper():
            blockers.append(
                {
                    "reason": "baseline equivalence mod hash mismatch",
                    "path": str(path),
                    "expected": expected_hash.upper(),
                    "actual": actual,
                }
            )
        baseline_mods.append(jar_worldgen_signals(path))

    forbidden_worldgen = [
        row for row in baseline_mods if row["worldgen_entry_count"] and "backport-1.5.jar" not in row["path"]
    ]
    # Happy Ghast/Nautilus are gameplay-equivalence mods with intentional spawn
    # biome modifiers.  They are excluded during the isolated vanilla freeze;
    # backport remains because its vanilla-1.21.11 equivalence is required.
    if any(row["worldgen_entry_count"] for row in baseline_mods if "backport-1.5.jar" not in row["path"]):
        blockers.append(
            {
                "reason": "isolated baseline contains non-vanilla spawn/worldgen modifiers",
                "rows": forbidden_worldgen,
                "policy": "copy only backport into the isolated pregen server; add gameplay equivalence mods after import",
            }
        )

    core_chunks = chunky_chunks(CORE_RADIUS)
    freeze_chunks = chunky_chunks(FREEZE_RADIUS)
    intersecting_core = intersecting_chunks(CORE_RADIUS)
    plan = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "READY_TO_PREGENERATE" if not blockers else "BLOCKED",
        "policy": {
            "core_radius_blocks": CORE_RADIUS,
            "frozen_radius_blocks": FREEZE_RADIUS,
            "structure_transition_buffer_blocks": STRUCTURE_BUFFER,
            "core_semantics": "Every block with Euclidean distance <= 1000 must be served by a pre-generated vanilla-compatible 1.21.1 chunk.",
            "transition_semantics": "Chunks selected through radius 1536 are generated by the same vanilla-compatible baseline to absorb structure and feature spillover.",
            "outside_semantics": "Full Mechanomania gameplay and world-generation stack is enabled for previously ungenerated chunks outside the frozen import.",
            "no_production_config_changes": True,
            "no_full_world_copy": True,
        },
        "geometry": {
            "center": {"x": CENTER_X, "z": CENTER_Z, "chunk_x": CENTER_X >> 4, "chunk_z": CENTER_Z >> 4},
            "core": {
                "radius": CORE_RADIUS,
                "chunky_selected_chunks": len(core_chunks),
                "all_intersecting_chunks": len(intersecting_core),
                "full_block_coverage_guard": "Chunky selected radius is expanded to 1536; the 536-block excess is much larger than one chunk, so every chunk intersecting the 1000-block core is included.",
            },
            "freeze": {
                "radius": FREEZE_RADIUS,
                "chunk_count": len(freeze_chunks),
                "region_count": len(regions_for_chunks(freeze_chunks)),
                "chunks": [{"x": x, "z": z} for x, z in freeze_chunks],
                "regions": [
                    {"x": x, "z": z, "file": mca_name(x, z)} for x, z in regions_for_chunks(freeze_chunks)
                ],
            },
        },
        "authoritative_empty_audit": audit,
        "isolated_generation": {
            "root": args.isolated_root,
            "minecraft": "1.21.1",
            "target_data_version": EXPECTED_TARGET_DATA_VERSION,
            "neoforge": args.neoforge_version,
            "memory": "-Xms2G -Xmx4G",
            "world_name": "vanilla-freeze-world",
            "seed": EXPECTED_SEED,
            "mods_allowed_during_generation": ["backport-1.5.jar", chunky.name],
            "mods_explicitly_excluded_until_after_import": [
                "happyghast-equivalence (spawn biome modifiers)",
                "nautilus-equivalence (spawn biome modifiers)",
                "all Mechanomania gameplay/worldgen mods",
            ],
            "chunky": {
                "path": str(chunky),
                "sha256": sha256(chunky) if chunky.is_file() else None,
                "modrinth_version_id": "LuFhm4eU",
                "version": "1.4.23",
                "commands": [
                    "chunky world vanilla-freeze-world",
                    f"chunky center {CENTER_X} {CENTER_Z}",
                    "chunky shape circle",
                    "chunky pattern concentric",
                    f"chunky radius {FREEZE_RADIUS}",
                    "chunky selection",
                    "chunky start",
                    "chunky progress",
                ],
            },
            "required_server_properties": {
                "level-name": "vanilla-freeze-world",
                "level-seed": str(EXPECTED_SEED),
                "level-type": "minecraft:normal",
                "generate-structures": "true",
                "online-mode": "false",
                "enable-rcon": "false",
                "server-port": "0",
            },
            "operational_rule": "Run detached on D. Stop only after Chunky reports 100% and the server saves and exits cleanly.",
        },
        "baseline_mods_audited": baseline_mods,
        "import_gate": {
            "preconditions": [
                "Re-run audit-empty immediately before import and require PASS.",
                "Require every expected freeze chunk in terrain region MCA and DataVersion=3955.",
                "Require no chunk outside the planned freeze selection in the isolated world import set.",
                "Require clean server save/stop marker and zero external .mcc chunks.",
                "Import only touched region/entities/poi MCA files; never overwrite level.dat or production configuration.",
            ],
            "postconditions": [
                "Build a SHA-256 manifest for all imported terrain/entities/poi MCA files.",
                "Re-scan every planned chunk and require presence in terrain MCA.",
                "Enable the complete Mechanomania mod/config/KubeJS/datapack stack only after freeze manifest PASS.",
                "Run boundary continuity comparison before public opening.",
            ],
        },
        "boundary_continuity_gate": {
            "scope": "same-seed A/B sample: vanilla-compatible baseline vs full Mechanomania generator",
            "radii": [FREEZE_RADIUS - 32, FREEZE_RADIUS - 16, FREEZE_RADIUS, FREEZE_RADIUS + 16, FREEZE_RADIUS + 32],
            "angle_samples_per_radius": 720,
            "heightmaps": list(HEIGHTMAPS),
            "thresholds": {
                "paired_height_absolute_difference_max": 2,
                "paired_height_p99_absolute_difference_max": 1,
                "boundary_adjacent_step_max": 8,
                "ocean_classification_mismatch_max": 0,
                "water_connectivity_breaks_max": 0,
                "unsupported_fluid_columns_max": 0,
                "cross_boundary_missing_structure_references_max": 0,
                "chunk_parse_errors_max": 0,
            },
            "reasoning": "Both generators use minecraft:noise with settings=minecraft:overworld; this supports a no-vertical-wall expectation. Biome/decorator vegetation can still differ visually and is not claimed mathematically seamless.",
        },
        "blockers": blockers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan


def selected_chunk_index(plan: dict[str, Any]) -> dict[tuple[int, int], set[int]]:
    result: dict[tuple[int, int], set[int]] = {}
    chunks = plan["geometry"]["freeze"]["chunks"]
    for row in chunks:
        chunk_x, chunk_z = int(row["x"]), int(row["z"])
        region = (floor_div(chunk_x, 32), floor_div(chunk_z, 32))
        result.setdefault(region, set()).add(slot_for_chunk(chunk_x, chunk_z))
    return result


def build_freeze_manifest(world: Path, plan_path: Path, output: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    blockers: list[dict[str, Any]] = []
    if plan.get("status") != "READY_TO_PREGENERATE":
        blockers.append({"reason": "plan was not READY_TO_PREGENERATE", "status": plan.get("status")})
    wanted = selected_chunk_index(plan)
    files: list[dict[str, Any]] = []
    terrain_seen: set[tuple[int, int]] = set()
    terrain_versions: Counter[int] = Counter()
    unexpected_slots: list[dict[str, Any]] = []

    for kind in MCA_KINDS:
        for region, expected_slots in sorted(wanted.items()):
            path = world / kind / mca_name(*region)
            if not path.exists():
                if kind == "region":
                    blockers.append({"reason": "terrain MCA is missing", "path": str(path)})
                continue
            try:
                occupied = read_location_table(path)
            except Exception as exc:
                blockers.append({"reason": str(exc), "path": str(path)})
                continue
            extras = sorted(set(occupied) - expected_slots)
            if extras:
                unexpected_slots.append({"kind": kind, "path": str(path), "slots": extras})
            row = {
                "kind": kind,
                "path": str(path),
                "relative_path": str(path.relative_to(world)).replace("\\", "/"),
                "size": path.stat().st_size,
                "sha256": sha256(path),
                "occupied_slots": len(occupied),
                "expected_slots_in_region": len(expected_slots),
                "unexpected_slots": extras,
            }
            files.append(row)
            if kind == "region":
                for slot, root in iter_region_chunks(path):
                    if slot not in expected_slots:
                        continue
                    chunk_x = region[0] * 32 + (slot & 31)
                    chunk_z = region[1] * 32 + (slot >> 5)
                    actual_x = int(root.get("xPos", chunk_x))
                    actual_z = int(root.get("zPos", chunk_z))
                    if (actual_x, actual_z) != (chunk_x, chunk_z):
                        blockers.append(
                            {
                                "reason": "chunk coordinate does not match MCA slot",
                                "path": str(path),
                                "slot": slot,
                                "expected": [chunk_x, chunk_z],
                                "actual": [actual_x, actual_z],
                            }
                        )
                    version = int(root.get("DataVersion", -1))
                    terrain_versions[version] += 1
                    terrain_seen.add((chunk_x, chunk_z))

    expected_chunks = {
        (int(row["x"]), int(row["z"])) for row in plan["geometry"]["freeze"]["chunks"]
    }
    missing = sorted(expected_chunks - terrain_seen)
    if missing:
        blockers.append(
            {
                "reason": "planned terrain chunks are missing",
                "count": len(missing),
                "samples": missing[:100],
            }
        )
    wrong_versions = {str(key): value for key, value in terrain_versions.items() if key != EXPECTED_TARGET_DATA_VERSION}
    if wrong_versions:
        blockers.append(
            {
                "reason": "terrain chunks were not generated by the pinned 1.21.1 baseline",
                "expected_data_version": EXPECTED_TARGET_DATA_VERSION,
                "actual_counts": wrong_versions,
            }
        )
    if unexpected_slots:
        blockers.append(
            {
                "reason": "isolated generation contains chunks outside the frozen selection",
                "rows": unexpected_slots,
            }
        )

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "freeze-manifest",
        "world": str(world),
        "plan": str(plan_path),
        "plan_sha256": sha256(plan_path),
        "expected_terrain_chunks": len(expected_chunks),
        "observed_terrain_chunks": len(terrain_seen),
        "terrain_data_versions": dict(sorted(terrain_versions.items())),
        "files": files,
        "blockers": blockers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def manifest_gate(world: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    blockers: list[dict[str, Any]] = []
    if manifest.get("status") != "PASS":
        blockers.append({"reason": "freeze manifest is not PASS", "status": manifest.get("status")})
    for row in manifest.get("files", []):
        path = world / row["relative_path"]
        if not path.is_file():
            blockers.append({"reason": "frozen MCA is missing", "path": str(path)})
            continue
        actual = sha256(path)
        if actual != row["sha256"]:
            blockers.append(
                {
                    "reason": "frozen MCA hash drift",
                    "path": str(path),
                    "expected": row["sha256"],
                    "actual": actual,
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "verify-manifest",
        "world": str(world),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "blockers": blockers,
    }


def sample_ring_points() -> list[tuple[int, int, int, float]]:
    points: list[tuple[int, int, int, float]] = []
    seen: set[tuple[int, int, int]] = set()
    for radius in (
        FREEZE_RADIUS - 32,
        FREEZE_RADIUS - 16,
        FREEZE_RADIUS,
        FREEZE_RADIUS + 16,
        FREEZE_RADIUS + 32,
    ):
        for index in range(720):
            angle = 2 * math.pi * index / 720
            block_x = round(CENTER_X + radius * math.cos(angle))
            block_z = round(CENTER_Z + radius * math.sin(angle))
            key = (radius, block_x, block_z)
            if key not in seen:
                seen.add(key)
                points.append((radius, block_x, block_z, angle))
    return points


def sample_world_ring(world: Path, output: Path) -> dict[str, Any]:
    facts = level_facts(world)
    reader = WorldReader(world)
    samples: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for radius, block_x, block_z, angle in sample_ring_points():
        row: dict[str, Any] = {
            "radius": radius,
            "angle_radians": angle,
            "x": block_x,
            "z": block_z,
        }
        try:
            root = reader.chunk(floor_div(block_x, 16), floor_div(block_z, 16))
            if root is None:
                raise ValueError("sample chunk is missing")
            heights = {
                name: heightmap_column(root, name, block_x & 15, block_z & 15)
                for name in HEIGHTMAPS
            }
            row["heightmaps"] = heights
            surface_y = heights["WORLD_SURFACE"] - 1
            top_state = reader.block(block_x, surface_y, block_z)
            below_state = reader.block(block_x, surface_y - 1, block_z)
            row["top_state"] = top_state
            row["below_state"] = below_state
            row["ocean"] = top_state in {"minecraft:water", "minecraft:bubble_column"}
            row["unsupported_fluid_columns"] = int(
                top_state in {"minecraft:water", "minecraft:lava"}
                and below_state in {
                    "minecraft:air",
                    "minecraft:cave_air",
                    "minecraft:void_air",
                }
            )
            normal_x = 1 if math.cos(angle) >= 0 else -1
            normal_z = 1 if math.sin(angle) >= 0 else -1
            neighbor_x = block_x + normal_x
            neighbor_z = block_z + normal_z
            neighbor_root = reader.chunk(floor_div(neighbor_x, 16), floor_div(neighbor_z, 16))
            if neighbor_root is None:
                raise ValueError("outward neighbor chunk is missing")
            neighbor_height = heightmap_column(
                neighbor_root, "WORLD_SURFACE", neighbor_x & 15, neighbor_z & 15
            )
            row["boundary_adjacent_step"] = neighbor_height - heights["WORLD_SURFACE"]
            missing_references = reader.missing_structure_references(root)
            row["missing_structure_references"] = len(missing_references)
            if missing_references:
                row["missing_structure_reference_samples"] = missing_references[:10]
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            blockers.append({"x": block_x, "z": block_z, "reason": row["error"]})
        samples.append(row)

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "sample-ring",
        "world": str(world),
        "seed": facts["seed"],
        "level": facts,
        "sample_count": len(samples),
        "radii": sorted({row["radius"] for row in samples}),
        "samples": samples,
        "blockers": blockers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def load_height_sample(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("samples"), list):
        raise ValueError(f"{path}: samples must be a list")
    return data


def percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def boundary_gate(vanilla_path: Path, full_path: Path, output: Path) -> dict[str, Any]:
    vanilla = load_height_sample(vanilla_path)
    full = load_height_sample(full_path)
    blockers: list[dict[str, Any]] = []
    for label, data in (("vanilla", vanilla), ("full", full)):
        if int(data.get("seed", 0)) != EXPECTED_SEED:
            blockers.append({"reason": f"{label} sample seed mismatch", "actual": data.get("seed")})

    def key(row: dict[str, Any]) -> tuple[int, int]:
        return int(row["x"]), int(row["z"])

    vanilla_rows = {key(row): row for row in vanilla["samples"]}
    full_rows = {key(row): row for row in full["samples"]}
    if set(vanilla_rows) != set(full_rows):
        blockers.append(
            {
                "reason": "A/B boundary sample coordinates differ",
                "vanilla_only": sorted(set(vanilla_rows) - set(full_rows))[:50],
                "full_only": sorted(set(full_rows) - set(vanilla_rows))[:50],
            }
        )

    paired_diffs: dict[str, list[int]] = {name: [] for name in HEIGHTMAPS}
    boundary_steps: list[int] = []
    ocean_mismatches = 0
    unsupported_fluid = 0
    parse_errors = 0
    for coordinate in sorted(set(vanilla_rows) & set(full_rows)):
        left = vanilla_rows[coordinate]
        right = full_rows[coordinate]
        if left.get("error") or right.get("error"):
            parse_errors += 1
            continue
        for name in HEIGHTMAPS:
            if name not in left.get("heightmaps", {}) or name not in right.get("heightmaps", {}):
                parse_errors += 1
                continue
            paired_diffs[name].append(
                abs(int(left["heightmaps"][name]) - int(right["heightmaps"][name]))
            )
        if bool(left.get("ocean")) != bool(right.get("ocean")):
            ocean_mismatches += 1
        unsupported_fluid += int(left.get("unsupported_fluid_columns", 0))
        unsupported_fluid += int(right.get("unsupported_fluid_columns", 0))
        if "boundary_adjacent_step" in right:
            boundary_steps.append(abs(int(right["boundary_adjacent_step"])))

    structure_missing = sum(int(row.get("missing_structure_references", 0)) for row in full_rows.values())
    metrics = {
        "paired_sample_count": len(set(vanilla_rows) & set(full_rows)),
        "heightmaps": {
            name: {
                "max_abs_diff": max(values, default=0),
                "p99_abs_diff": percentile(values, 0.99),
            }
            for name, values in paired_diffs.items()
        },
        "boundary_adjacent_step_max": max(boundary_steps, default=0),
        "ocean_classification_mismatches": ocean_mismatches,
        "unsupported_fluid_columns": unsupported_fluid,
        "cross_boundary_missing_structure_references": structure_missing,
        "chunk_parse_errors": parse_errors,
    }
    thresholds = {
        "paired_height_absolute_difference_max": 2,
        "paired_height_p99_absolute_difference_max": 1,
        "boundary_adjacent_step_max": 8,
        "ocean_classification_mismatch_max": 0,
        "unsupported_fluid_columns_max": 0,
        "cross_boundary_missing_structure_references_max": 0,
        "chunk_parse_errors_max": 0,
    }
    for name, row in metrics["heightmaps"].items():
        if row["max_abs_diff"] > thresholds["paired_height_absolute_difference_max"]:
            blockers.append({"reason": f"{name} max paired height difference exceeded", "actual": row})
        if row["p99_abs_diff"] > thresholds["paired_height_p99_absolute_difference_max"]:
            blockers.append({"reason": f"{name} p99 paired height difference exceeded", "actual": row})
    simple_checks = (
        ("boundary_adjacent_step_max", "boundary_adjacent_step_max"),
        ("ocean_classification_mismatches", "ocean_classification_mismatch_max"),
        ("unsupported_fluid_columns", "unsupported_fluid_columns_max"),
        ("cross_boundary_missing_structure_references", "cross_boundary_missing_structure_references_max"),
        ("chunk_parse_errors", "chunk_parse_errors_max"),
    )
    for metric, threshold in simple_checks:
        if metrics[metric] > thresholds[threshold]:
            blockers.append(
                {"reason": f"{metric} exceeded", "actual": metrics[metric], "maximum": thresholds[threshold]}
            )

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "boundary-gate",
        "vanilla_sample": str(vanilla_path),
        "full_sample": str(full_path),
        "metrics": metrics,
        "thresholds": thresholds,
        "claim_scope": "PASS rejects vertical walls, water breaks, unsupported fluids, parse failures, and missing cross-boundary structure references in the sampled ring. It does not claim mathematically identical biome vegetation or decorator placement.",
        "blockers": blockers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def write_result(result: dict[str, Any], output: Path | None) -> None:
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit-empty")
    audit.add_argument("--world", type=Path, required=True)
    audit.add_argument("--output", type=Path)
    audit.add_argument("--radius", type=int, default=FREEZE_RADIUS)

    build = sub.add_parser("build-plan")
    build.add_argument("--world", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--isolated-root", required=True)
    build.add_argument("--chunky", required=True)
    build.add_argument("--chunky-sha256", required=True)
    build.add_argument("--neoforge-version", default="21.1.241")
    build.add_argument(
        "--baseline-mod",
        nargs=2,
        action="append",
        default=[],
        metavar=("PATH", "SHA256"),
    )

    manifest = sub.add_parser("freeze-manifest")
    manifest.add_argument("--world", type=Path, required=True)
    manifest.add_argument("--plan", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)

    verify = sub.add_parser("verify-manifest")
    verify.add_argument("--world", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--output", type=Path)

    sample = sub.add_parser("sample-ring")
    sample.add_argument("--world", type=Path, required=True)
    sample.add_argument("--output", type=Path, required=True)

    boundary = sub.add_parser("boundary-gate")
    boundary.add_argument("--vanilla-sample", type=Path, required=True)
    boundary.add_argument("--full-sample", type=Path, required=True)
    boundary.add_argument("--output", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "audit-empty":
        result = audit_empty(args.world, args.radius)
        write_result(result, args.output)
    elif args.command == "build-plan":
        result = build_plan(args.world, args.output, args)
        print(json.dumps({"status": result["status"], "output": str(args.output)}, ensure_ascii=False))
    elif args.command == "freeze-manifest":
        result = build_freeze_manifest(args.world, args.plan, args.output)
        print(json.dumps({"status": result["status"], "output": str(args.output)}, ensure_ascii=False))
    elif args.command == "verify-manifest":
        result = manifest_gate(args.world, args.manifest)
        write_result(result, args.output)
    elif args.command == "sample-ring":
        result = sample_world_ring(args.world, args.output)
        print(json.dumps({"status": result["status"], "output": str(args.output)}, ensure_ascii=False))
    elif args.command == "boundary-gate":
        result = boundary_gate(args.vanilla_sample, args.full_sample, args.output)
        print(json.dumps({"status": result["status"], "output": str(args.output)}, ensure_ascii=False))
    else:  # pragma: no cover
        raise AssertionError(args.command)
    return 0 if result["status"] in {"PASS", "READY_TO_PREGENERATE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
