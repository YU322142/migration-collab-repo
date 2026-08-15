from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


AXES = {
    "minecraft:wooden_axe",
    "minecraft:stone_axe",
    "minecraft:iron_axe",
    "minecraft:golden_axe",
    "minecraft:diamond_axe",
    "minecraft:netherite_axe",
}

DIMENSIONS = {
    "minecraft:overworld": Path("."),
    "minecraft:the_nether": Path("DIM-1"),
    "minecraft:the_end": Path("DIM1"),
}

NEIGHBORS = (
    (1, 0, "west"),
    (-1, 0, "east"),
    (0, 1, "north"),
    (0, -1, "south"),
)


def value(tag):
    return getattr(tag, "value", tag)


def string(tag) -> str:
    return str(value(tag))


def number(tag) -> float:
    return float(value(tag))


def decode_uuid(entity) -> str | None:
    raw = entity.get("UUID")
    if raw is None:
        return None
    parts = [int(value(part)) & 0xFFFFFFFF for part in raw]
    if len(parts) != 4:
        return None
    return "".join(f"{part:08x}" for part in parts)


def item_components(item) -> dict:
    components = item.get("components")
    if components is None:
        return {}
    result = {}
    for component in components.tags:
        key = component.name
        if key == "minecraft:damage":
            result[key] = int(value(component))
        elif key in {"minecraft:enchantments", "minecraft:unbreakable"}:
            result[key] = str(component)
    return result


def parse_region_name(path: Path) -> tuple[int, int]:
    match = re.fullmatch(r"r\.(-?\d+)\.(-?\d+)\.mca", path.name)
    if not match:
        raise ValueError(f"invalid region filename: {path.name}")
    return int(match.group(1)), int(match.group(2))


def get_sections(chunk):
    root = chunk.get("Level", chunk)
    return root.get("sections", root.get("Sections", []))


def palette_state(entry) -> dict:
    name = string(entry.get("Name", entry.get("name", "minecraft:air")))
    properties = entry.get("Properties", entry.get("properties"))
    props = {}
    if properties is not None:
        for prop in properties.tags:
            props[prop.name] = string(prop)
    return {"name": name, "properties": props}


def section_block(section, x: int, y: int, z: int) -> dict:
    states = section.get("block_states", section.get("BlockStates"))
    if states is None:
        return {"name": "minecraft:air", "properties": {}}
    palette = states.get("palette", states.get("Palette", []))
    if not palette:
        return {"name": "minecraft:air", "properties": {}}
    if len(palette) == 1:
        return palette_state(palette[0])
    data = states.get("data", states.get("Data"))
    if data is None:
        return palette_state(palette[0])
    bits = max(4, (len(palette) - 1).bit_length())
    values_per_long = 64 // bits
    index = (y << 8) | (z << 4) | x
    raw = int(value(data[index // values_per_long])) & 0xFFFFFFFFFFFFFFFF
    palette_index = (raw >> ((index % values_per_long) * bits)) & ((1 << bits) - 1)
    if palette_index >= len(palette):
        return {"name": "<invalid-palette-index>", "properties": {}}
    return palette_state(palette[palette_index])


def load_blocks(world: Path, nbt, read_slots, decode, requests: dict) -> dict:
    results = {}
    by_region = defaultdict(lambda: defaultdict(list))
    for dimension, positions in requests.items():
        for position in positions:
            x, y, z = position
            chunk_x, chunk_z = x // 16, z // 16
            region = (chunk_x // 32, chunk_z // 32)
            slot = (chunk_x & 31) + (chunk_z & 31) * 32
            by_region[(dimension, region)][slot].append(position)

    for (dimension, (region_x, region_z)), slots in by_region.items():
        relative = DIMENSIONS[dimension]
        path = world / relative / "region" / f"r.{region_x}.{region_z}.mca"
        if not path.exists():
            continue
        for slot, _offset, _sectors, compression, payload in read_slots(path):
            positions = slots.get(slot)
            if not positions:
                continue
            chunk = nbt.NBTFile(buffer=io.BytesIO(decode(payload, compression)))
            sections = {int(value(section.get("Y"))): section for section in get_sections(chunk)}
            for x, y, z in positions:
                section = sections.get(y // 16)
                if section is None:
                    state = {"name": "minecraft:air", "properties": {}}
                else:
                    state = section_block(section, x & 15, y & 15, z & 15)
                results[(dimension, x, y, z)] = state
    return results


def scan_entities(world: Path, nbt, read_slots, decode):
    item_frames = []
    failures = []
    type_counts = Counter()
    for dimension, relative in DIMENSIONS.items():
        folder = world / relative / "entities"
        for path in sorted(folder.glob("r.*.*.mca")):
            try:
                for slot, _offset, _sectors, compression, payload in read_slots(path):
                    chunk = nbt.NBTFile(buffer=io.BytesIO(decode(payload, compression)))
                    for entity in chunk.get("Entities", []):
                        identifier = string(entity.get("id", ""))
                        type_counts[identifier] += 1
                        if identifier != "minecraft:item_frame":
                            continue
                        item = entity.get("Item")
                        if item is None:
                            continue
                        item_id = string(item.get("id", ""))
                        if item_id not in AXES:
                            continue
                        pos = [number(part) for part in entity.get("Pos", [])]
                        if len(pos) != 3:
                            continue
                        item_frames.append(
                            {
                                "dimension": dimension,
                                "region": path.name,
                                "slot": slot,
                                "uuid": decode_uuid(entity),
                                "pos": pos,
                                "block_pos": [math.floor(part) for part in pos],
                                "facing": int(value(entity.get("Facing", 0))),
                                "item": item_id,
                                "item_count": int(value(item.get("count", item.get("Count", 0)))),
                                "components": item_components(item),
                                "tags": [string(tag) for tag in entity.get("Tags", [])],
                            }
                        )
            except Exception as exc:  # keep the full-world audit useful
                failures.append({"dimension": dimension, "region": path.name, "error": str(exc)})
    return item_frames, type_counts, failures


def find_strings(node, prefix=""):
    hits = []
    if node.__class__.__name__ == "TAG_List":
        for index, child in enumerate(node):
            child_path = f"{prefix}[{index}]"
            if child.__class__.__name__ == "TAG_String" and "potted_farms" in string(child):
                hits.append({"path": child_path, "value": string(child)})
            hits.extend(find_strings(child, child_path))
    elif node.__class__.__name__ in {"NBTFile", "TAG_Compound"} or hasattr(node, "tags"):
        for child in node.tags:
            child_path = f"{prefix}.{child.name}" if prefix else child.name
            if child.__class__.__name__ == "TAG_String" and "potted_farms" in string(child):
                hits.append({"path": child_path, "value": string(child)})
            hits.extend(find_strings(child, child_path))
    return hits


def scan_named_data(world: Path, nbt):
    result = {}
    for relative in (Path("level.dat"), Path("data/scoreboard.dat"), Path("data/command_storage_minecraft.dat")):
        path = world / relative
        if not path.exists():
            continue
        root = nbt.NBTFile(filename=str(path))
        result[str(relative).replace("\\", "/")] = find_strings(root)
    return result


def classify_farms(frames, blocks):
    farms = []
    for frame in frames:
        dimension = frame["dimension"]
        x, y, z = frame["block_pos"]
        center = blocks.get((dimension, x, y - 1, z), {"name": "<unloaded>", "properties": {}})
        plots = []
        for dx, dz, facing in NEIGHBORS:
            plant = blocks.get((dimension, x + dx, y, z + dz), {"name": "<unloaded>", "properties": {}})
            hopper = blocks.get((dimension, x + dx, y - 1, z + dz), {"name": "<unloaded>", "properties": {}})
            if plant["name"].startswith("minecraft:potted_") or plant["name"].startswith("backport:potted_"):
                plots.append(
                    {
                        "offset": [dx, dz],
                        "plant": plant,
                        "hopper": hopper,
                        "required_facing": facing,
                        "valid": hopper["name"] == "minecraft:hopper" and hopper["properties"].get("facing") == facing,
                    }
                )
        farms.append(
            {
                **frame,
                "center_below": center,
                "plots": plots,
                "operational_structure": center["name"] == "minecraft:hopper" and any(plot["valid"] for plot in plots),
            }
        )
    return farms


def main():
    parser = argparse.ArgumentParser(description="Read-only Potted Farms state inventory")
    parser.add_argument("world", type=Path)
    parser.add_argument("--nbt-path", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    sys.path.insert(0, str(args.nbt_path))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from nbt import nbt
    from convert_world_nbt import decode, read_slots

    frames, type_counts, failures = scan_entities(args.world, nbt, read_slots, decode)
    requests = defaultdict(set)
    for frame in frames:
        x, y, z = frame["block_pos"]
        dimension = frame["dimension"]
        requests[dimension].add((x, y - 1, z))
        for dx, dz, _facing in NEIGHBORS:
            requests[dimension].add((x + dx, y, z + dz))
            requests[dimension].add((x + dx, y - 1, z + dz))
    blocks = load_blocks(args.world, nbt, read_slots, decode, requests)
    farms = classify_farms(frames, blocks)
    report = {
        "world": str(args.world.resolve()),
        "read_only": True,
        "entity_region_failures": failures,
        "item_frame_count": type_counts.get("minecraft:item_frame", 0),
        "axe_item_frames": len(frames),
        "operational_potted_farm_structures": sum(farm["operational_structure"] for farm in farms),
        "farms": farms,
        "named_persistent_data": scan_named_data(args.world, nbt),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
