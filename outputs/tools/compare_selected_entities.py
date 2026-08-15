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
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def decode(payload, kind):
    kind &= 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(kind)


def read_region(path):
    with path.open("rb") as handle:
        locations = handle.read(4096)
        for slot in range(1024):
            entry = locations[slot * 4:(slot + 1) * 4]
            offset = int.from_bytes(entry[:3], "big")
            if not offset:
                continue
            handle.seek(offset * 4096)
            length = int.from_bytes(handle.read(4), "big")
            kind = handle.read(1)[0]
            yield slot, nbtlib.File.parse(io.BytesIO(decode(handle.read(length - 1), kind)), byteorder="big")


def values(chunk):
    for key in ("Entities", "entities"):
        if key in chunk:
            return chunk[key]
        level = chunk.get("Level")
        if isinstance(level, dict) and key in level:
            return level[key]
    return []


def uid(item):
    value = plain(item.get("UUID"))
    if isinstance(value, list) and len(value) == 4:
        number = 0
        for part in value:
            number = (number << 32) | (int(part) & 0xFFFFFFFF)
        return f"{number:032x}"
    return str(value) if value is not None else None


def scan(root, relatives, ids):
    result = {}
    counts = collections.Counter()
    for relative in relatives:
        path = root / relative
        if not path.exists():
            continue
        for slot, chunk in read_region(path):
            for index, raw in enumerate(values(chunk)):
                value = plain(raw)
                if ids and value.get("id") not in ids:
                    continue
                key = uid(value) or f"{path.name}:{slot}:{index}"
                result[key] = {"id": value.get("id"), "pos": value.get("Pos"), "region": path.name, "slot": slot, "index": index, "value": value}
                counts[str(value.get("id"))] += 1
    return result, counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("target_root", type=Path)
    parser.add_argument("--region", action="append", required=True)
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ids = set(args.ids)
    source, sc = scan(args.source_root, args.region, ids)
    target, tc = scan(args.target_root, args.region, ids)
    missing = [source[k] for k in sorted(set(source) - set(target))]
    extra = [target[k] for k in sorted(set(target) - set(source))]
    changed = [{"source": source[k], "target": target[k]} for k in sorted(set(source) & set(target)) if source[k]["value"] != target[k]["value"]]
    report = {"source_counts": dict(sc), "target_counts": dict(tc), "missing": missing, "extra": extra, "changed": changed}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_counts": report["source_counts"], "target_counts": report["target_counts"], "missing": len(missing), "extra": len(extra), "changed": len(changed)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
