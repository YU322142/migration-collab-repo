#!/usr/bin/env python3
"""Read-only preflight classifier for a terrain/biome three-way OTA.

The tool never edits any world.  It binds the stopped public snapshot (C), an
exact bad-generation baseline (B, optional but required for automatic repair),
and the desired vanilla-compatible reference (V) to file/slot/component hashes.
It deliberately does not implement the write path: rows classified as
THREE_WAY_REQUIRED need the registry-aware merge/apply engine described in
``outputs/terrain-biome-safe-ota-design-20260815.md``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import struct
import zlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nbtlib


REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
MCA_KINDS = ("region", "entities", "poi")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def selected_chunks(center_x: int, center_z: int, radius: int) -> list[tuple[int, int]]:
    """Return chunks containing at least one integer block inside the circle.

    Minecraft blocks occupy discrete integer coordinates.  Testing only the
    chunk centre misses boundary chunks whose centre lies outside the circle
    while one or more of their 16x16 block coordinates lie inside it.  The
    closest integer x/z coordinate in each closed chunk square is therefore
    used for the exact intersection test.
    """

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


def slot_for_chunk(chunk_x: int, chunk_z: int) -> int:
    return (chunk_x & 31) + (chunk_z & 31) * 32


def typed_plain(value: Any) -> Any:
    """Return a deterministic, type-preserving JSON-compatible NBT value."""

    tag_type = type(value).__name__
    if isinstance(value, Mapping):
        return [
            tag_type,
            [[str(key), typed_plain(child)] for key, child in sorted(value.items(), key=lambda row: str(row[0]))],
        ]
    if isinstance(value, (str, bytes, bytearray)):
        return [tag_type, value.hex() if isinstance(value, (bytes, bytearray)) else str(value)]
    if hasattr(value, "tolist"):
        return [tag_type, [typed_plain(child) for child in value.tolist()]]
    if isinstance(value, Sequence):
        return [tag_type, [typed_plain(child) for child in value]]
    if hasattr(value, "unpack"):
        unpacked = value.unpack()
        return [tag_type, unpacked]
    if isinstance(value, (int, float, bool)) or value is None:
        return [tag_type, value]
    return [tag_type, str(value)]


def semantic_hash(value: Any) -> str:
    payload = json.dumps(
        typed_plain(value), ensure_ascii=False, sort_keys=False, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def chunk_body(root: Any) -> Any:
    if isinstance(root, Mapping) and isinstance(root.get("Level"), Mapping):
        return root["Level"]
    return root


def first(body: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in body:
            return body[name]
    return default


def chunk_components(root: Any) -> dict[str, Any]:
    body = chunk_body(root)
    sections = list(first(body, "sections", "Sections", default=[]) or [])
    sections.sort(key=lambda section: int(section.get("Y", 0)))

    blocks = []
    biomes = []
    lighting = []
    for section in sections:
        section_y = int(section.get("Y", 0))
        blocks.append(
            {
                "Y": section_y,
                "block_states": first(section, "block_states", "BlockStates", default=None),
            }
        )
        biomes.append(
            {
                "Y": section_y,
                "biomes": first(section, "biomes", "Biomes", default=None),
            }
        )
        lighting.append(
            {
                "Y": section_y,
                "BlockLight": section.get("BlockLight"),
                "SkyLight": section.get("SkyLight"),
            }
        )

    block_entities = first(
        body,
        "block_entities",
        "BlockEntities",
        "blockEntities",
        "TileEntities",
        default=[],
    )
    structures = first(body, "structures", "Structures", default={})
    heightmaps = first(body, "Heightmaps", "heightmaps", default={})
    scheduled = {
        "block_ticks": first(body, "block_ticks", "TileTicks", default=[]),
        "fluid_ticks": first(body, "fluid_ticks", "LiquidTicks", default=[]),
        "PostProcessing": first(body, "PostProcessing", "post_processing", default=[]),
    }
    runtime = {
        "Status": first(body, "Status", "status"),
        "LastUpdate": first(body, "LastUpdate", "last_update"),
        "InhabitedTime": first(body, "InhabitedTime", "inhabited_time"),
        "isLightOn": first(body, "isLightOn", "is_light_on"),
        "DataVersion": first(body, "DataVersion", default=root.get("DataVersion") if isinstance(root, Mapping) else None),
    }

    hashes = {
        "block_states": semantic_hash(blocks),
        "biomes": semantic_hash(biomes),
        "block_entities": semantic_hash(block_entities),
        "structures": semantic_hash(structures),
        "scheduled": semantic_hash(scheduled),
        "heightmaps": semantic_hash(heightmaps),
        "lighting": semantic_hash(lighting),
        "runtime": semantic_hash(runtime),
    }
    hashes["repair_domains"] = semantic_hash(
        {
            key: hashes[key]
            for key in ("block_states", "biomes", "block_entities", "structures", "scheduled")
        }
    )
    return {"hashes": hashes, "runtime": typed_plain(runtime)}


@dataclass
class ChunkRecord:
    record_sha256: str
    nbt_sha256: str
    components: dict[str, Any]


class RegionView:
    def __init__(self, path: Path):
        self.path = path
        self.exists = path.is_file() and path.stat().st_size > 0
        self.file_size = path.stat().st_size if path.exists() else 0
        self.file_sha256 = sha256_file(path) if path.is_file() else None
        self.locations: dict[int, tuple[int, int]] = {}
        if not self.exists:
            return
        with path.open("rb") as stream:
            header = stream.read(4096)
        if len(header) != 4096:
            raise ValueError(f"{path}: truncated MCA location table")
        for slot in range(1024):
            entry = header[slot * 4 : slot * 4 + 4]
            offset = int.from_bytes(entry[:3], "big")
            sectors = entry[3]
            if not offset:
                continue
            if offset < 2 or sectors < 1:
                raise ValueError(f"{path}: invalid slot {slot}: offset={offset}, sectors={sectors}")
            if (offset + sectors) * 4096 > self.file_size + 4095:
                raise ValueError(f"{path}: slot {slot} allocation exceeds file")
            self.locations[slot] = (offset, sectors)

    def read(self, slot: int, semantic: bool) -> ChunkRecord | None:
        location = self.locations.get(slot)
        if location is None:
            return None
        offset, sectors = location
        with self.path.open("rb") as stream:
            stream.seek(offset * 4096)
            length_raw = stream.read(4)
            compression_raw = stream.read(1)
            if len(length_raw) != 4 or len(compression_raw) != 1:
                raise ValueError(f"{self.path}: slot {slot} truncated record header")
            length = struct.unpack(">I", length_raw)[0]
            compression = compression_raw[0]
            if compression & 0x80:
                raise ValueError(f"{self.path}: slot {slot} external .mcc is refused")
            if length < 1 or length + 4 > sectors * 4096:
                raise ValueError(f"{self.path}: slot {slot} invalid length {length}")
            payload = stream.read(length - 1)
        if len(payload) != length - 1:
            raise ValueError(f"{self.path}: slot {slot} truncated payload")
        record = length_raw + compression_raw + payload
        if compression == 1:
            raw = gzip.decompress(payload)
        elif compression == 2:
            raw = zlib.decompress(payload)
        elif compression == 3:
            raw = payload
        else:
            raise ValueError(f"{self.path}: slot {slot} unsupported compression {compression}")
        parsed = nbtlib.File.parse(io.BytesIO(raw), byteorder="big")
        return ChunkRecord(
            record_sha256=sha256_bytes(record),
            nbt_sha256=sha256_bytes(raw),
            components=chunk_components(parsed) if semantic else {},
        )


def level_info(world: Path) -> dict[str, Any]:
    path = world / "level.dat"
    result: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        return result
    result["sha256"] = sha256_file(path)
    with gzip.open(path, "rb") as stream:
        root = nbtlib.File.parse(stream, byteorder="big")
    data = root.get("Data", root)
    settings = data.get("WorldGenSettings", {}) if isinstance(data, Mapping) else {}
    result.update(
        {
            "DataVersion": int(data.get("DataVersion", 0)) if isinstance(data, Mapping) else None,
            "seed": int(settings.get("seed")) if isinstance(settings, Mapping) and "seed" in settings else None,
            "generator": typed_plain(
                settings.get("dimensions", {}).get("minecraft:overworld", {}).get("generator")
                if isinstance(settings, Mapping)
                else None
            ),
        }
    )
    return result


def disposition(current: str, base: str | None, desired: str) -> str:
    if current == desired:
        return "ALREADY_DESIRED"
    if base is None:
        return "BLOCKED_NO_EXACT_BASE"
    if current == base:
        return "SAFE_REPLACE_WITH_DESIRED"
    return "THREE_WAY_REQUIRED_CURRENT_WINS_ON_CONFLICT"


def audit(
    current_world: Path,
    desired_world: Path,
    bad_base_world: Path | None,
    center_x: int,
    center_z: int,
    radius: int,
    include_all_rows: bool,
) -> dict[str, Any]:
    chunks = selected_chunks(center_x, center_z, radius)
    grouped: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for chunk_x, chunk_z in chunks:
        grouped.setdefault((chunk_x // 32, chunk_z // 32), []).append((chunk_x, chunk_z))

    worlds: dict[str, Path | None] = {
        "current": current_world,
        "bad_base": bad_base_world,
        "desired": desired_world,
    }
    levels = {name: level_info(path) if path else None for name, path in worlds.items()}
    blockers: list[dict[str, Any]] = []
    current_seed = levels["current"].get("seed") if levels["current"] else None
    desired_seed = levels["desired"].get("seed") if levels["desired"] else None
    base_seed = levels["bad_base"].get("seed") if levels["bad_base"] else None
    if current_seed is None or desired_seed is None:
        blockers.append({"reason": "current or desired level.dat seed is unavailable"})
    elif current_seed != desired_seed:
        blockers.append(
            {"reason": "current/desired seed mismatch", "current": current_seed, "desired": desired_seed}
        )
    if bad_base_world is not None and base_seed != current_seed:
        blockers.append(
            {"reason": "bad-base/current seed mismatch", "bad_base": base_seed, "current": current_seed}
        )

    counts: Counter[str] = Counter()
    domain_counts: dict[str, Counter[str]] = {
        "block_states": Counter(),
        "biomes": Counter(),
        "block_entities": Counter(),
        "structures": Counter(),
        "scheduled": Counter(),
    }
    samples: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    region_manifest: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []

    for (region_x, region_z), region_chunks in sorted(grouped.items()):
        views: dict[str, dict[str, RegionView | None]] = {}
        for label, world in worlds.items():
            views[label] = {}
            for kind in MCA_KINDS:
                if world is None:
                    views[label][kind] = None
                    continue
                path = world / kind / f"r.{region_x}.{region_z}.mca"
                try:
                    view = RegionView(path)
                    views[label][kind] = view
                    region_manifest.append(
                        {
                            "world": label,
                            "kind": kind,
                            "region": [region_x, region_z],
                            "path": str(path),
                            "exists": view.exists,
                            "bytes": view.file_size,
                            "sha256": view.file_sha256,
                            "occupied_slots": len(view.locations),
                        }
                    )
                except Exception as exc:
                    views[label][kind] = None
                    parse_errors.append(
                        {
                            "world": label,
                            "kind": kind,
                            "region": [region_x, region_z],
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

        for chunk_x, chunk_z in sorted(region_chunks):
            slot = slot_for_chunk(chunk_x, chunk_z)
            try:
                current = views["current"]["region"].read(slot, True) if views["current"]["region"] else None
                desired = views["desired"]["region"].read(slot, True) if views["desired"]["region"] else None
                base = (
                    views["bad_base"]["region"].read(slot, True)
                    if views["bad_base"]["region"]
                    else None
                )
                current_entity = (
                    views["current"]["entities"].read(slot, False)
                    if views["current"]["entities"]
                    else None
                )
                current_poi = (
                    views["current"]["poi"].read(slot, False)
                    if views["current"]["poi"]
                    else None
                )
            except Exception as exc:
                parse_errors.append(
                    {
                        "chunk": [chunk_x, chunk_z],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            row: dict[str, Any] = {
                "chunk": [chunk_x, chunk_z],
                "region": [region_x, region_z],
                "slot": slot,
                "current_entity_record_sha256": current_entity.record_sha256 if current_entity else None,
                "current_poi_record_sha256": current_poi.record_sha256 if current_poi else None,
            }
            if desired is None:
                classification = "BLOCKED_DESIRED_CHUNK_MISSING"
            elif current is None:
                classification = (
                    "BLOCKED_ORPHAN_ENTITY_OR_POI"
                    if current_entity is not None or current_poi is not None
                    else "SAFE_IMPORT_INTO_EMPTY_SLOT"
                )
            elif current.components["hashes"]["repair_domains"] == desired.components["hashes"]["repair_domains"]:
                classification = "ALREADY_DESIRED"
            elif bad_base_world is None:
                classification = "BLOCKED_NO_EXACT_BAD_BASE"
            elif base is None:
                classification = "BLOCKED_BAD_BASE_CHUNK_MISSING"
            elif current.components["hashes"]["repair_domains"] == base.components["hashes"]["repair_domains"]:
                classification = "SAFE_COMPONENT_REPLACE_UNTOUCHED_BAD_BASE"
            else:
                classification = "THREE_WAY_REQUIRED_CURRENT_WINS_ON_CONFLICT"

            row["classification"] = classification
            counts[classification] += 1
            for label, record in (("current", current), ("bad_base", base), ("desired", desired)):
                row[label] = (
                    {
                        "record_sha256": record.record_sha256,
                        "nbt_sha256": record.nbt_sha256,
                        "components": record.components["hashes"],
                        "runtime": record.components["runtime"],
                    }
                    if record
                    else None
                )

            if current and desired:
                for domain in domain_counts:
                    base_hash = base.components["hashes"][domain] if base else None
                    value = disposition(
                        current.components["hashes"][domain],
                        base_hash,
                        desired.components["hashes"][domain],
                    )
                    row.setdefault("domain_disposition", {})[domain] = value
                    domain_counts[domain][value] += 1

            if include_all_rows:
                all_rows.append(row)
            elif classification not in ("ALREADY_DESIRED", "SAFE_IMPORT_INTO_EMPTY_SLOT") and len(samples) < 200:
                samples.append(row)

    if parse_errors:
        blockers.append({"reason": "MCA parse errors", "count": len(parse_errors)})
    hard_blocked = sum(
        count
        for label, count in counts.items()
        if label.startswith("BLOCKED_")
    )
    three_way = counts["THREE_WAY_REQUIRED_CURRENT_WINS_ON_CONFLICT"]
    if blockers or hard_blocked:
        status = "BLOCKED"
    elif three_way:
        status = "REQUIRES_REGISTRY_AWARE_THREE_WAY_ENGINE"
    else:
        status = "INPUTS_CLASSIFIED_FOR_PATCH_BUILD"

    return {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "status": status,
        "operation": "audit-terrain-biome-ota-inputs-readonly",
        "policy": {
            "conflict_winner": "current public server state",
            "block_rule": "C==B ? V : C",
            "biome_rule": "C==B ? V : C",
            "entities_rule": "never write entities MCA",
            "world_modified": False,
        },
        "scope": {
            "center": {"x": center_x, "z": center_z},
            "radius_blocks": radius,
            "selected_chunks": len(chunks),
            "selected_regions": len(grouped),
        },
        "worlds": {name: str(path) if path else None for name, path in worlds.items()},
        "levels": levels,
        "classification_counts": dict(sorted(counts.items())),
        "domain_disposition_counts": {
            domain: dict(sorted(values.items())) for domain, values in domain_counts.items()
        },
        "blockers": blockers,
        "parse_errors": parse_errors[:200],
        "region_manifest": region_manifest,
        "rows": all_rows if include_all_rows else None,
        "nontrivial_samples": samples if not include_all_rows else None,
        "next_gate": (
            "Do not build/apply a patch until all BLOCKED rows are resolved and every THREE_WAY row "
            "has a registry-aware per-coordinate merge plan."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-world", type=Path, required=True)
    parser.add_argument("--desired-world", type=Path, required=True)
    parser.add_argument("--bad-baseline-world", type=Path)
    parser.add_argument("--center-x", type=int, default=10_192)
    parser.add_argument("--center-z", type=int, default=-1_574)
    parser.add_argument("--radius", type=int, default=1_536)
    parser.add_argument("--include-all-rows", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = audit(
        args.current_world.resolve(),
        args.desired_world.resolve(),
        args.bad_baseline_world.resolve() if args.bad_baseline_world else None,
        args.center_x,
        args.center_z,
        args.radius,
        args.include_all_rows,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "scope": report["scope"],
        "classification_counts": report["classification_counts"],
        "blockers": report["blockers"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"] != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
