from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


DIMENSIONS = {
    "minecraft:overworld": Path("."),
    "minecraft:the_nether": Path("DIM-1"),
    "minecraft:the_end": Path("DIM1"),
}


def value(tag):
    return getattr(tag, "value", tag)


def string(tag) -> str:
    return str(value(tag))


def state(entry) -> dict:
    name = string(entry.get("Name", entry.get("name", "minecraft:air")))
    properties = entry.get("Properties", entry.get("properties"))
    result = {}
    if properties is not None:
        for prop in properties.tags:
            result[prop.name] = string(prop)
    return {"name": name, "properties": result}


def sections(chunk):
    root = chunk.get("Level", chunk)
    return root.get("sections", root.get("Sections", []))


def palette_values(section):
    block_states = section.get("block_states", section.get("BlockStates"))
    if block_states is None:
        return [], None
    palette = block_states.get("palette", block_states.get("Palette", []))
    data = block_states.get("data", block_states.get("Data"))
    return palette, data


def palette_index(data, index: int, palette_size: int) -> int:
    if data is None or palette_size <= 1:
        return 0
    bits = max(4, (palette_size - 1).bit_length())
    per_long = 64 // bits
    raw = int(value(data[index // per_long])) & 0xFFFFFFFFFFFFFFFF
    return (raw >> ((index % per_long) * bits)) & ((1 << bits) - 1)


def parse_region_name(path: Path):
    _, rx, rz, _extension = path.name.split(".")
    return int(rx), int(rz)


def scan(world: Path, nbt, read_slots, decode):
    counts = Counter()
    positions = []
    failures = []
    for dimension, relative in DIMENSIONS.items():
        folder = world / relative / "region"
        for path in sorted(folder.glob("r.*.*.mca")):
            try:
                region_x, region_z = parse_region_name(path)
                for slot, _offset, _sectors, compression, payload in read_slots(path):
                    chunk = nbt.NBTFile(buffer=io.BytesIO(decode(payload, compression)))
                    chunk_x = region_x * 32 + (slot & 31)
                    chunk_z = region_z * 32 + (slot >> 5)
                    for section in sections(chunk):
                        section_y = int(value(section.get("Y", 0)))
                        palette, data = palette_values(section)
                        if not palette:
                            continue
                        states = [state(entry) for entry in palette]
                        potted_indexes = {index for index, item in enumerate(states) if item["name"].startswith("minecraft:potted_") or item["name"].startswith("backport:potted_")}
                        if not potted_indexes:
                            continue
                        for index in range(4096):
                            palette_id = palette_index(data, index, len(states))
                            if palette_id not in potted_indexes:
                                continue
                            x = chunk_x * 16 + (index & 15)
                            z = chunk_z * 16 + ((index >> 4) & 15)
                            y = section_y * 16 + (index >> 8)
                            block = states[palette_id]
                            counts[block["name"]] += 1
                            positions.append({"dimension": dimension, "pos": [x, y, z], "state": block})
            except Exception as exc:
                failures.append({"dimension": dimension, "region": path.name, "error": str(exc)})
    return counts, positions, failures


def main():
    parser = argparse.ArgumentParser(description="Read-only inventory of every Potted Farms block candidate")
    parser.add_argument("world", type=Path)
    parser.add_argument("--nbt-path", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.nbt_path))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from nbt import nbt
    from convert_world_nbt import decode, read_slots
    from audit_potted_farms_world import load_blocks, NEIGHBORS

    counts, positions, failures = scan(args.world, nbt, read_slots, decode)
    requests = defaultdict(set)
    for record in positions:
        dimension = record["dimension"]
        x, y, z = record["pos"]
        for dx, dz, _facing in NEIGHBORS:
            requests[dimension].add((x - dx, y - 1, z - dz))
            requests[dimension].add((x, y - 1, z))
    blocks = load_blocks(args.world, nbt, read_slots, decode, requests)
    pairs = []
    for record in positions:
        dimension = record["dimension"]
        x, y, z = record["pos"]
        for dx, dz, facing in NEIGHBORS:
            frame_x, frame_z = x - dx, z - dz
            center = blocks.get((dimension, frame_x, y - 1, frame_z), {"name": "<missing>", "properties": {}})
            side = blocks.get((dimension, x, y - 1, z), {"name": "<missing>", "properties": {}})
            # A canonical farm has a hopper below the frame and a second hopper
            # below the pot, pointing toward the frame.
            if center["name"] == "minecraft:hopper" and side["name"] == "minecraft:hopper" and side["properties"].get("facing") == facing:
                pairs.append({"dimension": dimension, "pot_pos": [x, y, z], "frame_pos": [frame_x, y, frame_z], "facing": facing, "pot": record["state"]})
                break
    report = {
        "world": str(args.world.resolve()),
        "read_only": True,
        "region_failures": failures,
        "potted_block_counts": dict(sorted(counts.items())),
        "potted_block_total": sum(counts.values()),
        "canonical_hopper_pairs": pairs,
        "canonical_hopper_pair_count": len(pairs),
        "potted_positions": positions,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
