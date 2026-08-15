from __future__ import annotations

import argparse
import gzip
import io
import json
import zlib
from collections import Counter, defaultdict
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


def decompress(payload: bytes, compression: int) -> bytes:
    compression &= 0x7F
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"unsupported compression {compression}")


def read_region(path: Path):
    with path.open("rb") as handle:
        locations = handle.read(4096)
        for slot in range(1024):
            loc = locations[slot * 4:(slot + 1) * 4]
            offset = int.from_bytes(loc[:3], "big")
            if not offset:
                continue
            handle.seek(offset * 4096)
            length = int.from_bytes(handle.read(4), "big")
            compression = handle.read(1)[0]
            payload = decompress(handle.read(length - 1), compression)
            yield slot, nbtlib.File.parse(io.BytesIO(payload), byteorder="big")


def roots(server: Path, kind: str):
    for relative, dimension in (
        (Path("world") / kind, "minecraft:overworld"),
        (Path("world") / "DIM-1" / kind, "minecraft:the_nether"),
        (Path("world") / "DIM1" / kind, "minecraft:the_end"),
    ):
        root = server / relative
        if root.exists():
            yield root, dimension


def values(chunk, names):
    for name in names:
        if name in chunk:
            return chunk[name]
    level = chunk.get("Level")
    if isinstance(level, dict):
        for name in names:
            if name in level:
                return level[name]
    return []


def uuid_text(entity):
    value = plain(entity.get("UUID"))
    if isinstance(value, str):
        return value.replace("-", "").lower()
    if isinstance(value, list) and len(value) == 4:
        number = 0
        for part in value:
            number = (number << 32) | (int(part) & 0xFFFFFFFF)
        return f"{number:032x}"
    return None


def scan(server: Path, kind: str, region_names: set[str] | None = None):
    result = []
    for root, dimension in roots(server, kind):
        for region in sorted(root.glob("*.mca")):
            if region_names is not None and region.name not in region_names:
                continue
            for slot, chunk in read_region(region):
                for index, value in enumerate(values(chunk, ("Entities", "entities") if kind == "entities" else ("block_entities", "BlockEntities", "blockEntities"))):
                    item = plain(value)
                    item["_meta"] = {"dimension": dimension, "region": region.name, "slot": slot, "index": index}
                    result.append(item)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("target", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--regions", nargs="*", help="Only inspect named MCA files, e.g. r.0.0.mca")
    args = ap.parse_args()
    region_names = set(args.regions) if args.regions else None
    source_entities = scan(args.source, "entities", region_names)
    target_entities = scan(args.target, "entities", region_names)
    source_blocks = scan(args.source, "region", region_names)
    target_blocks = scan(args.target, "region", region_names)

    wanted_entity_ids = {"minecraft:cherry_boat", "create:super_glue", "minecraft:zombie", "minecraft:enderman", "minecraft:chicken", "immersive_paintings:painting", "immersive_paintings:glow_painting", "immersive_paintings:glow_graffiti"}
    src_by_uuid = {uuid_text(e): e for e in source_entities if uuid_text(e)}
    dst_by_uuid = {uuid_text(e): e for e in target_entities if uuid_text(e)}
    entity_samples = {}
    for uid, e in src_by_uuid.items():
        if e.get("id") not in wanted_entity_ids:
            continue
        d = dst_by_uuid.get(uid)
        if e.get("id") in entity_samples:
            continue
        entity_samples[e.get("id")] = {"source": e, "target": d}
    # Ensure all missing/changed super glue and boat records are represented.
    entity_groups = defaultdict(list)
    for e in source_entities:
        if e.get("id") in wanted_entity_ids:
            uid = uuid_text(e)
            d = dst_by_uuid.get(uid)
            if d is None or e.get("id") == "create:super_glue":
                entity_groups[e.get("id")].append({"source": e, "target": d})

    block_counts = {"source": Counter(str(e.get("id")) for e in source_blocks), "target": Counter(str(e.get("id")) for e in target_blocks)}
    wanted_block_ids = {"create:bracketed_kinetic", "create:schematicannon", "create:schematicannon", "toms_storage:storage_terminal", "toms_storage:inventory_cable", "toms_storage:inventory_connector", "toms_storage:filtered_inventory_connector", "minecraft:sign", "minecraft:hanging_sign"}
    block_samples = {}
    for bid in sorted(set(block_counts["source"]) | set(block_counts["target"])):
        if bid not in wanted_block_ids and not bid.startswith("toms_storage:") and bid not in {"create:bracketed_kinetic", "create:schematicannon"}:
            continue
        src = next((e for e in source_blocks if str(e.get("id")) == bid), None)
        dst = next((e for e in target_blocks if str(e.get("id")) == bid), None)
        block_samples[bid] = {"source": src, "target": dst}

    out = {
        "entity_counts": {"source": Counter(str(e.get("id")) for e in source_entities), "target": Counter(str(e.get("id")) for e in target_entities)},
        "entity_samples": entity_samples,
        "entity_groups": entity_groups,
        "block_counts": {"source": block_counts["source"], "target": block_counts["target"]},
        "block_samples": block_samples,
    }
    # Counters are not JSON serializable.
    def normalize(v):
        if isinstance(v, Counter):
            return dict(v)
        if isinstance(v, dict):
            return {str(k): normalize(x) for k, x in v.items()}
        if isinstance(v, list):
            return [normalize(x) for x in v]
        return v
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(normalize(out), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_entities": len(source_entities), "target_entities": len(target_entities), "source_block_entities": len(source_blocks), "target_block_entities": len(target_blocks), "block_ids": sorted(block_samples)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
