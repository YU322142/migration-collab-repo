import io
import sys
from pathlib import Path

sys.path.insert(0, r"<AUDIT_ROOT>\anvildeps")
from nbt import nbt


def decode(payload: bytes, kind: int) -> bytes:
    import gzip
    import zlib

    kind &= 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported compression {kind}")


def read_slots(path: Path):
    data = path.read_bytes()
    for slot in range(1024):
        entry = data[slot * 4:(slot + 1) * 4]
        offset = int.from_bytes(entry[:3], "big")
        if not offset:
            continue
        start = offset * 4096
        length = int.from_bytes(data[start:start + 4], "big")
        yield slot, data[start + 4], data[start + 5:start + 4 + length]


def value(tag):
    if tag is None:
        return None
    if isinstance(tag, nbt.TAG_Compound):
        return {key: value(child) for key, child in tag.items()}
    if isinstance(tag, nbt.TAG_List):
        return [value(child) for child in tag]
    raw = getattr(tag, "value", tag)
    try:
        return list(raw) if not isinstance(raw, (str, bytes, int, float)) else raw
    except TypeError:
        return str(raw)


for region in ("r.-1.-1.mca", "r.-1.-2.mca"):
    path = Path(r"<TRANS_ROOT>\20260807\world\entities") / region
    for slot, compression, payload in read_slots(path):
        chunk = nbt.NBTFile(buffer=io.BytesIO(decode(payload, compression)))
        for entity in chunk.get("Entities", []):
            if str(entity.get("id")) != "minecraft:happy_ghast":
                continue
            print({
                "region": region,
                "slot": slot,
                "uuid": value(entity.get("UUID")),
                "home_pos": value(entity.get("home_pos")),
                "home_radius": value(entity.get("home_radius")),
                "pos": value(entity.get("Pos")),
            })
