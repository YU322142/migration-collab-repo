"""Decode and compare block-state storage for selected Anvil chunk slots."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any

import nbtlib

import audit_full_world_transfer as audit


def read_slot(path: Path, slot: int) -> dict[str, Any]:
    data = path.read_bytes()
    entry = data[slot * 4 : slot * 4 + 4]
    offset = int.from_bytes(entry[:3], "big")
    sectors = entry[3]
    if not offset or not sectors:
        raise ValueError(f"slot {slot} is empty in {path}")
    start = offset * 4096
    length = int.from_bytes(data[start : start + 4], "big")
    compression = data[start + 4]
    payload = data[start + 5 : start + 4 + length]
    root = nbtlib.File.parse(io.BytesIO(audit.decompress(payload, compression)), byteorder="big")
    return audit.plain(root)


def sections(root: dict[str, Any]) -> dict[int, dict[str, Any]]:
    raw = audit.find_value(root, ("sections", "Sections"))
    result: dict[int, dict[str, Any]] = {}
    for section in raw if isinstance(raw, list) else []:
        if not isinstance(section, dict):
            continue
        y = section.get("Y", section.get("y"))
        if type(y) is int:
            result[y] = section
    return result


def block_container(section: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("block_states", "BlockStates"):
        value = section.get(key)
        if isinstance(value, dict):
            return value
    return None


def palette_state(value: Any) -> str:
    return audit.canonical_json(value)


def decode_section(section: dict[str, Any] | None) -> list[str]:
    if section is None:
        return [palette_state({"Name": "minecraft:air"})] * 4096
    container = block_container(section)
    if not container:
        return [palette_state({"Name": "minecraft:air"})] * 4096
    palette = container.get("palette", container.get("Palette"))
    if not isinstance(palette, list) or not palette:
        raise ValueError("block-state palette is missing or empty")
    names = [palette_state(value) for value in palette]
    data = container.get("data", container.get("Data"))
    if len(names) == 1 and not data:
        return [names[0]] * 4096
    if not isinstance(data, list):
        raise ValueError("multi-entry block-state palette has no packed data")
    bits = max(4, (len(names) - 1).bit_length())
    values_per_long = 64 // bits
    mask = (1 << bits) - 1
    decoded: list[str] = []
    for index in range(4096):
        long_index = index // values_per_long
        if long_index >= len(data):
            raise ValueError(f"packed data ended at long {len(data)}, need {long_index + 1}")
        raw = int(data[long_index]) & 0xFFFFFFFFFFFFFFFF
        palette_index = (raw >> ((index % values_per_long) * bits)) & mask
        if palette_index >= len(names):
            raise ValueError(f"palette index {palette_index} is outside palette size {len(names)}")
        decoded.append(names[palette_index])
    return decoded


def component_hashes(section: dict[str, Any] | None) -> dict[str, str | None]:
    if section is None:
        return {key: None for key in ("block_states", "biomes", "block_light", "sky_light")}
    lowered = {str(key).lower(): value for key, value in section.items()}
    aliases = {
        "block_states": ("block_states", "blockstates"),
        "biomes": ("biomes",),
        "block_light": ("blocklight", "block_light"),
        "sky_light": ("skylight", "sky_light"),
    }
    result: dict[str, str | None] = {}
    for label, names in aliases.items():
        value = next((lowered[name] for name in names if name in lowered), None)
        result[label] = audit.digest_value(value) if value is not None else None
    return result


def compare(source_path: Path, target_path: Path, slots: list[int]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "source": str(source_path.resolve()),
        "target": str(target_path.resolve()),
        "source_sha256": audit.digest_file(source_path),
        "target_sha256": audit.digest_file(target_path),
        "slots": [],
    }
    for slot in slots:
        left_root = read_slot(source_path, slot)
        right_root = read_slot(target_path, slot)
        left_sections = sections(left_root)
        right_sections = sections(right_root)
        chunk_x, chunk_z = audit.chunk_position(left_root)
        changes: list[dict[str, Any]] = []
        section_reports = []
        for section_y in sorted(set(left_sections) | set(right_sections)):
            left_section = left_sections.get(section_y)
            right_section = right_sections.get(section_y)
            left_blocks = decode_section(left_section)
            right_blocks = decode_section(right_section)
            section_changes = 0
            for index, (left, right) in enumerate(zip(left_blocks, right_blocks)):
                if left == right:
                    continue
                section_changes += 1
                local_x = index & 15
                local_z = (index >> 4) & 15
                local_y = (index >> 8) & 15
                if len(changes) < 500:
                    changes.append(
                        {
                            "pos": [chunk_x * 16 + local_x, section_y * 16 + local_y, chunk_z * 16 + local_z],
                            "source": json.loads(left),
                            "target": json.loads(right),
                        }
                    )
            left_hashes = component_hashes(left_section)
            right_hashes = component_hashes(right_section)
            if section_changes or left_hashes != right_hashes:
                section_reports.append(
                    {
                        "section_y": section_y,
                        "changed_block_positions": section_changes,
                        "source_components": left_hashes,
                        "target_components": right_hashes,
                    }
                )
        report["slots"].append(
            {
                "slot": slot,
                "chunk": [chunk_x, chunk_z],
                "source_data_version": left_root.get("DataVersion"),
                "target_data_version": right_root.get("DataVersion"),
                "changed_block_positions": len(changes) if len(changes) < 500 else sum(item["changed_block_positions"] for item in section_reports),
                "change_sample": changes,
                "sections_with_storage_differences": section_reports,
            }
        )
    report["total_changed_block_positions"] = sum(item["changed_block_positions"] for item in report["slots"])
    report["block_states_semantically_equal"] = report["total_changed_block_positions"] == 0
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--slot", action="append", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.source, args.target, args.slot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "block_states_semantically_equal": report["block_states_semantically_equal"],
        "total_changed_block_positions": report["total_changed_block_positions"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
