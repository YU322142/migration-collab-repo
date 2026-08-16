#!/usr/bin/env python3
"""Build a deterministic, whitelist-only overlay for Immersive Paintings.

The base JAR is authoritative: every entry except the compiled compatibility
classes is copied byte-for-byte.  This preserves migration-specific resources
and existing rotation/VRotation fixes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


WHITELIST = frozenset(
    {
        "net/conczin/immersive_paintings/ClientPaintingManager.class",
        "net/conczin/immersive_paintings/neoforge/ClientNeoForge.class",
        "net/conczin/immersive_paintings/neoforge/compat/MineAstrImageCodec.class",
        "net/conczin/immersive_paintings/neoforge/compat/MineAstrTranslationCompat.class",
        "net/conczin/immersive_paintings/neoforge/compat/MineAstrTranslationCompat$TranslationKey.class",
        "net/conczin/immersive_paintings/neoforge/compat/MineAstrTranslationCompat$Translation.class",
        "net/conczin/immersive_paintings/neoforge/compat/MineAstrTranslationCompat$TranslationCache.class",
    }
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def read_unique(path: Path) -> tuple[list[zipfile.ZipInfo], dict[str, bytes]]:
    with zipfile.ZipFile(path, "r") as zf:
        infos = zf.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate ZIP entry in {path}")
        return infos, {i.filename: zf.read(i) for i in infos}


def build(base: Path, compiled: Path, output: Path) -> dict:
    base_infos, base_data = read_unique(base)
    _, compiled_data = read_unique(compiled)
    missing = sorted(WHITELIST - compiled_data.keys())
    if missing:
        raise ValueError(f"compiled JAR missing whitelist entries: {missing}")
    if "META-INF/MANIFEST.MF" in compiled_data:
        # The overlay must not import a second manifest/signature set.
        pass

    merged = dict(base_data)
    for name in WHITELIST:
        merged[name] = compiled_data[name]

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for info in base_infos:
            zi = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            zi.create_system = info.create_system
            zi.flag_bits = info.flag_bits & 0x800
            out.writestr(zi, merged[info.filename])
        # New compatibility classes are appended deterministically; all base
        # entries retain their original order and byte content unless whitelisted.
        for name in sorted(WHITELIST - base_data.keys()):
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 0
            zi.external_attr = 0
            zi.flag_bits = 0
            out.writestr(zi, merged[name])
    tmp.replace(output)

    _, final_data = read_unique(output)
    expected_entries = set(base_data) | set(WHITELIST)
    if set(final_data) != expected_entries:
        raise ValueError("final entry set differs from base plus whitelist")
    for name in base_data:
        if name not in WHITELIST and final_data[name] != base_data[name]:
            raise ValueError(f"non-whitelist entry changed: {name}")

    result = {
        "base": {"path": str(base), "sha256": sha256(base.read_bytes()), "bytes": base.stat().st_size},
        "compiled": {"path": str(compiled), "sha256": sha256(compiled.read_bytes()), "bytes": compiled.stat().st_size},
        "output": {"path": str(output), "sha256": sha256(output.read_bytes()), "bytes": output.stat().st_size},
        "entry_count": len(final_data),
        "whitelist": {name: {"base": sha256(base_data.get(name, b"")), "overlay": sha256(final_data[name])} for name in sorted(WHITELIST)},
        "non_whitelist_byte_identical": True,
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-jar", type=Path, required=True)
    ap.add_argument("--compiled-jar", type=Path, required=True)
    ap.add_argument("--output-jar", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    result = build(args.base_jar, args.compiled_jar, args.output_jar)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
