from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import io
import json
import zlib
from pathlib import Path

import nbtlib


def plain(value):
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    return value


def decompress(payload: bytes, compression: int) -> bytes:
    compression &= 0x7F
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"unsupported compression type {compression}")


def read_region(path: Path):
    if path.stat().st_size == 0:
        return
    with path.open("rb") as handle:
        locations = handle.read(4096)
        if len(locations) != 4096:
            raise ValueError("region location table is truncated")
        for slot in range(1024):
            entry = locations[slot * 4:(slot + 1) * 4]
            offset = int.from_bytes(entry[:3], "big")
            if not offset:
                continue
            handle.seek(offset * 4096)
            length_bytes = handle.read(4)
            if len(length_bytes) != 4:
                raise ValueError(f"slot {slot} chunk header is truncated")
            length = int.from_bytes(length_bytes, "big")
            compression_raw = handle.read(1)
            if len(compression_raw) != 1 or length < 1:
                raise ValueError(f"slot {slot} has an invalid chunk header")
            compression = compression_raw[0]
            if compression & 0x80:
                raise ValueError(f"slot {slot} uses an external chunk stream")
            payload = handle.read(length - 1)
            if len(payload) != length - 1:
                raise ValueError(f"slot {slot} payload is truncated")
            raw = decompress(payload, compression)
            yield slot, nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def tag_name(value):
    return type(value).__name__.removeprefix("TAG_")


def type_signature(value, depth=0):
    if depth >= 8:
        return tag_name(value)
    if isinstance(value, dict):
        fields = ",".join(
            f"{key}:{type_signature(child, depth + 1)}"
            for key, child in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
        return f"{tag_name(value)}{{{fields}}}"
    if isinstance(value, (list, tuple)):
        children = sorted({type_signature(child, depth + 1) for child in value})
        return f"{tag_name(value)}[{','.join(children) or '-'}]"
    return tag_name(value)


def path_text(parts):
    result = ""
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif result:
            result += f".{part}"
        else:
            result = str(part)
    return result


def bounded(value, limit=2000):
    unpacked = plain(value)
    encoded = json.dumps(unpacked, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded) <= limit:
        return unpacked
    return {
        "_truncated": True,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "json_chars": len(encoded),
        "preview": encoded[:limit],
    }


def entity_lists(chunk):
    for key in ("Entities", "entities"):
        value = chunk.get(key)
        if isinstance(value, (list, tuple)):
            return value
    level = chunk.get("Level")
    if isinstance(level, dict):
        for key in ("Entities", "entities"):
            value = level.get(key)
            if isinstance(value, (list, tuple)):
                return value
    return ()


def main():
    parser = argparse.ArgumentParser(
        description="Inventory modern ItemStack components stored anywhere inside entity region NBT."
    )
    parser.add_argument("world", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-examples", type=int, default=20)
    args = parser.parse_args()

    component_counts = collections.Counter()
    component_shapes: dict[str, collections.Counter] = {}
    component_parents: dict[str, collections.Counter] = {}
    component_entities: dict[str, collections.Counter] = {}
    examples: dict[str, list] = {}
    item_counts = collections.Counter()
    parse_errors = []
    region_count = 0
    empty_region_count = 0
    chunk_count = 0
    root_entities = 0
    all_entities = 0
    item_stacks = 0
    component_stacks = 0

    def visit(value, entity_id, entity_ref, parts, entity_node=False):
        nonlocal all_entities, item_stacks, component_stacks
        if isinstance(value, dict):
            if parts and parts[-1] == "Passengers":
                # The passenger list itself is counted when its members are visited.
                pass
            identifier = plain(value.get("id"))
            components = value.get("components")
            has_count = "count" in value or "Count" in value
            if not entity_node and isinstance(identifier, str) and ":" in identifier and has_count:
                item_stacks += 1
                item_counts[identifier] += 1
            if not entity_node and has_count and isinstance(identifier, str) and ":" in identifier and isinstance(components, dict):
                component_stacks += 1
                for component_id, component_value in components.items():
                    component_id = str(component_id)
                    component_counts[component_id] += 1
                    component_parents.setdefault(component_id, collections.Counter())[identifier] += 1
                    component_entities.setdefault(component_id, collections.Counter())[entity_id] += 1
                    shape = type_signature(component_value)
                    component_shapes.setdefault(component_id, collections.Counter())[shape] += 1
                    target_examples = examples.setdefault(component_id, [])
                    if len(target_examples) < args.max_examples:
                        target_examples.append({
                            **entity_ref,
                            "entity_id": entity_id,
                            "path": path_text(parts + ["components", component_id]),
                            "item_id": identifier,
                            "type_signature": shape,
                            "value": bounded(component_value),
                        })
            for key, child in value.items():
                visit(child, entity_id, entity_ref, parts + [str(key)])
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                child_entity_id = entity_id
                if parts and parts[-1] == "Passengers" and isinstance(child, dict):
                    all_entities += 1
                    child_entity_id = str(plain(child.get("id")) or "")
                visit(child, child_entity_id, entity_ref, parts + [index], parts and parts[-1] == "Passengers")

    entity_dirs = sorted(path for path in args.world.rglob("entities") if path.is_dir())
    for entity_dir in entity_dirs:
        for region in sorted(entity_dir.glob("*.mca")):
            region_count += 1
            if region.stat().st_size == 0:
                empty_region_count += 1
                continue
            try:
                for slot, chunk in read_region(region):
                    chunk_count += 1
                    for index, entity in enumerate(entity_lists(chunk)):
                        if not isinstance(entity, dict):
                            continue
                        root_entities += 1
                        all_entities += 1
                        entity_id = str(plain(entity.get("id")) or "")
                        reference = {
                            "region": str(region.relative_to(args.world)).replace("\\", "/"),
                            "slot": slot,
                            "root_index": index,
                        }
                        visit(entity, entity_id, reference, ["entity"], True)
            except Exception as exc:
                parse_errors.append({
                    "region": str(region.relative_to(args.world)).replace("\\", "/"),
                    "error": f"{type(exc).__name__}: {exc}",
                })

    components = {}
    for component_id in sorted(component_counts):
        components[component_id] = {
            "instances": component_counts[component_id],
            "parent_items": dict(component_parents[component_id].most_common()),
            "root_entity_ids": dict(component_entities[component_id].most_common()),
            "type_signatures": dict(component_shapes[component_id].most_common()),
            "examples": examples[component_id],
        }

    report = {
        "source": str(args.world.resolve()),
        "entity_directories": [str(path.relative_to(args.world)).replace("\\", "/") for path in entity_dirs],
        "regions": region_count,
        "empty_regions": empty_region_count,
        "chunks": chunk_count,
        "root_entities": root_entities,
        "entities_including_passengers": all_entities,
        "item_stack_instances": item_stacks,
        "item_stacks_with_components": component_stacks,
        "component_type_count": len(components),
        "parse_errors": parse_errors,
        "item_counts": dict(item_counts.most_common()),
        "components": components,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        key: report[key]
        for key in (
            "regions", "empty_regions", "chunks", "root_entities", "entities_including_passengers",
            "item_stack_instances", "item_stacks_with_components", "component_type_count", "parse_errors",
        )
    }, ensure_ascii=False, indent=2))
    print(json.dumps({key: value["instances"] for key, value in components.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
