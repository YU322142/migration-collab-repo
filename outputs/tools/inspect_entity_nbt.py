from __future__ import annotations

import argparse
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
            length = int.from_bytes(handle.read(4), "big")
            kind = handle.read(1)[0]
            raw = decompress(handle.read(length - 1), kind)
            yield slot, nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--kind", choices=("entities", "region"), default="entities")
    parser.add_argument("--ids", nargs="+", default=[])
    parser.add_argument("--has", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    ids = set(args.ids)
    count = 0
    for region in sorted(args.root.rglob("*.mca")):
        if args.kind not in region.parts:
            continue
        for slot, chunk in read_region(region):
            keys = ("Entities", "entities") if args.kind == "entities" else ("block_entities", "BlockEntities", "blockEntities")
            values = []
            for key in keys:
                if key in chunk:
                    values = chunk[key]
                    break
                if "Level" in chunk and key in chunk["Level"]:
                    values = chunk["Level"][key]
                    break
            for value in values:
                item = plain(value)
                if ids and item.get("id") not in ids:
                    continue
                if any(key not in item for key in args.has):
                    continue
                print(json.dumps({"region": str(region), "slot": slot, "value": item}, ensure_ascii=False, sort_keys=True))
                count += 1
                if count >= args.limit:
                    return


if __name__ == "__main__":
    main()
