#!/usr/bin/env python3
"""Fail-closed audit for the Kaleidoscope Cookery chopping-board crash fix."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path


OLD_SHA256 = "A061FB1E953AD815144304F7567B30876DBBC07B8565069871771F0AAEB63D3F"
EXPECTED_CHANGED_ENTRIES = {
    "com/github/ysbbbbbb/kaleidoscopecookery/blockentity/kitchen/ChoppingBoardBlockEntity.class",
    "com/github/ysbbbbbb/kaleidoscopecookery/client/render/block/ChoppingBoardBlockEntityRender.class",
}
RENDERER_ENTRY = (
    "com/github/ysbbbbbb/kaleidoscopecookery/client/render/block/"
    "ChoppingBoardBlockEntityRender.class"
)
BLOCK_ENTITY_ENTRY = (
    "com/github/ysbbbbbb/kaleidoscopecookery/blockentity/kitchen/"
    "ChoppingBoardBlockEntity.class"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_archive(path: Path) -> tuple[dict[str, bytes], dict]:
    with zipfile.ZipFile(path) as archive:
        names = [entry.filename for entry in archive.infolist()]
        duplicates = sorted(name for name, count in Counter(names).items() if count != 1)
        bad_crc = archive.testzip()
        payload = {name: archive.read(name) for name in names}
    return payload, {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "entries": len(names),
        "duplicates": duplicates,
        "bad_crc_entry": bad_crc,
    }


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True, type=Path)
    parser.add_argument("--build1", required=True, type=Path)
    parser.add_argument("--build2", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    failures: list[str] = []
    for path in (args.old, args.build1, args.build2):
        require(path.is_file(), f"missing archive: {path}", failures)
    if failures:
        raise SystemExit("; ".join(failures))

    old_payload, old_meta = read_archive(args.old)
    b1_payload, b1_meta = read_archive(args.build1)
    b2_payload, b2_meta = read_archive(args.build2)

    require(old_meta["sha256"] == OLD_SHA256, "old JAR hash drift", failures)
    for label, meta in (("old", old_meta), ("build1", b1_meta), ("build2", b2_meta)):
        require(not meta["duplicates"], f"{label} has duplicate ZIP entries", failures)
        require(meta["bad_crc_entry"] is None, f"{label} failed ZIP CRC", failures)

    old_names = set(old_payload)
    new_names = set(b1_payload)
    require(old_names == new_names, "archive entry set changed", failures)
    require(set(b2_payload) == new_names, "two builds have different entry sets", failures)

    changed = sorted(name for name in old_names if old_payload[name] != b1_payload[name])
    require(set(changed) == EXPECTED_CHANGED_ENTRIES, "unexpected old/new entry diff", failures)
    require(b1_payload == b2_payload, "two builds differ in entry payload bytes", failures)
    require(b1_meta["sha256"] == b2_meta["sha256"], "two builds are not byte-identical", failures)

    manifest = b1_payload["META-INF/MANIFEST.MF"]
    mods_toml = b1_payload["META-INF/neoforge.mods.toml"]
    require(b"migration.3-neoforge+mc1.21.1" in manifest, "compatible version absent from manifest", failures)
    require(b"migration.3-neoforge+mc1.21.1" in mods_toml, "compatible version absent from mods.toml", failures)

    renderer = b1_payload[RENDERER_ENTRY]
    block_entity = b1_payload[BLOCK_ENTITY_ENTRY]
    for token in (b"minecraft", b"air", b"getMissingModel", b"isProvablyEmptyBoard", b"Math"):
        require(token in renderer, f"renderer bytecode missing token {token!r}", failures)
    for token in (b"minecraft", b"air", b"isEmpty", b"isProvablyEmptyBoard"):
        require(token in block_entity, f"block entity bytecode missing token {token!r}", failures)

    report = {
        "schema": 1,
        "status": "PASS" if not failures else "FAIL",
        "purpose": "kaleidoscope_cookery_chopping_board_empty_model_crash_fix",
        "old": old_meta,
        "build1": b1_meta,
        "build2": b2_meta,
        "entry_sets_equal": old_names == new_names == set(b2_payload),
        "changed_entries": changed,
        "expected_changed_entries": sorted(EXPECTED_CHANGED_ENTRIES),
        "build_payloads_equal": b1_payload == b2_payload,
        "build_archives_byte_identical": b1_meta["sha256"] == b2_meta["sha256"],
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(args.report), "sha256": sha256(args.report)}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
