from __future__ import annotations

import argparse
import collections
import io
import json
import time
from pathlib import Path
from typing import Any

import nbtlib

import audit_legacy_dimension_roots as base


def occupied(root: Path) -> dict[str, tuple[Path, int]]:
    result: dict[str, tuple[Path, int]] = {}
    for path in sorted((root / "region").glob("*.mca"), key=lambda item: item.name):
        match = base.REGION_NAME.fullmatch(path.name)
        if match is None or path.stat().st_size == 0:
            continue
        region_x, region_z = int(match.group(1)), int(match.group(2))
        with path.open("rb") as handle:
            locations = handle.read(4096)
        if len(locations) != 4096:
            raise ValueError(f"invalid MCA header: {path}")
        for slot in range(1024):
            offset = int.from_bytes(locations[slot * 4 : slot * 4 + 3], "big")
            if offset:
                chunk_x = region_x * 32 + (slot & 31)
                chunk_z = region_z * 32 + (slot >> 5)
                result[f"{chunk_x},{chunk_z}"] = (path, slot)
    return result


def choose_evenly(values: list[str], count: int) -> list[str]:
    if len(values) <= count:
        return values
    return [values[index * len(values) // count] for index in range(count)]


def read_chunk(path: Path, slot: int) -> Any:
    with path.open("rb") as handle:
        header = handle.read(8192)
        location = header[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(location[:3], "big")
        sectors = location[3]
        if not offset:
            raise ValueError(f"unoccupied slot {slot} in {path}")
        handle.seek(offset * 4096)
        length = int.from_bytes(handle.read(4), "big")
        compression = handle.read(1)[0]
        if length + 4 > sectors * 4096:
            raise ValueError(f"payload overruns allocation at slot {slot} in {path}")
        raw = base.decompress(handle.read(length - 1), compression)
    return nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def chunk_body(chunk: Any) -> Any:
    level = chunk.get("Level")
    return level if isinstance(level, dict) else chunk


def section_hash(chunk: Any) -> str:
    body = chunk_body(chunk)
    sections = body.get("sections") or body.get("Sections") or ()
    normalized = []
    for section in sections:
        unpacked = base.plain(section)
        if not isinstance(unpacked, dict):
            continue
        normalized.append(
            {
                "Y": unpacked.get("Y", unpacked.get("y")),
                "block_states": unpacked.get("block_states", {
                    "Palette": unpacked.get("Palette"),
                    "BlockStates": unpacked.get("BlockStates"),
                }),
            }
        )
    normalized.sort(key=lambda value: int(value["Y"]) if value["Y"] is not None else -1000)
    return base.json_hash(normalized)


def biome_hash(chunk: Any) -> str:
    body = chunk_body(chunk)
    sections = body.get("sections") or body.get("Sections") or ()
    normalized = []
    for section in sections:
        unpacked = base.plain(section)
        if not isinstance(unpacked, dict):
            continue
        normalized.append(
            {
                "Y": unpacked.get("Y", unpacked.get("y")),
                "biomes": unpacked.get("biomes", unpacked.get("Biomes")),
            }
        )
    normalized.sort(key=lambda value: int(value["Y"]) if value["Y"] is not None else -1000)
    return base.json_hash(normalized)


def block_entity_keys(chunk: Any) -> set[str]:
    body = chunk_body(chunk)
    values = body.get("block_entities") or body.get("TileEntities") or body.get("BlockEntities") or ()
    result = set()
    for value in values:
        unpacked = base.plain(value)
        if not isinstance(unpacked, dict):
            continue
        result.add(f"{unpacked.get('x')},{unpacked.get('y')},{unpacked.get('z')}|{unpacked.get('id')}")
    return result


def audit_pair(name: str, legacy: Path, canonical: Path, sample_count: int) -> dict[str, Any]:
    legacy_slots = occupied(legacy)
    canonical_slots = occupied(canonical)
    common = sorted(set(legacy_slots) & set(canonical_slots), key=lambda value: tuple(int(x) for x in value.split(",")))
    sample = choose_evenly(common, sample_count)
    counts: collections.Counter[str] = collections.Counter()
    details = []
    errors = []
    for coord in sample:
        try:
            legacy_chunk = read_chunk(*legacy_slots[coord])
            canonical_chunk = read_chunk(*canonical_slots[coord])
            legacy_sections = section_hash(legacy_chunk)
            canonical_sections = section_hash(canonical_chunk)
            legacy_biomes = biome_hash(legacy_chunk)
            canonical_biomes = biome_hash(canonical_chunk)
            legacy_block_entities = block_entity_keys(legacy_chunk)
            canonical_block_entities = block_entity_keys(canonical_chunk)
            same_sections = legacy_sections == canonical_sections
            same_biomes = legacy_biomes == canonical_biomes
            if same_sections:
                counts["same_block_states"] += 1
            if same_biomes:
                counts["same_biomes"] += 1
            counts["legacy_block_entities"] += len(legacy_block_entities)
            counts["canonical_block_entities"] += len(canonical_block_entities)
            counts["common_block_entity_keys"] += len(legacy_block_entities & canonical_block_entities)
            details.append(
                {
                    "coord": coord,
                    "same_block_states": same_sections,
                    "same_biomes": same_biomes,
                    "legacy_block_state_sha256": legacy_sections,
                    "canonical_block_state_sha256": canonical_sections,
                    "legacy_block_entity_count": len(legacy_block_entities),
                    "canonical_block_entity_count": len(canonical_block_entities),
                    "common_block_entity_key_count": len(legacy_block_entities & canonical_block_entities),
                }
            )
        except Exception as exc:
            errors.append({"coord": coord, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "name": name,
        "legacy": str(legacy),
        "canonical": str(canonical),
        "common_occupied_coords": len(common),
        "sample_strategy": "evenly spaced over numerically sorted common chunk coordinates",
        "sample_requested": sample_count,
        "sample_completed": len(details),
        "counts": dict(counts),
        "details": details,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Semantic block-state sample for legacy/canonical dimension roots")
    parser.add_argument("--source", type=Path, default=Path(r"D:\Trans\20260807"))
    parser.add_argument("--sample-count", type=int, default=1024)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    pairs = []
    for name, wrapper_relative, legacy_relative, canonical_relative in base.PAIR_DEFINITIONS:
        pairs.append(
            audit_pair(
                name,
                source / wrapper_relative / legacy_relative,
                source / canonical_relative,
                args.sample_count,
            )
        )
    report = {
        "schema": 1,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(source),
        "source_mode": "read-only",
        "pairs": pairs,
    }
    report["status"] = "FAIL" if any(pair["errors"] for pair in pairs) else "PASS"
    report["report_sha256"] = base.json_hash(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report_sha256": report["report_sha256"], "output": str(args.output)}))
    return 2 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
