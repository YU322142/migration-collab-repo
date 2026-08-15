#!/usr/bin/env python3
"""Semantic postverify for a runtime-saved protected terrain clone.

The slot OTA intentionally protects raw MCA records, but a normal Minecraft
load/save rewrites compression, allocation order, timestamps, palette packing,
and sometimes non-terrain bookkeeping.  The fast path compares raw chunk
records.  Only records that changed are fully decoded into block, biome,
structure, and heightmap semantics.  This keeps the all-29,305-slot gate strict
without expanding every section in the immutable records.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import zipfile
import zlib
from pathlib import Path
from typing import Any, Mapping

import nbtlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protected_zone_terrain_ota as terrain
import audit_protected_zone_terrain_semantic_post as semantic


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
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def sha(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest().upper()


def decode_record(record: terrain.ChunkRecord) -> dict[str, Any]:
    raw = record.raw
    compression = raw[4]
    payload = raw[5:]
    if compression == 1:
        body = gzip.decompress(payload)
    elif compression == 2:
        body = zlib.decompress(payload)
    elif compression == 3:
        body = payload
    else:
        raise ValueError(f"unsupported compression {compression}")
    return plain(nbtlib.File.parse(io.BytesIO(body), byteorder="big"))


def body(root: Mapping[str, Any]) -> dict[str, Any]:
    value = root.get("Level", root)
    return dict(value) if isinstance(value, Mapping) else {}


def section_semantic_view(root: Mapping[str, Any]) -> dict[str, Any]:
    """Decode palette packing while ignoring light arrays and save metadata."""
    b = body(root)
    raw_sections = b.get("sections", b.get("Sections", []))
    result: dict[str, Any] = {}
    for section in raw_sections if isinstance(raw_sections, list) else []:
        if not isinstance(section, Mapping):
            raise ValueError("non-compound section")
        y = int(section.get("Y", -10000))
        blocks = semantic.decode_palette(
            section.get("block_states", section.get("BlockStates", {})),
            4096,
            block=True,
        )
        biomes = semantic.decode_palette(
            section.get("biomes", section.get("Biomes", {})),
            64,
            block=False,
        )
        result[str(y)] = {
            "blocks": sha(blocks),
            "biomes": sha(biomes),
        }
    return result


def heightmap_values(raw: Any) -> list[int] | None:
    values = plain(raw)
    if not isinstance(values, list) or len(values) not in (37, 43):
        return None
    bits = 9 if len(values) == 37 else 10
    per_long = 64 // bits
    mask = (1 << bits) - 1
    words = [int(v) & ((1 << 64) - 1) for v in values]
    out: list[int] = []
    for index in range(256):
        word = index // per_long
        shift = (index % per_long) * bits
        if word >= len(words):
            return None
        out.append((words[word] >> shift) & mask)
    return out


def heightmap_view(root: Mapping[str, Any]) -> dict[str, Any]:
    b = body(root)
    raw = b.get("Heightmaps", b.get("heightmaps", {}))
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, value in raw.items():
        decoded = heightmap_values(value)
        result[str(key)] = decoded if decoded is not None else {"raw": plain(value)}
    return result


def read_region(path: Path) -> terrain.RegionImage:
    if not path.is_file():
        return terrain.RegionImage()
    return terrain.RegionImage.parse(path.read_bytes(), str(path))


def zip_region(zf: zipfile.ZipFile, prefix: str, relative: str) -> terrain.RegionImage:
    name = f"{prefix}/{relative.replace('/', chr(47))}"
    try:
        data = zf.read(name)
    except KeyError:
        return terrain.RegionImage()
    return terrain.RegionImage.parse(data, name)


def compare_chunk(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    diffs: list[str] = []
    ab, bb = body(a), body(b)
    ac = [int(ab.get("xPos", 0)), int(ab.get("zPos", 0))]
    bc = [int(bb.get("xPos", 0)), int(bb.get("zPos", 0))]
    if ac != bc:
        diffs.append("coords")
    av, bv = section_semantic_view(a), section_semantic_view(b)
    if av != bv:
        block_diff = any(av.get(y, {}).get("blocks") != bv.get(y, {}).get("blocks") for y in set(av) | set(bv))
        biome_diff = any(av.get(y, {}).get("biomes") != bv.get(y, {}).get("biomes") for y in set(av) | set(bv))
        if block_diff:
            diffs.append("blocks")
        if biome_diff:
            diffs.append("biomes")
    if plain(ab.get("structures", ab.get("Structures", {}))) != plain(bb.get("structures", bb.get("Structures", {}))):
        diffs.append("structures")
    ah, bh = heightmap_view(a), heightmap_view(b)
    if ah != bh:
        diffs.append("heightmaps")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--current-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    selections = terrain.selection_by_region()
    prefix = "mechanomania-matched-runtime-attempt13-20260814/world"
    summary = {
        "schema": "protected-terrain-semantic-postverify/v1",
        "status": "PASS",
        "runtime": str(args.runtime),
        "donor": str(args.donor),
        "current_zip": str(args.current_zip),
        "selected_chunks": 0,
        "selected_missing": 0,
        "selected_mismatches": 0,
        "selected_heightmap_mismatches": 0,
        "selected_raw_equal": 0,
        "selected_semantic_decodes": 0,
        "outside_checked": 0,
        "outside_stable_mismatches": 0,
        "outside_raw_equal": 0,
        "outside_semantic_decodes": 0,
        "outside_runtime_only_slots": 0,
        "outside_current_only_slots": 0,
        "outside_drift_categories": {},
        "examples": [],
    }
    with zipfile.ZipFile(args.current_zip) as zf:
        for (rx, rz), slots in selections.items():
            relative = f"region/r.{rx}.{rz}.mca"
            runtime_image = read_region(args.runtime / relative)
            donor_image = read_region(args.donor / relative)
            current_image = zip_region(zf, prefix, relative)
            all_slots = set(runtime_image.records) | set(donor_image.records) | set(current_image.records)
            for slot in sorted(slots):
                summary["selected_chunks"] += 1
                rr, dd = runtime_image.records.get(slot), donor_image.records.get(slot)
                if rr is None or dd is None:
                    summary["selected_missing"] += 1
                    summary["status"] = "BLOCKED"
                    if len(summary["examples"]) < 20:
                        summary["examples"].append({"kind": "selected_missing", "region": [rx, rz], "slot": slot})
                    continue
                if rr.raw == dd.raw:
                    summary["selected_raw_equal"] += 1
                    continue
                summary["selected_semantic_decodes"] += 1
                diffs = compare_chunk(decode_record(rr), decode_record(dd))
                if diffs:
                    summary["selected_mismatches"] += 1
                    if "heightmaps" in diffs:
                        summary["selected_heightmap_mismatches"] += 1
                    summary["status"] = "BLOCKED"
                    if len(summary["examples"]) < 20:
                        summary["examples"].append({"kind": "selected_mismatch", "region": [rx, rz], "slot": slot, "fields": diffs})
            for slot in sorted(set(all_slots) - set(slots)):
                rr, cc = runtime_image.records.get(slot), current_image.records.get(slot)
                if rr is None and cc is None:
                    continue
                if rr is not None and cc is None:
                    summary["outside_runtime_only_slots"] += 1
                    continue
                if rr is None and cc is not None:
                    summary["outside_current_only_slots"] += 1
                    summary["status"] = "BLOCKED"
                    if len(summary["examples"]) < 20:
                        summary["examples"].append({"kind": "outside_current_slot_missing", "region": [rx, rz], "slot": slot})
                    continue
                summary["outside_checked"] += 1
                assert rr is not None and cc is not None
                if rr.raw == cc.raw:
                    summary["outside_raw_equal"] += 1
                    continue
                summary["outside_semantic_decodes"] += 1
                diffs = compare_chunk(decode_record(rr), decode_record(cc))
                if diffs:
                    summary["outside_stable_mismatches"] += 1
                    for field in diffs:
                        summary["outside_drift_categories"][field] = summary["outside_drift_categories"].get(field, 0) + 1
                    if len(summary["examples"]) < 20:
                        summary["examples"].append({"kind": "outside_mismatch", "region": [rx, rz], "slot": slot, "fields": diffs})
    if summary["selected_missing"] or summary["selected_mismatches"]:
        summary["status"] = "BLOCKED"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
