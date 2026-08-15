from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import time
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import nbtlib


REGION_RE = re.compile(r"r\.(-?\d+)\.(-?\d+)\.mca$")
HORIZONTAL = {"north", "south", "west", "east"}


def decode(payload: bytes, kind: int) -> bytes:
    kind &= 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported compression {kind}")


def slots(path: Path):
    data = path.read_bytes()
    if not data:
        return
    if len(data) < 8192:
        raise ValueError("non-empty region is shorter than its header")
    locations = data[:4096]
    for slot in range(1024):
        entry = locations[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if not offset:
            continue
        start = offset * 4096
        allocation_end = start + sectors * 4096
        if offset < 2 or not sectors or start + 5 > len(data):
            raise ValueError(f"invalid region slot {slot}")
        length = int.from_bytes(data[start : start + 4], "big")
        if length < 1 or start + 4 + length > min(len(data), allocation_end):
            raise ValueError(f"invalid payload length in slot {slot}")
        yield slot, decode(data[start + 5 : start + 4 + length], data[start + 4])


def scalar(value):
    if value is None:
        return None
    try:
        value = value.unpack()
    except AttributeError:
        pass
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [scalar(child) for child in value]
    return str(value)


def vector3(value):
    raw = scalar(value)
    if isinstance(raw, list) and len(raw) == 3:
        try:
            return [int(part) for part in raw]
        except (TypeError, ValueError):
            return None
    return None


def unpack_block_pos(value):
    packed = int(value) & ((1 << 64) - 1)
    x = (packed >> 38) & 0x3FFFFFF
    z = (packed >> 12) & 0x3FFFFFF
    y = packed & 0xFFF
    if x >= 1 << 25:
        x -= 1 << 26
    if z >= 1 << 25:
        z -= 1 << 26
    if y >= 1 << 11:
        y -= 1 << 12
    return [x, y, z]


def actor_states(contraption):
    blocks = contraption.get("Blocks")
    if not isinstance(blocks, dict):
        return []
    palette = blocks.get("Palette", [])
    block_list = blocks.get("BlockList", [])
    by_pos = {}
    for block in block_list:
        if not isinstance(block, dict) or "Pos" not in block or "State" not in block:
            continue
        by_pos[tuple(unpack_block_pos(block["Pos"]))] = int(block["State"])
    rows = []
    for actor_index, actor in enumerate(contraption.get("Actors", [])):
        if not isinstance(actor, dict):
            rows.append({"actor_index": actor_index, "issues": ["noncompound_actor"]})
            continue
        position = vector3(actor.get("Pos"))
        state_index = by_pos.get(tuple(position)) if position is not None else None
        state = palette[state_index] if state_index is not None and 0 <= state_index < len(palette) else None
        name = str(state.get("Name", "")) if isinstance(state, dict) else None
        properties = state.get("Properties", {}) if isinstance(state, dict) else {}
        facing = str(properties.get("facing")) if isinstance(properties, dict) and "facing" in properties else None
        issues = []
        if position is None:
            issues.append("invalid_actor_position")
        elif state_index is None:
            issues.append("actor_position_missing_from_blocks")
        elif state is None:
            issues.append("actor_state_outside_palette")
        if name == "create:controls" and (facing is None or facing.lower() not in HORIZONTAL):
            issues.append("non_horizontal_controls_facing")
        rows.append(
            {
                "actor_index": actor_index,
                "local_pos": position,
                "state_index": state_index,
                "block": name,
                "facing": facing,
                "issues": issues,
            }
        )
    return rows


def entity_row(entity, relative: str, slot: int, index: int):
    identifier = str(entity.get("id", ""))
    if "Contraption" not in entity and "contraption" not in identifier:
        return None
    contraption = entity.get("Contraption")
    row = {
        "region": relative,
        "slot": slot,
        "entity_index": index,
        "id": identifier,
        "uuid": scalar(entity.get("UUID")),
        "pos": scalar(entity.get("Pos")),
        "initial_orientation": scalar(entity.get("InitialOrientation")),
        "assembly_direction": None,
        "contraption_type": None,
        "actors": 0,
        "actor_states": [],
        "disabled_actors": 0,
        "controls": [],
        "issues": [],
    }
    initial = str(row["initial_orientation"]).lower() if row["initial_orientation"] is not None else None
    if identifier == "create:carriage_contraption":
        if initial is None:
            row["issues"].append("missing_initial_orientation")
        elif initial not in HORIZONTAL:
            row["issues"].append("non_horizontal_initial_orientation")
    if not isinstance(contraption, dict):
        row["issues"].append("missing_or_noncompound_contraption")
        return row
    row["assembly_direction"] = scalar(contraption.get("AssemblyDirection"))
    row["contraption_type"] = scalar(contraption.get("Type"))
    row["actors"] = len(contraption.get("Actors", []))
    row["actor_states"] = actor_states(contraption)
    row["disabled_actors"] = len(contraption.get("DisabledActors", []))
    assembly = str(row["assembly_direction"]).lower() if row["assembly_direction"] is not None else None
    if assembly is not None and assembly not in HORIZONTAL:
        row["issues"].append("non_horizontal_assembly_direction")
    if any(actor["issues"] for actor in row["actor_states"]):
        row["issues"].append("actor_state_issue")
    blocks = contraption.get("Blocks")
    if isinstance(blocks, dict):
        palette = blocks.get("Palette", [])
        block_list = blocks.get("BlockList", [])
        state_counts = Counter(int(block.get("State", -1)) for block in block_list if isinstance(block, dict))
        for palette_index, state in enumerate(palette):
            if not isinstance(state, dict) or str(state.get("Name", "")) != "create:controls":
                continue
            properties = state.get("Properties", {})
            facing = str(properties.get("facing")) if isinstance(properties, dict) and "facing" in properties else None
            control = {
                "palette_index": palette_index,
                "facing": facing,
                "horizontal": facing is not None and facing.lower() in HORIZONTAL,
                "block_instances": state_counts[palette_index],
            }
            row["controls"].append(control)
            if not control["horizontal"]:
                row["issues"].append("non_horizontal_controls_facing")
    return row


def scan_region(job):
    root, path = job
    relative = path.relative_to(root).as_posix()
    rows = []
    chunks = 0
    entities = 0
    errors = []
    try:
        for slot, raw in slots(path):
            chunks += 1
            chunk = nbtlib.File.parse(io.BytesIO(raw))
            values = chunk.get("Entities", [])
            entities += len(values)
            for index, entity in enumerate(values):
                if isinstance(entity, dict):
                    row = entity_row(entity, relative, slot, index)
                    if row is not None:
                        rows.append(row)
    except Exception as exc:  # report and continue; this tool is audit-only
        errors.append({"region": relative, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "region": relative,
        "chunks": chunks,
        "entities": entities,
        "contraptions": rows,
        "errors": errors,
    }


def entity_regions(world: Path):
    return sorted(path for path in world.rglob("entities/r.*.*.mca") if REGION_RE.match(path.name))


def scan_world(label: str, world: Path, workers: int):
    paths = entity_regions(world)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(scan_region, ((world, path) for path in paths)))
    rows = [row for result in results for row in result["contraptions"]]
    errors = [error for result in results for error in result["errors"]]
    return {
        "label": label,
        "world": str(world.resolve()),
        "regions": len(paths),
        "chunks": sum(result["chunks"] for result in results),
        "entities": sum(result["entities"] for result in results),
        "contraptions": rows,
        "errors": errors,
        "counts": {
            "contraptions": len(rows),
            "carriage_contraptions": sum(row["id"] == "create:carriage_contraption" for row in rows),
            "controls_palette_entries": sum(len(row["controls"]) for row in rows),
            "controls_block_instances": sum(
                control["block_instances"] for row in rows for control in row["controls"]
            ),
            "issue_rows": sum(bool(row["issues"]) for row in rows),
            "actor_state_issues": sum(
                bool(actor["issues"]) for row in rows for actor in row["actor_states"]
            ),
            "errors": len(errors),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only full entity-region Create contraption audit")
    parser.add_argument("--world", action="append", nargs=2, metavar=("LABEL", "PATH"), required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.time()
    roots = [scan_world(label, Path(path), max(1, args.workers)) for label, path in args.world]
    report = {
        "category": "create_contraption_entity_regions_read_only_audit",
        "status": "PASS" if all(not root["errors"] for root in roots) else "ERRORS",
        "workers": max(1, args.workers),
        "elapsed_seconds": round(time.time() - started, 3),
        "roots": roots,
        "summary": {
            "regions": sum(root["regions"] for root in roots),
            "chunks": sum(root["chunks"] for root in roots),
            "entities": sum(root["entities"] for root in roots),
            "contraptions": sum(root["counts"]["contraptions"] for root in roots),
            "controls_block_instances": sum(root["counts"]["controls_block_instances"] for root in roots),
            "issue_rows": sum(root["counts"]["issue_rows"] for root in roots),
            "errors": sum(root["counts"]["errors"] for root in roots),
        },
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(hashlib.sha256(payload.encode("utf-8")).hexdigest().upper())
    raise SystemExit(0 if report["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
