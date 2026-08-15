#!/usr/bin/env python3
"""Read-only helpers shared by the Candidate13 full-world NBT audits."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import struct
import zlib
from pathlib import Path
from typing import Any, Iterable

import nbtlib


NBT_FILE_SUFFIXES = {".dat", ".dat_old", ".nbt"}
# Bukkit stores a raw 128-bit world UUID in ``uid.dat``.  It is deliberately
# named like vanilla saved-data but is not an NBT container.  Treating it as a
# parse failure would make an otherwise exhaustive NBT audit report a false
# blocker.  The callers record every skipped path/hash so this exception stays
# explicit and auditable.
KNOWN_NON_NBT_BASENAMES = {"uid.dat"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def plain(value: Any) -> Any:
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    return value


def tag_type(value: Any) -> str:
    # nbtlib creates specialised list classes such as ``List[Compound]``.
    # The outer on-disk tag kind is what cross-version schema checks need.
    return type(value).__name__.removeprefix("TAG_").split("[", 1)[0]


def bounded(value: Any, limit: int = 100_000) -> Any:
    unpacked = plain(value)
    encoded = json.dumps(
        unpacked,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(encoded) <= limit:
        return unpacked
    return {
        "_truncated": True,
        "json_chars": len(encoded),
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper(),
        "preview": encoded[: min(limit, 4_000)],
    }


def path_text(parts: Iterable[str | int]) -> str:
    result = ""
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif result:
            result += f".{part}"
        else:
            result = str(part)
    return result


def decompress(payload: bytes, compression: int) -> bytes:
    kind = compression & 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported region compression type {kind}")


def iter_region(path: Path):
    """Yield ``(slot, compression, root)`` for every occupied MCA slot."""

    if path.stat().st_size == 0:
        return
    with path.open("rb") as handle:
        locations = handle.read(4096)
        if len(locations) != 4096:
            raise ValueError("region location table is truncated")
        for slot in range(1024):
            entry = locations[slot * 4 : (slot + 1) * 4]
            offset = int.from_bytes(entry[:3], "big")
            sectors = entry[3]
            if not offset:
                continue
            handle.seek(offset * 4096)
            length_bytes = handle.read(4)
            if len(length_bytes) != 4:
                raise ValueError(f"slot {slot} has a truncated chunk header")
            length = struct.unpack(">I", length_bytes)[0]
            compression_bytes = handle.read(1)
            if len(compression_bytes) != 1 or length < 1:
                raise ValueError(f"slot {slot} has an invalid chunk header")
            compression = compression_bytes[0]
            if compression & 0x80:
                raise ValueError(
                    f"slot {slot} uses an external chunk stream; "
                    "the audit intentionally refuses to guess its .mcc path"
                )
            if sectors and length + 4 > sectors * 4096:
                raise ValueError(f"slot {slot} length exceeds allocated sectors")
            payload = handle.read(length - 1)
            if len(payload) != length - 1:
                raise ValueError(f"slot {slot} payload is truncated")
            raw = decompress(payload, compression)
            yield slot, compression & 0x7F, nbtlib.File.parse(
                io.BytesIO(raw), byteorder="big"
            )


def load_nbt_file(path: Path):
    errors: list[str] = []
    for gzipped in (True, False):
        try:
            return nbtlib.load(path, gzipped=gzipped), gzipped
        except Exception as exc:  # both encodings are attempted and reported
            errors.append(f"gzipped={gzipped}: {type(exc).__name__}: {exc}")
    raise ValueError("; ".join(errors))


def collect_world_nbt_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".mca" or suffix in NBT_FILE_SUFFIXES:
            files.append(path)
    return sorted(files)


def known_non_nbt_reason(path: Path) -> str | None:
    if path.name.lower() in KNOWN_NON_NBT_BASENAMES:
        return "Bukkit raw 16-byte world UUID, not an NBT container"
    return None


def compound_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    context: dict[str, Any] = {}
    identifier = plain(value.get("id"))
    if isinstance(identifier, str):
        context["id"] = identifier
    for key in ("UUID", "UUIDMost", "UUIDLeast", "Pos", "x", "y", "z"):
        if key in value:
            context[key] = bounded(value[key], 10_000)
    return context
