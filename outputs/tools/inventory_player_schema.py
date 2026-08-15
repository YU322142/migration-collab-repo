from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import nbtlib


def plain(value):
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def visit_items(value, ids, components):
    if isinstance(value, dict):
        if isinstance(value.get("id"), str) and ":" in value["id"]:
            ids[value["id"]] += int(value.get("count", 1) or 1)
        comp = value.get("components")
        if isinstance(comp, dict):
            components.update(comp.keys())
        for child in value.values():
            visit_items(child, ids, components)
    elif isinstance(value, list):
        for child in value:
            visit_items(child, ids, components)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("player_dir", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    top_keys = collections.Counter()
    equipment_slots = collections.Counter()
    equipment_items = collections.Counter()
    attribute_ids = collections.Counter()
    attribute_bases = collections.defaultdict(collections.Counter)
    component_ids = collections.Counter()
    item_ids = collections.Counter()
    respawn_dimensions = collections.Counter()
    respawn_pitch = collections.Counter()
    respawn_forced = collections.Counter()
    special_values = collections.defaultdict(collections.Counter)
    collisions = []
    files = list(sorted(args.player_dir.glob("*.dat")))
    for path in files:
        root = plain(nbtlib.load(path))
        top_keys.update(root.keys())
        visit_items({"Inventory": root.get("Inventory", []), "EnderItems": root.get("EnderItems", []), "equipment": root.get("equipment", {})}, item_ids, component_ids)
        equipment = root.get("equipment", {})
        if isinstance(equipment, dict):
            for slot, item in equipment.items():
                equipment_slots[slot] += 1
                if isinstance(item, dict) and item.get("id"):
                    equipment_items[f"{slot}|{item['id']}"] += 1
        occupied_legacy = []
        for item in root.get("Inventory", []):
            if isinstance(item, dict) and int(item.get("Slot", 0)) & 0xFF >= 100:
                occupied_legacy.append({"slot": int(item.get("Slot")) & 0xFF, "id": item.get("id")})
        if equipment and occupied_legacy:
            collisions.append({"file": path.name, "legacy": occupied_legacy, "equipment": sorted(equipment)})
        for attribute in root.get("attributes", []):
            if isinstance(attribute, dict):
                identifier = str(attribute.get("id"))
                attribute_ids[identifier] += 1
                attribute_bases[identifier][str(attribute.get("base"))] += 1
        respawn = root.get("respawn")
        if isinstance(respawn, dict):
            respawn_dimensions[str(respawn.get("dimension"))] += 1
            respawn_pitch[str(respawn.get("pitch", 0.0))] += 1
            respawn_forced[str(respawn.get("forced", False))] += 1
        for key in ("fall_distance", "spawn_extra_particles_on_fall", "ignore_fall_damage_from_current_explosion", "current_impulse_context_reset_grace_time"):
            if key in root:
                special_values[key][str(root[key])] += 1
    out = {
        "files": len(files),
        "top_keys": dict(top_keys),
        "equipment_slots": dict(equipment_slots),
        "equipment_items": dict(equipment_items),
        "attribute_ids": dict(attribute_ids),
        "attribute_bases": {k: dict(v) for k, v in attribute_bases.items()},
        "item_ids": dict(item_ids),
        "component_ids": dict(component_ids),
        "respawn_dimensions": dict(respawn_dimensions),
        "respawn_pitch": dict(respawn_pitch),
        "respawn_forced": dict(respawn_forced),
        "special_values": {k: dict(v) for k, v in special_values.items()},
        "legacy_equipment_collisions": collisions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("files", "equipment_slots", "attribute_ids", "respawn_dimensions", "respawn_pitch", "legacy_equipment_collisions")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
