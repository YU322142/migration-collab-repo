#!/usr/bin/env python3
"""Read-only semantic post-audit for the protected-terrain OTA test clone.

The detached clone has already been started and stopped dynamically.  This
tool does not start Java and does not write any world.  It compares only the
terrain MCA slots in the 40 affected regions:

* selected slots must semantically equal the strict vanilla V donor;
* all unselected slots must semantically equal the C preimage;
* MCA timestamps, record compression/packing, and entities MCA are ignored;
* the comparison is limited to block states, biomes, structures, heightmaps,
  and chunk coordinates.  Block entities/ticks/light/entity files are not part
  of this gate.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import struct
import sys
import zlib
import gzip
import io
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import nbtlib


TOOL_VERSION = 1
EXPECTED_ARCHIVE_SHA256 = "ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92"
EXPECTED_CHUNKS = 29_305
EXPECTED_REGIONS = 40
MCA_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
SCRIPT_DIR = Path(__file__).resolve().parent


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


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mca_name(path: Path) -> tuple[int, int]:
    match = MCA_RE.fullmatch(path.name)
    if match is None:
        raise ValueError(f"invalid MCA filename: {path}")
    return int(match.group(1)), int(match.group(2))


def slot_for_chunk(chunk_x: int, chunk_z: int) -> int:
    return (chunk_x & 31) + (chunk_z & 31) * 32


def chunk_for_slot(region_x: int, region_z: int, slot: int) -> tuple[int, int]:
    return region_x * 32 + (slot & 31), region_z * 32 + (slot >> 5)


def occupied_slots(path: Path | None) -> set[int]:
    if path is None or not path.is_file() or path.stat().st_size == 0:
        return set()
    with path.open("rb") as stream:
        locations = stream.read(4096)
    if len(locations) != 4096:
        raise ValueError(f"truncated MCA location header: {path}")
    result: set[int] = set()
    for slot in range(1024):
        entry = locations[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if offset:
            if offset < 2 or sectors < 1:
                raise ValueError(f"invalid MCA location entry {path} slot {slot}")
            result.add(slot)
    return result


def load_chunk(path: Path, slot: int) -> Any:
    with path.open("rb") as stream:
        locations = stream.read(4096)
        entry = locations[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if offset == 0 or sectors == 0:
            raise KeyError(f"missing MCA slot {slot}: {path}")
        stream.seek(offset * 4096)
        length_raw = stream.read(4)
        if len(length_raw) != 4:
            raise ValueError(f"truncated MCA length: {path} slot {slot}")
        length = struct.unpack(">I", length_raw)[0]
        if length < 1 or length + 4 > sectors * 4096:
            raise ValueError(f"invalid MCA record length: {path} slot {slot}")
        compression = stream.read(1)[0]
        if compression & 0x80:
            raise ValueError(f"external .mcc storage is not supported: {path} slot {slot}")
        payload = stream.read(length - 1)
    if compression == 1:
        raw = gzip.decompress(payload)
    elif compression == 2:
        raw = zlib.decompress(payload)
    elif compression == 3:
        raw = payload
    else:
        raise ValueError(f"unsupported MCA compression {compression}: {path} slot {slot}")
    return nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def body_of(root: Any) -> Mapping[str, Any]:
    if isinstance(root, Mapping) and isinstance(root.get("Level"), Mapping):
        return root["Level"]
    return root if isinstance(root, Mapping) else {}


def iter_values(raw: Any) -> list[Any]:
    try:
        return list(raw)
    except TypeError:
        return []


def palette_entry(value: Any, *, block: bool) -> Any:
    value = plain(value)
    if block:
        if isinstance(value, Mapping):
            props = value.get("Properties", value.get("properties", {}))
            if not isinstance(props, Mapping):
                props = {}
            return {
                "name": str(value.get("Name", value.get("name", "minecraft:air"))),
                "properties": {str(k): str(v) for k, v in sorted(props.items())},
            }
        return {"name": str(value), "properties": {}}
    return str(value)


def decode_palette(container: Any, count: int, *, block: bool) -> list[Any]:
    if not isinstance(container, Mapping):
        default = palette_entry("minecraft:air" if block else "minecraft:plains", block=block)
        return [default] * count
    palette_raw = container.get("palette", container.get("Palette", []))
    palette = [palette_entry(value, block=block) for value in iter_values(palette_raw)]
    if not palette:
        default = palette_entry("minecraft:air" if block else "minecraft:plains", block=block)
        return [default] * count
    if len(palette) == 1:
        return [palette[0]] * count
    data = [int(plain(value)) & 0xFFFFFFFFFFFFFFFF for value in iter_values(container.get("data", container.get("Data", [])))]
    minimum_bits = 4 if block else 1
    bits = max(minimum_bits, (len(palette) - 1).bit_length())
    values_per_long = 64 // bits
    values: list[Any] = []
    for index in range(count):
        long_index = index // values_per_long
        if long_index >= len(data):
            raise ValueError(f"packed palette data is short: index={index}, longs={len(data)}, bits={bits}")
        shift = (index % values_per_long) * bits
        palette_index = (data[long_index] >> shift) & ((1 << bits) - 1)
        if palette_index >= len(palette):
            raise ValueError(f"palette index {palette_index} >= {len(palette)}")
        values.append(palette[palette_index])
    return values


def section_projection(section: Mapping[str, Any]) -> dict[str, Any]:
    y = int(plain(section.get("Y", -10000)))
    blocks = decode_palette(section.get("block_states", section.get("BlockStates", {})), 4096, block=True)
    biomes = decode_palette(section.get("biomes", section.get("Biomes", {})), 64, block=False)
    return {
        "y": y,
        "block_digest": digest(blocks),
        "biome_digest": digest(biomes),
        "non_air_blocks": sum(1 for value in blocks if value.get("name") not in {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}),
        "block_palette_names": sorted({value["name"] for value in blocks}),
        "biome_names": sorted(set(biomes)),
    }


def structures_projection(value: Any) -> dict[str, Any]:
    normalized = plain(value if isinstance(value, Mapping) else {})
    keys: list[str] = []
    if isinstance(normalized, Mapping):
        for name in ("starts", "References", "references"):
            child = normalized.get(name)
            if isinstance(child, Mapping):
                keys.extend(str(key) for key in child.keys())
    return {"digest": digest(normalized), "top_level_keys": sorted(normalized.keys()) if isinstance(normalized, Mapping) else [], "structure_ids": sorted(set(keys))}


def heightmaps_projection(value: Any) -> dict[str, Any]:
    normalized = plain(value if isinstance(value, Mapping) else {})
    lengths = {str(key): len(child) if isinstance(child, list) else None for key, child in normalized.items()} if isinstance(normalized, Mapping) else {}
    return {"digest": digest(normalized), "keys": sorted(normalized.keys()) if isinstance(normalized, Mapping) else [], "lengths": lengths}


def semantic_projection(root: Any) -> dict[str, Any]:
    body = body_of(root)
    raw_sections = body.get("sections", body.get("Sections", []))
    section_rows: dict[int, dict[str, Any]] = {}
    section_errors: list[str] = []
    for section in iter_values(raw_sections):
        if not isinstance(section, Mapping):
            section_errors.append("non-compound section")
            continue
        try:
            row = section_projection(section)
            section_rows[row["y"]] = row
        except Exception as exc:  # noqa: BLE001 - fail closed per chunk
            section_errors.append(f"section decode: {type(exc).__name__}: {exc}")
    section_order = sorted(section_rows)
    block_semantic = [{"y": y, "digest": section_rows[y]["block_digest"]} for y in section_order]
    biome_semantic = [{"y": y, "digest": section_rows[y]["biome_digest"]} for y in section_order]
    structures = structures_projection(body.get("structures", {}))
    heightmaps = heightmaps_projection(body.get("Heightmaps", {}))
    coords = [int(plain(body.get("xPos", 0))), int(plain(body.get("zPos", 0)))]
    return {
        "coords": coords,
        "data_version": int(plain(body.get("DataVersion", -1))),
        "status": str(plain(body.get("Status", ""))),
        "section_y": section_order,
        "sections": section_rows,
        "blocks_digest": digest(block_semantic),
        "biomes_digest": digest(biome_semantic),
        "structures": structures,
        "heightmaps": heightmaps,
        "semantic_digest": digest(
            {
                "coords": coords,
                "blocks": block_semantic,
                "biomes": biome_semantic,
                "structures": structures,
                "heightmaps": heightmaps,
            }
        ),
        "section_errors": section_errors,
    }


def compare_semantic(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> list[str]:
    differences: list[str] = []
    if expected.get("coords") != actual.get("coords"):
        differences.append("coords")
    if expected.get("blocks_digest") != actual.get("blocks_digest"):
        differences.append("blocks")
    if expected.get("biomes_digest") != actual.get("biomes_digest"):
        differences.append("biomes")
    if expected.get("structures", {}).get("digest") != actual.get("structures", {}).get("digest"):
        differences.append("structures")
    if expected.get("heightmaps", {}).get("digest") != actual.get("heightmaps", {}).get("digest"):
        differences.append("heightmaps")
    if expected.get("section_errors") or actual.get("section_errors"):
        differences.append("section_decode_errors")
    return differences


def file_identity(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"exists": False, "bytes": 0, "sha256": None}
    return {"exists": True, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def selected_slots_from_plan(plan: Mapping[str, Any]) -> dict[tuple[int, int], set[int]]:
    selection = plan.get("selection", {})
    grouped: dict[tuple[int, int], set[int]] = {}
    for row in selection.get("regions", []):
        region = tuple(int(value) for value in row["region"])
        grouped[region] = {int(slot) for slot in row.get("slots", [])}
    return grouped


def audit_region(
    region: tuple[int, int],
    selected: set[int],
    clone_dir: Path,
    c_dir: Path,
    v_dir: Path,
    progress: dict[str, int],
) -> dict[str, Any]:
    rx, rz = region
    filename = f"r.{rx}.{rz}.mca"
    clone_path = clone_dir / filename
    c_path = c_dir / filename
    v_path = v_dir / filename
    clone_slots = occupied_slots(clone_path)
    c_slots = occupied_slots(c_path)
    v_slots = occupied_slots(v_path)
    expected_slots = set(selected) | (c_slots - set(selected))
    all_slots = set(selected) | clone_slots | c_slots | v_slots
    mismatches: list[dict[str, Any]] = []
    matched_selected = 0
    matched_outside = 0
    selected_missing = 0
    outside_missing = 0
    field_counts: Counter[str] = Counter()
    data_version_counts: Counter[str] = Counter()
    raw_diffs = 0
    chunk_cache: dict[tuple[str, int], dict[str, Any]] = {}

    def projection(kind: str, path: Path, slot: int) -> dict[str, Any]:
        key = (kind, slot)
        if key not in chunk_cache:
            chunk_cache[key] = semantic_projection(load_chunk(path, slot))
        return chunk_cache[key]

    for slot in sorted(all_slots):
        is_selected = slot in selected
        expected_kind = "V" if is_selected else "C"
        expected_path = v_path if is_selected else c_path
        expected_exists = slot in (v_slots if is_selected else c_slots)
        actual_exists = slot in clone_slots
        if is_selected and not expected_exists:
            mismatches.append({"slot": slot, "chunk": list(chunk_for_slot(rx, rz, slot)), "scope": "selected", "reason": "V donor slot missing"})
            selected_missing += 1
            continue
        if not is_selected and not expected_exists and not actual_exists:
            continue
        if expected_exists != actual_exists:
            mismatches.append(
                {
                    "slot": slot,
                    "chunk": list(chunk_for_slot(rx, rz, slot)),
                    "scope": "selected" if is_selected else "outside",
                    "reason": "presence mismatch",
                    "expected_kind": expected_kind,
                    "expected_exists": expected_exists,
                    "actual_exists": actual_exists,
                }
            )
            if is_selected:
                selected_missing += 1
            else:
                outside_missing += 1
            continue
        if not actual_exists:
            continue
        try:
            expected_projection = projection(expected_kind, expected_path, slot)
            actual_projection = projection("clone", clone_path, slot)
            differences = compare_semantic(expected_projection, actual_projection)
            data_version_counts[str(actual_projection.get("data_version"))] += 1
            if differences:
                field_counts.update(differences)
                mismatches.append(
                    {
                        "slot": slot,
                        "chunk": list(chunk_for_slot(rx, rz, slot)),
                        "scope": "selected" if is_selected else "outside",
                        "reason": "semantic mismatch",
                        "expected_kind": expected_kind,
                        "fields": differences,
                        "expected": {
                            "semantic_digest": expected_projection.get("semantic_digest"),
                            "blocks_digest": expected_projection.get("blocks_digest"),
                            "biomes_digest": expected_projection.get("biomes_digest"),
                            "structures_digest": expected_projection.get("structures", {}).get("digest"),
                            "heightmaps_digest": expected_projection.get("heightmaps", {}).get("digest"),
                        },
                        "actual": {
                            "semantic_digest": actual_projection.get("semantic_digest"),
                            "blocks_digest": actual_projection.get("blocks_digest"),
                            "biomes_digest": actual_projection.get("biomes_digest"),
                            "structures_digest": actual_projection.get("structures", {}).get("digest"),
                            "heightmaps_digest": actual_projection.get("heightmaps", {}).get("digest"),
                        },
                    }
                )
            elif is_selected:
                matched_selected += 1
            else:
                matched_outside += 1
        except Exception as exc:  # noqa: BLE001 - collect and fail closed
            mismatches.append(
                {
                    "slot": slot,
                    "chunk": list(chunk_for_slot(rx, rz, slot)),
                    "scope": "selected" if is_selected else "outside",
                    "reason": "semantic decode error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            field_counts["decode_error"] += 1

    if file_identity(clone_path) != file_identity(v_path if selected else c_path):
        raw_diffs = 1
    progress["chunks"] += len(all_slots)
    if progress["chunks"] % 2000 < len(all_slots):
        print(f"audited {progress['chunks']} terrain slots", flush=True)
    return {
        "region": [rx, rz],
        "selected_slots": len(selected),
        "clone_occupied_slots": len(clone_slots),
        "c_occupied_slots": len(c_slots),
        "v_occupied_slots": len(v_slots),
        "matched_selected": matched_selected,
        "matched_outside": matched_outside,
        "selected_presence_mismatches": selected_missing,
        "outside_presence_mismatches": outside_missing,
        "semantic_mismatch_count": sum(1 for row in mismatches if row.get("reason") == "semantic mismatch"),
        "raw_file_differs_from_expected": bool(raw_diffs),
        "data_version_counts": dict(sorted(data_version_counts.items())),
        "field_mismatch_counts": dict(sorted(field_counts.items())),
        "mismatches": mismatches,
        "file_identities": {
            "clone": file_identity(clone_path),
            "c_preimage": file_identity(c_path),
            "v": file_identity(v_path),
        },
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    clone_world = args.clone_world.resolve()
    c_preimage = args.c_preimage.resolve()
    v_world = args.v_world.resolve()
    plan_path = args.plan.resolve()
    verify_path = args.clone_verify.resolve() if args.clone_verify else None
    source_archive = args.source_archive.resolve() if args.source_archive else None
    for path in (clone_world, c_preimage, v_world, plan_path):
        if not path.exists():
            raise FileNotFoundError(path)
    plan = json_load(plan_path)
    selected_by_region = selected_slots_from_plan(plan)
    input_failures: list[str] = []
    if len(selected_by_region) != EXPECTED_REGIONS:
        input_failures.append(f"plan selected region count {len(selected_by_region)} != {EXPECTED_REGIONS}")
    if sum(len(slots) for slots in selected_by_region.values()) != EXPECTED_CHUNKS:
        input_failures.append(
            f"plan selected chunk count {sum(len(slots) for slots in selected_by_region.values())} != {EXPECTED_CHUNKS}"
        )
    if verify_path and verify_path.exists():
        dynamic_verify = json_load(verify_path)
    else:
        dynamic_verify = None
        input_failures.append("clean-dynamic verification JSON was not supplied")
    source_info: dict[str, Any] = {"path": str(source_archive) if source_archive else None}
    if source_archive:
        source_info["exists"] = source_archive.is_file()
        source_info["bytes"] = source_archive.stat().st_size if source_archive.is_file() else 0
        source_info["sha256"] = sha256_file(source_archive) if source_archive.is_file() else None
        source_info["expected_sha256"] = EXPECTED_ARCHIVE_SHA256
        source_info["matches_expected"] = source_info["sha256"] == EXPECTED_ARCHIVE_SHA256
        if not source_info["matches_expected"]:
            input_failures.append(f"source archive SHA drift: {source_info['sha256']}")

    progress = {"chunks": 0}
    region_rows: list[dict[str, Any]] = []
    for region, slots in sorted(selected_by_region.items()):
        region_rows.append(audit_region(region, slots, clone_world / "region", c_preimage / "region", v_world / "region", progress))

    all_mismatches = [row for region in region_rows for row in region["mismatches"]]
    selected_rows = [row for row in all_mismatches if row.get("scope") == "selected"]
    outside_rows = [row for row in all_mismatches if row.get("scope") == "outside"]
    selected_matched = sum(row["matched_selected"] for row in region_rows)
    outside_matched = sum(row["matched_outside"] for row in region_rows)
    selected_expected_occupied = sum(row["selected_slots"] for row in region_rows)
    outside_expected_occupied = sum(row["c_occupied_slots"] - len(selected_by_region[tuple(row["region"]) ] & set()) for row in []) if False else None
    outside_presence = sum(row["outside_presence_mismatches"] for row in region_rows)
    semantic_mismatch_count = sum(row["semantic_mismatch_count"] for row in region_rows)
    raw_file_diff_count = sum(1 for row in region_rows if row["raw_file_differs_from_expected"])
    field_counts: Counter[str] = Counter()
    for row in region_rows:
        field_counts.update(row["field_mismatch_counts"])
    status = "PASS"
    if input_failures:
        status = "BLOCKED_INPUT_GATE"
    elif all_mismatches:
        status = "BLOCKED_SEMANTIC_TERRAIN_GATE"

    return {
        "schema_version": TOOL_VERSION,
        "generated_at_utc": utc_now(),
        "status": status,
        "operation": "protected-zone-terrain-semantic-post-audit-after-clean-dynamic-stop-readonly",
        "inputs": {
            "clone_world": str(clone_world),
            "c_preimage": str(c_preimage),
            "v_world": str(v_world),
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            "source_archive": source_info,
            "clean_dynamic_verify": {
                "path": str(verify_path) if verify_path else None,
                "sha256": sha256_file(verify_path) if verify_path and verify_path.is_file() else None,
                "status": dynamic_verify.get("status") if isinstance(dynamic_verify, Mapping) else None,
                "raw_mismatch_count": len(dynamic_verify.get("mismatches", [])) if isinstance(dynamic_verify, Mapping) else None,
            },
        },
        "scope": {
            "dimension": "minecraft:overworld",
            "selected_chunks": EXPECTED_CHUNKS,
            "selected_regions": EXPECTED_REGIONS,
            "selected_policy": "V semantic projection",
            "outside_policy": "C preimage semantic projection",
            "ignored": [
                "MCA location allocation, timestamps, compression codec, record padding",
                "entities MCA and entity-only dynamic changes",
                "block_entities, tick lists, light flags, inhabited time, LastUpdate",
            ],
            "compared": ["block states", "biomes", "structures", "heightmaps", "chunk coordinates"],
        },
        "input_failures": input_failures,
        "summary": {
            "selected_expected_slots": selected_expected_occupied,
            "selected_semantically_matched": selected_matched,
            "selected_mismatch_rows": len(selected_rows),
            "outside_semantically_matched": outside_matched,
            "outside_presence_mismatches": outside_presence,
            "outside_mismatch_rows": len(outside_rows),
            "semantic_mismatch_count": semantic_mismatch_count,
            "raw_expected_file_differences_ignored": raw_file_diff_count,
            "field_mismatch_counts": dict(sorted(field_counts.items())),
            "post_clean_dynamic_raw_verify_status": dynamic_verify.get("status") if isinstance(dynamic_verify, Mapping) else None,
        },
        "regions": region_rows,
        "non_actions": {
            "java_started": False,
            "clone_world_modified": False,
            "c_preimage_modified": False,
            "v_world_modified": False,
        },
    }


def markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 保护区 terrain 语义后审计（2026-08-15）",
        "",
        f"**状态：{report['status']}**",
        "",
        "本审计没有启动 Java，也没有修改测试克隆、C preimage 或 V 世界。它在 MCA 解压后的 NBT 层比较 40 个受影响 region 文件：选中槽对 V，未选中槽对 C preimage。",
        "",
        "## 结果",
        "",
        f"- V 选中槽：{summary['selected_semantically_matched']} / {summary['selected_expected_slots']} 语义一致",
        f"- C 区外槽：{summary['outside_semantically_matched']} 语义一致；存在性异常 {summary['outside_presence_mismatches']}",
        f"- 语义不一致记录：{summary['semantic_mismatch_count']}",
        f"- 原始 MCA 文件差异（仅记录，不判失败）：{summary['raw_expected_file_differences_ignored']}",
        f"- 字段差异：{summary['field_mismatch_counts'] or '无'}",
        "",
        "比较字段为 block states、biomes、structures、heightmaps、chunk 坐标。MCA timestamp、压缩/填充、entities MCA、block entities、tick/light/LastUpdate 等均按要求忽略。",
        "",
        "## 动态停服背景",
        "",
        f"clean-dynamic 原始文件校验状态：{summary['post_clean_dynamic_raw_verify_status']}。原始校验发现的实体或 region 字节变化不直接代表地形语义变化，本报告已逐槽解压复核。",
        "",
        "所有不一致槽位、字段摘要和每个 region 的计数都在同名 JSON 中。",
        "",
    ]
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--clone-world", type=Path, required=True)
    result.add_argument("--c-preimage", type=Path, required=True)
    result.add_argument("--v-world", type=Path, required=True)
    result.add_argument("--plan", type=Path, required=True)
    result.add_argument("--clone-verify", type=Path, required=True)
    result.add_argument("--source-archive", type=Path, required=True)
    result.add_argument("--output-json", type=Path, required=True)
    result.add_argument("--output-md", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = build_report(args)
    json_write(args.output_json, report)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown(report), encoding="utf-8")
    sidecar = args.output_json.with_suffix(".sha256")
    paths = [args.output_json.resolve(), args.output_md.resolve(), SCRIPT_DIR / Path(__file__).name]
    sidecar.write_text("\n".join(f"{sha256_file(path)} *{path}" for path in paths) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "summary": report["summary"], "output_json": str(args.output_json.resolve())}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
