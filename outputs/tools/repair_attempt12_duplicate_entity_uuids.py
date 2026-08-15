#!/usr/bin/env python3
"""Fail-closed repair for the one known duplicated Happy Ghast UUID.

The converted source contains the same Happy Ghast UUID in two adjacent entity
chunks.  Minecraft 1.21.1 keeps the entity from chunk slot 751 and warns when
the slot-750 copy is loaded.  This tool applies only that evidence-bound repair
to a disposable Attempt12 world; it never edits the authoritative staging
world.  Any shape/hash drift aborts before writing.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import shutil
import struct
import time
import zlib
from pathlib import Path
from typing import Any

import nbtlib


REGION_REL = Path("entities") / "r.-1.-1.mca"
TARGET_UUID = "39a2182d62cb4651a9fe94948145c520"
TARGET_ID = "minecraft:happy_ghast"
STALE_SLOT = 750
RETAINED_SLOT = 751
EXPECTED_SOURCE_SHA256 = "BBCC0E4D76E802C553A414B9CE4093389416D0C27A4864155EAEA8A6BA17F756"


class RepairError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def plain(value: Any) -> Any:
    if hasattr(value, "unpack"):
        try:
            return plain(value.unpack())
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return plain(value.tolist())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def uuid_text(entity: Any) -> str | None:
    value = entity.get("UUID")
    if value is None:
        return None
    raw = plain(value)
    if isinstance(raw, list) and len(raw) == 4:
        # The audit pipeline already canonicalizes UUID int arrays.  Compare
        # against its stable text representation without changing the NBT.
        import uuid

        bits = b"".join(int(x).to_bytes(4, "big", signed=True) for x in raw)
        return str(uuid.UUID(bytes=bits)).replace("-", "")
    return str(raw).replace("-", "").lower()


def decode_chunk(data: bytes, slot: int) -> tuple[int, int, int, nbtlib.File]:
    entry = data[slot * 4 : slot * 4 + 4]
    offset = int.from_bytes(entry[:3], "big")
    sectors = entry[3]
    if offset < 2 or sectors < 1:
        raise RepairError(f"slot {slot} is not occupied")
    start = offset * 4096
    length = int.from_bytes(data[start : start + 4], "big")
    compression = data[start + 4]
    payload = data[start + 5 : start + 4 + length]
    if compression & 0x7F == 1:
        raw = __import__("gzip").decompress(payload)
    elif compression & 0x7F == 2:
        raw = zlib.decompress(payload)
    elif compression & 0x7F == 3:
        raw = payload
    else:
        raise RepairError(f"slot {slot} unsupported compression {compression}")
    return offset, sectors, compression & 0x7F, nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def encode_chunk(chunk: nbtlib.File, compression: int = 2) -> bytes:
    raw = io.BytesIO()
    chunk.write(raw, byteorder="big")
    payload = raw.getvalue()
    if compression == 1:
        import gzip

        compressed = gzip.compress(payload, mtime=0)
    elif compression == 2:
        compressed = zlib.compress(payload, 6)
    elif compression == 3:
        compressed = payload
    else:
        raise RepairError(f"unsupported output compression {compression}")
    return struct.pack(">I", len(compressed) + 1) + bytes([compression]) + compressed


def entities_list(chunk: nbtlib.File) -> Any:
    if "Entities" in chunk:
        return chunk["Entities"]
    if "entities" in chunk:
        return chunk["entities"]
    raise RepairError("chunk has no Entities list")


def target_rows(chunk: nbtlib.File) -> list[tuple[int, Any]]:
    rows = []
    values = entities_list(chunk)
    for index, entity in enumerate(values):
        if str(entity.get("id", "")) == TARGET_ID and uuid_text(entity) == TARGET_UUID:
            rows.append((index, entity))
    return rows


def comparable(entity: Any) -> Any:
    value = plain(entity)
    for key in ("Pos", "Motion", "Rotation"):
        value.pop(key, None)
    return value


def rewrite_slot(data: bytearray, slot: int, chunk: nbtlib.File, old_offset: int, old_sectors: int, compression: int) -> None:
    record = encode_chunk(chunk, compression)
    needed = (len(record) + 4095) // 4096
    if needed > old_sectors:
        raise RepairError(f"slot {slot} grew from {old_sectors} to {needed} sectors; refusing relocation")
    start = old_offset * 4096
    data[start : start + len(record)] = record
    data[start + len(record) : start + old_sectors * 4096] = b"\x00" * (old_sectors * 4096 - len(record))
    timestamp_offset = 4096 + slot * 4
    data[timestamp_offset : timestamp_offset + 4] = int(time.time()).to_bytes(4, "big")


def scan_duplicate_uuids(world: Path) -> dict[str, Any]:
    seen: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    files = 0
    parse_errors: list[str] = []
    for path in sorted(world.rglob("entities/r.*.*.mca")):
        files += 1
        try:
            data = path.read_bytes()
            for slot in range(1024):
                entry = data[slot * 4 : slot * 4 + 4]
                offset = int.from_bytes(entry[:3], "big")
                if offset == 0:
                    continue
                try:
                    _, _, _, chunk = decode_chunk(data, slot)
                    values = entities_list(chunk)
                    for index, entity in enumerate(values):
                        uid = uuid_text(entity)
                        if uid:
                            seen[uid].append({"path": str(path), "slot": slot, "index": index, "id": str(entity.get("id", ""))})
                except Exception as exc:  # pragma: no cover - guarded runtime data
                    parse_errors.append(f"{path}:{slot}:{type(exc).__name__}:{exc}")
        except Exception as exc:  # pragma: no cover
            parse_errors.append(f"{path}:{type(exc).__name__}:{exc}")
    duplicates = {uid: rows for uid, rows in seen.items() if len(rows) > 1}
    return {"region_files": files, "uuid_count": len(seen), "duplicate_count": len(duplicates), "duplicates": duplicates, "parse_errors": parse_errors}


def repair(world: Path, backup: Path, report_path: Path) -> dict[str, Any]:
    region = world / REGION_REL
    if not region.is_file():
        raise RepairError(f"missing target region: {region}")
    original = region.read_bytes()
    if sha256(original) != EXPECTED_SOURCE_SHA256:
        raise RepairError(f"source region hash drift: {sha256(original)} != {EXPECTED_SOURCE_SHA256}")
    old750, sec750, comp750, chunk750 = decode_chunk(original, STALE_SLOT)
    old751, sec751, comp751, chunk751 = decode_chunk(original, RETAINED_SLOT)
    rows750 = target_rows(chunk750)
    rows751 = target_rows(chunk751)
    if len(rows750) != 1 or len(rows751) != 1:
        raise RepairError(f"expected one target in slots 750/751, got {len(rows750)}/{len(rows751)}")
    if comparable(rows750[0][1]) != comparable(rows751[0][1]):
        raise RepairError("duplicate entities differ beyond movement fields; refusing deletion")
    backup.mkdir(parents=True, exist_ok=False)
    backup_region = backup / REGION_REL
    backup_region.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(region, backup_region)
    values = entities_list(chunk750)
    removed = plain(values[rows750[0][0]])
    del values[rows750[0][0]]
    updated = bytearray(original)
    rewrite_slot(updated, STALE_SLOT, chunk750, old750, sec750, comp750)
    region_tmp = region.with_suffix(region.suffix + ".happyghast.tmp")
    region_tmp.write_bytes(updated)
    region_tmp.replace(region)
    after = region.read_bytes()
    if sha256(after) == sha256(original):
        raise RepairError("region bytes did not change")
    post = scan_duplicate_uuids(world)
    if post["parse_errors"] or post["duplicate_count"]:
        raise RepairError(f"post-repair UUID scan failed: {post}")
    report = {
        "schema": "attempt12-duplicate-entity-uuid-repair/v1",
        "status": "PASS_APPLIED",
        "world": str(world),
        "region": str(region),
        "input_sha256": sha256(original),
        "output_sha256": sha256(after),
        "backup": str(backup_region),
        "policy": "remove only the exact slot-750 stale copy; preserve slot-751 copy that Minecraft retained in Attempt11",
        "removed": {"uuid": TARGET_UUID, "id": TARGET_ID, "slot": STALE_SLOT, "entity": removed},
        "retained": {"uuid": TARGET_UUID, "id": TARGET_ID, "slot": RETAINED_SLOT, "entity": plain(rows751[0][1])},
        "post_scan": post,
        "world_files_modified": 1,
        "unknown_uuid_policy": "fail_closed",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = repair(args.world.resolve(), args.backup.resolve(), args.report.resolve())
    print(json.dumps({"status": result["status"], "output_sha256": result["output_sha256"], "duplicate_count": result["post_scan"]["duplicate_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
