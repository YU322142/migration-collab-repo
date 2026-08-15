from __future__ import annotations

import argparse
import gzip
import io
import math
import struct
import zlib
from pathlib import Path

import nbtlib


def decompress(payload: bytes, kind: int) -> bytes:
    kind &= 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(kind)


def chunk_file(root: Path, x: int, z: int) -> Path:
    rx = math.floor(x / 512)
    rz = math.floor(z / 512)
    cx = x % 512 // 16
    cz = z % 512 // 16
    return root / f"r.{rx}.{rz}.mca", cx, cz


def load_chunk(path: Path, index: int):
    with path.open("rb") as handle:
        handle.seek(index * 4)
        loc = handle.read(4)
        offset = int.from_bytes(loc[:3], "big")
        handle.seek(offset * 4096)
        length = int.from_bytes(handle.read(4), "big")
        kind = handle.read(1)[0]
        raw = decompress(handle.read(length - 1), kind)
        return nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def unpacked(value):
    if hasattr(value, "unpack"):
        return value.unpack()
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def block_at(chunk, x: int, y: int, z: int):
    level = chunk.get("Level", chunk)
    sections = level.get("sections", level.get("Sections", []))
    section_y = math.floor(y / 16)
    local_x, local_y, local_z = x & 15, y & 15, z & 15
    for section in sections:
        sy = int(unpacked(section.get("Y", section.get("y", 0))))
        if sy != section_y:
            continue
        states = section.get("block_states", section.get("BlockStates"))
        palette = states.get("palette", states.get("Palette", [])) if states else []
        palette = [unpacked(item) for item in palette]
        if not palette:
            return None
        if len(palette) == 1:
            index = 0
        else:
            bits = max(4, (len(palette) - 1).bit_length())
            values = [int(unpacked(v)) & ((1 << 64) - 1) for v in states.get("data", states.get("Data", []))]
            linear = (local_y * 16 + local_z) * 16 + local_x
            bit = linear * bits
            word = bit // 64
            shift = bit % 64
            index = (values[word] >> shift) & ((1 << bits) - 1)
            if shift + bits > 64:
                index |= (values[word + 1] << (64 - shift)) & ((1 << bits) - 1)
        return palette[index] if index < len(palette) else {"error": "palette index", "index": index}
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("coords", nargs="+", help="x,y,z")
    args = parser.parse_args()
    for raw in args.coords:
        x, y, z = (int(part) for part in raw.split(","))
        region, cx, cz = chunk_file(args.root / "region", x, z)
        slot = cz * 32 + cx
        chunk = load_chunk(region, slot)
        print(raw, block_at(chunk, x, y, z))


if __name__ == "__main__":
    main()
