from __future__ import annotations

import argparse
import collections
import gzip
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
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def decompress(payload: bytes, kind: int) -> bytes:
    kind &= 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported compression {kind}")


def read_region(path: Path):
    with path.open("rb") as handle:
        locations = handle.read(4096)
        for slot in range(1024):
            entry = locations[slot * 4:(slot + 1) * 4]
            offset = int.from_bytes(entry[:3], "big")
            if not offset:
                continue
            handle.seek(offset * 4096)
            length_raw = handle.read(4)
            if len(length_raw) != 4:
                continue
            length = int.from_bytes(length_raw, "big")
            kind_raw = handle.read(1)
            if not kind_raw:
                continue
            raw = decompress(handle.read(length - 1), kind_raw[0])
            yield slot, nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def entries(chunk):
    for key in ("block_entities", "BlockEntities", "blockEntities"):
        if key in chunk:
            return chunk[key]
        level = chunk.get("Level")
        if isinstance(level, dict) and key in level:
            return level[key]
    return []


def scan(path: Path, ids: set[str] | None = None):
    result = {}
    counts = collections.Counter()
    if not path.exists():
        return result, counts
    for slot, chunk in read_region(path):
        for index, raw in enumerate(entries(chunk)):
            value = plain(raw)
            identifier = str(value.get("id", "<missing>"))
            if ids and identifier not in ids:
                continue
            pos = tuple(value.get(axis) for axis in ("x", "y", "z"))
            key = f"{pos}|{identifier}"
            result[key] = {"id": identifier, "pos": list(pos), "region": path.name, "slot": slot, "index": index, "value": value}
            counts[identifier] += 1
    return result, counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("target_root", type=Path)
    parser.add_argument("--region", action="append", required=True, help="relative region path, e.g. DIM-1/region/r.-1.0.mca")
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ids = set(args.ids)
    missing = []
    extra = []
    changed = []
    source_counts = collections.Counter()
    target_counts = collections.Counter()
    for relative in args.region:
        source, sc = scan(args.source_root / relative, ids)
        target, tc = scan(args.target_root / relative, ids)
        source_counts.update(sc)
        target_counts.update(tc)
        for key in sorted(set(source) - set(target)):
            missing.append(source[key])
        for key in sorted(set(target) - set(source)):
            extra.append(target[key])
        for key in sorted(set(source) & set(target)):
            if json.dumps(source[key]["value"], sort_keys=True, ensure_ascii=False) != json.dumps(target[key]["value"], sort_keys=True, ensure_ascii=False):
                changed.append({"source": source[key], "target": target[key]})
    report = {
        "regions": args.region,
        "ids": sorted(ids),
        "source_counts": dict(source_counts),
        "target_counts": dict(target_counts),
        "missing": missing,
        "extra": extra,
        "changed": changed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_counts": report["source_counts"], "target_counts": report["target_counts"], "missing": len(missing), "extra": len(extra), "changed": len(changed)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
