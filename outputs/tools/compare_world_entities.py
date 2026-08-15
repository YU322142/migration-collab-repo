from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import io
import json
import struct
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
    raise ValueError(f"unsupported region compression {compression}")


def read_region(path: Path):
    with path.open("rb") as handle:
        locations = handle.read(4096)
        for slot in range(1024):
            loc = locations[slot * 4:(slot + 1) * 4]
            offset = int.from_bytes(loc[:3], "big")
            if not offset:
                continue
            handle.seek(offset * 4096)
            length_raw = handle.read(4)
            if len(length_raw) != 4:
                raise ValueError(f"missing chunk length at {slot}")
            length = int.from_bytes(length_raw, "big")
            compression_raw = handle.read(1)
            if not compression_raw or length < 1:
                raise ValueError(f"invalid chunk header at {slot}")
            raw = decompress(handle.read(length - 1), compression_raw[0])
            yield slot, nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def uuid_text(entity: dict) -> str | None:
    value = plain(entity.get("UUID"))
    if isinstance(value, str):
        return value
    if isinstance(value, list) and len(value) == 4:
        number = 0
        for part in value:
            number = (number << 32) | (int(part) & 0xFFFFFFFF)
        return f"{number:032x}"
    if "UUIDMost" in entity and "UUIDLeast" in entity:
        return f"{(int(entity['UUIDMost']) & 0xFFFFFFFFFFFFFFFF):016x}{(int(entity['UUIDLeast']) & 0xFFFFFFFFFFFFFFFF):016x}"
    return None


def stable(value) -> str:
    raw = json.dumps(plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def roots(server: Path, kind: str):
    # NeoForge's dimension layout is also the layout already used inside the source world.
    for relative, dimension in (
        (Path("world") / kind, "minecraft:overworld"),
        (Path("world") / "DIM-1" / kind, "minecraft:the_nether"),
        (Path("world") / "DIM1" / kind, "minecraft:the_end"),
    ):
        path = server / relative
        if path.exists():
            yield path, dimension


def list_values(chunk: dict, names: tuple[str, ...]):
    for name in names:
        value = chunk.get(name)
        if value is not None:
            return value
    level = chunk.get("Level")
    if isinstance(level, dict):
        for name in names:
            value = level.get(name)
            if value is not None:
                return value
    return []


def scan_entities(server: Path):
    records = {}
    id_counts = collections.Counter()
    failures = []
    for root, dimension in roots(server, "entities"):
        for region in sorted(root.glob("*.mca")):
            try:
                for slot, chunk in read_region(region):
                    entities = list_values(chunk, ("Entities", "entities"))
                    for index, raw_entity in enumerate(entities):
                        entity = plain(raw_entity)
                        identifier = str(entity.get("id", "<missing>"))
                        uid = uuid_text(entity)
                        pos = entity.get("Pos", [])
                        if uid is None:
                            key = f"{dimension}|{region.name}|{slot}|{index}|{identifier}|{pos}"
                        else:
                            key = f"uuid:{uid}"
                        records[key] = {
                            "key": key,
                            "id": identifier,
                            "uuid": uid,
                            "pos": pos,
                            "dimension": dimension,
                            "region": region.name,
                            "slot": slot,
                            "hash": stable(entity),
                        }
                        id_counts[identifier] += 1
            except Exception as exc:
                failures.append({"path": str(region), "error": f"{type(exc).__name__}: {exc}"})
    return {"records": records, "id_counts": id_counts, "failures": failures}


def scan_block_entities(server: Path):
    records = {}
    id_counts = collections.Counter()
    failures = []
    for root, dimension in roots(server, "region"):
        for region in sorted(root.glob("*.mca")):
            try:
                for slot, chunk in read_region(region):
                    entities = list_values(chunk, ("block_entities", "BlockEntities", "blockEntities"))
                    for index, raw_entity in enumerate(entities):
                        entity = plain(raw_entity)
                        identifier = str(entity.get("id", "<missing>"))
                        pos = [entity.get(axis) for axis in ("x", "y", "z")]
                        key = f"{dimension}|{tuple(pos)}|{identifier}"
                        if key in records:
                            key = f"{key}|{index}"
                        records[key] = {
                            "key": key,
                            "id": identifier,
                            "pos": pos,
                            "dimension": dimension,
                            "region": region.name,
                            "slot": slot,
                            "hash": stable(entity),
                        }
                        id_counts[identifier] += 1
            except Exception as exc:
                failures.append({"path": str(region), "error": f"{type(exc).__name__}: {exc}"})
    return {"records": records, "id_counts": id_counts, "failures": failures}


def compare(source, target):
    source_records = source["records"]
    target_records = target["records"]
    missing = [source_records[key] for key in sorted(set(source_records) - set(target_records))]
    extra = [target_records[key] for key in sorted(set(target_records) - set(source_records))]
    common = set(source_records) & set(target_records)
    changed = [
        {"source": source_records[key], "target": target_records[key]}
        for key in sorted(common)
        if source_records[key]["hash"] != target_records[key]["hash"]
    ]
    return {
        "source_count": len(source_records),
        "target_count": len(target_records),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "changed_count": len(changed),
        "missing": missing,
        "extra": extra,
        "changed": changed,
        "source_id_counts": dict(source["id_counts"].most_common()),
        "target_id_counts": dict(target["id_counts"].most_common()),
        "source_failures": source["failures"],
        "target_failures": target["failures"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--block-entities", action="store_true")
    args = parser.parse_args()
    scanner = scan_block_entities if args.block_entities else scan_entities
    result = {
        "source": str(args.source.resolve()),
        "target": str(args.target.resolve()),
        "kind": "block_entities" if args.block_entities else "entities",
        "comparison": compare(scanner(args.source.resolve()), scanner(args.target.resolve())),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = result["comparison"]
    print(json.dumps({key: summary[key] for key in ("source_count", "target_count", "missing_count", "extra_count", "changed_count", "source_failures", "target_failures")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
