"""Audit data lost while loading a bounded set of Anvil regions.

The report intentionally keeps only identifiers, positions, and attachment
fields needed to explain loader warnings; it does not copy arbitrary NBT.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

from inspect_schema_samples import plain, scan, uuid_text


# These entity types inherit the 1.21.1 BlockAttachedEntity/HangingEntity
# serializer and require legacy TileX/TileY/TileZ anchors.  Create Super Glue
# is deliberately excluded: it is a normal Entity with a From/To bounding box.
ATTACHED_IDS = {
    "minecraft:painting",
    "minecraft:item_frame",
    "minecraft:glow_item_frame",
    "minecraft:leash_knot",
    "immersive_paintings:painting",
    "immersive_paintings:glow_painting",
    "immersive_paintings:graffiti",
    "immersive_paintings:glow_graffiti",
}
BLOCK_IDS = {"create:schematicannon", "create:bracketed_kinetic"}


def _meta(value: dict) -> dict:
    return {
        "dimension": value.get("_meta", {}).get("dimension"),
        "region": value.get("_meta", {}).get("region"),
        "slot": value.get("_meta", {}).get("slot"),
        "index": value.get("_meta", {}).get("index"),
    }


def _block_summary(value: dict) -> dict:
    fields = {
        "id": str(value.get("id", "<missing>")),
        "x": value.get("x"),
        "y": value.get("y"),
        "z": value.get("z"),
        "meta": _meta(value),
    }
    for key in ("State", "state", "Status", "Mode", "Progress", "Running", "Contraption"):
        if key in value:
            fields[key] = plain(value[key])
    return fields


def _entity_summary(value: dict) -> dict:
    fields = {
        "id": str(value.get("id", "<missing>")),
        "uuid": uuid_text(value),
        "pos": plain(value.get("Pos", [])),
        "meta": _meta(value),
    }
    tile = [value.get(key) for key in ("TileX", "TileY", "TileZ")]
    if any(item is not None for item in tile):
        fields["tile"] = plain(tile)
    for key in ("block_pos", "BlockPos", "Facing", "Direction", "Rotation", "Item", "Variant"):
        if key in value:
            fields[key] = plain(value[key])
    return fields


def _attachment_probe(value: dict) -> dict:
    tile_keys = [key for key in ("TileX", "TileY", "TileZ") if key in value]
    tile = [plain(value.get(key)) for key in ("TileX", "TileY", "TileZ")]
    block_pos = plain(value.get("block_pos", value.get("BlockPos")))
    return {
        "id": str(value.get("id", "<missing>")),
        "uuid": uuid_text(value),
        "pos": plain(value.get("Pos", [])),
        "tile_keys": tile_keys,
        "tile": tile,
        "block_pos": block_pos,
        "meta": _meta(value),
    }


def _key(value: dict, kind: str, index: int) -> str:
    meta = _meta(value)
    if kind == "block":
        return "|".join(
            str(item)
            for item in (
                meta["dimension"],
                value.get("id"),
                value.get("x"),
                value.get("y"),
                value.get("z"),
            )
        )
    uid = uuid_text(value)
    if uid:
        return f"uuid:{uid}"
    return "|".join(str(item) for item in (meta["dimension"], value.get("id"), tuple(plain(value.get("Pos", [])))))


def _index(values: list[dict], kind: str, allowed: set[str] | None = None) -> dict[str, dict]:
    records = {}
    occurrences = collections.Counter()
    for index, value in enumerate(values):
        identifier = str(value.get("id", "<missing>"))
        if allowed is not None and identifier not in allowed:
            continue
        base_key = _key(value, kind, index)
        occurrence = occurrences[base_key]
        occurrences[base_key] += 1
        key = base_key if occurrence == 0 else f"{base_key}|dup{occurrence}"
        records[key] = value
    return records


def _stable(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def audit(source: Path, target: Path, regions: list[str]) -> dict:
    source_entities = scan(source, "entities", set(regions))
    target_entities = scan(target, "entities", set(regions))
    source_blocks = scan(source, "region", set(regions))
    target_blocks = scan(target, "region", set(regions))

    source_block_index = _index(source_blocks, "block")
    target_block_index = _index(target_blocks, "block")
    missing_blocks = [
        _block_summary(source_block_index[key])
        for key in sorted(set(source_block_index) - set(target_block_index))
    ]
    target_blocks_by_key = {
        key: _block_summary(value) for key, value in target_block_index.items()
    }

    source_attached = _index(source_entities, "entity", ATTACHED_IDS)
    target_attached = _index(target_entities, "entity", ATTACHED_IDS)
    missing_attached = [
        _entity_summary(source_attached[key])
        for key in sorted(set(source_attached) - set(target_attached))
    ]
    changed_attached = []
    for key in sorted(set(source_attached) & set(target_attached)):
        source_summary = _entity_summary(source_attached[key])
        target_summary = _entity_summary(target_attached[key])
        if _stable(source_summary) != _stable(target_summary):
            changed_attached.append({"source": source_summary, "target": target_summary})

    suspicious_attached = []
    for value in source_entities:
        if str(value.get("id")) not in ATTACHED_IDS:
            continue
        tile = [plain(value.get(key)) for key in ("TileX", "TileY", "TileZ")]
        block_pos = plain(value.get("block_pos", value.get("BlockPos")))
        if (not all(key in value for key in ("TileX", "TileY", "TileZ"))) or tile == [0, 0, 0] or block_pos in ([0, 0, 0], [0, 0, 0, 0]):
            suspicious_attached.append(_attachment_probe(value))

    counts = {
        "source_block_entities": len(source_blocks),
        "target_block_entities": len(target_blocks),
        "source_attached_entities": len([x for x in source_entities if str(x.get("id")) in ATTACHED_IDS]),
        "target_attached_entities": len([x for x in target_entities if str(x.get("id")) in ATTACHED_IDS]),
        "source_block_ids": dict(collections.Counter(str(x.get("id")) for x in source_blocks).most_common()),
        "target_block_ids": dict(collections.Counter(str(x.get("id")) for x in target_blocks).most_common()),
        "source_attached_ids": dict(collections.Counter(str(x.get("id")) for x in source_entities if str(x.get("id")) in ATTACHED_IDS).most_common()),
        "target_attached_ids": dict(collections.Counter(str(x.get("id")) for x in target_entities if str(x.get("id")) in ATTACHED_IDS).most_common()),
    }
    return {
        "schema": 1,
        "source": str(source.resolve()),
        "target": str(target.resolve()),
        "regions": sorted(regions),
        "counts": counts,
        "missing_block_entities": missing_blocks,
        "missing_attached_entities": missing_attached,
        "changed_attached_entities": changed_attached,
        "suspicious_attached_entities": suspicious_attached,
        "source_relevant_block_entities": [
            _block_summary(value) for value in source_block_index.values() if str(value.get("id")) in BLOCK_IDS
        ],
        "target_relevant_block_entities": [
            value for key, value in target_blocks_by_key.items() if str(value.get("id")) in BLOCK_IDS
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--regions", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.source.resolve(), args.target.resolve(), args.regions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "missing_block_entities": len(result["missing_block_entities"]), "missing_attached_entities": len(result["missing_attached_entities"]), "changed_attached_entities": len(result["changed_attached_entities"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
