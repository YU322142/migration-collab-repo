#!/usr/bin/env python3
"""Fail-closed verification for the Immersive Paintings MineAstr overlay."""

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


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def read(path: Path) -> tuple[list[str], dict[str, bytes]]:
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)):
            raise AssertionError(f"duplicate ZIP entries: {path}")
        bad = zf.testzip()
        if bad:
            raise AssertionError(f"CRC failure: {path}!{bad}")
        return names, {n: zf.read(n) for n in names}


def verify(base: Path, compiled_a: Path, compiled_b: Path, final: Path) -> dict:
    base_names, base_data = read(base)
    a_names, a_data = read(compiled_a)
    b_names, b_data = read(compiled_b)
    final_names, final_data = read(final)

    if set(a_names) != set(b_names) or any(a_data[n] != b_data[n] for n in set(a_names) & set(b_names)):
        raise AssertionError("clean build whitelist source jars are not content-identical")
    if not WHITELIST.issubset(a_data):
        raise AssertionError("compiled jar is missing one or more whitelist entries")
    expected = set(base_data) | set(WHITELIST)
    if set(final_data) != expected:
        raise AssertionError("final entry set is not base union whitelist")

    non_whitelist = [n for n in base_data if n not in WHITELIST and final_data[n] != base_data[n]]
    if non_whitelist:
        raise AssertionError(f"non-whitelist entries changed: {non_whitelist[:5]}")
    changed = [n for n in WHITELIST if final_data[n] != base_data.get(n, b"")]
    if set(changed) != set(WHITELIST):
        raise AssertionError("every whitelist entry must be replaced or newly added")

    # The migration-specific entity class is intentionally not overlaid.
    preserved = "net/conczin/immersive_paintings/entity/ImmersivePaintingEntity.class"
    preserved_hash = None
    if preserved in base_data:
        if final_data.get(preserved) != base_data[preserved]:
            raise AssertionError("existing rotation/VRotation entity patch was altered")
        preserved_hash = digest(base_data[preserved])

    toml = final_data.get("META-INF/neoforge.mods.toml", b"").decode("utf-8", "replace")
    if "immersive_paintings" not in toml:
        raise AssertionError("mod metadata missing")
    if b"MineAstrTranslationCompat" not in final_data["net/conczin/immersive_paintings/neoforge/compat/MineAstrTranslationCompat.class"]:
        raise AssertionError("compat class payload missing")

    return {
        "status": "PASS",
        "base": {"path": str(base), "sha256": digest(base.read_bytes()), "bytes": base.stat().st_size, "entries": len(base_data)},
        "compiled_build_a": {"path": str(compiled_a), "sha256": digest(compiled_a.read_bytes()), "bytes": compiled_a.stat().st_size},
        "compiled_build_b": {"path": str(compiled_b), "sha256": digest(compiled_b.read_bytes()), "bytes": compiled_b.stat().st_size},
        "final": {"path": str(final), "sha256": digest(final.read_bytes()), "bytes": final.stat().st_size, "entries": len(final_data)},
        "whitelist": {n: digest(final_data[n]) for n in sorted(WHITELIST)},
        "non_whitelist_byte_identical": True,
        "preserved_rotation_entity_sha256": preserved_hash,
        "crc": "PASS",
        "duplicate_entries": 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-jar", type=Path, required=True)
    ap.add_argument("--compiled-a", type=Path, required=True)
    ap.add_argument("--compiled-b", type=Path, required=True)
    ap.add_argument("--final-jar", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    result = verify(args.base_jar, args.compiled_a, args.compiled_b, args.final_jar)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
