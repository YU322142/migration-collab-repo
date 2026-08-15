#!/usr/bin/env python3
"""Build and verify the Tracks block-tag compatibility patch.

Tracks 1.0.1 registers only tracks:track_mount as a block.  The other two
identifiers in its block tags are item-only compatibility remnants whose
recipes are disabled.  Keeping them in block tags makes NeoForge emit hard
TagLoader errors.  This builder removes only those two invalid block-tag
values and preserves every other JAR entry.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile


SOURCE = Path(
    r"D:\Trans\migration-audit-work\attempt6-data-resource-fixes-20260814\jars\tracks-neoforge-1.21.1-1.0.1.jar"
)
SOURCE_BYTES = 165_882
SOURCE_SHA256 = "B5022C73AE4A36E8798D1E57D8128EB42DA2964C6E38C722D2AD7CCD2FF443E5"
OUTPUT_ROOT = Path(r"D:\Trans\migration-audit-work\tracks-tag-fix-artifacts-20260814")
OUTPUT_NAME = "tracks-neoforge-1.21.1-1.0.1-block-tag-fix.1.jar"
TAG_ENTRIES = (
    "data/create/tags/block/safe_nbt.json",
    "data/minecraft/tags/block/mineable/pickaxe.json",
)
EXPECTED_VALUE = "tracks:track_mount"
REMOVED_VALUES = {"tracks:suspension_track", "tracks:track_drive_wheel"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def build(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    if temp.exists():
        temp.unlink()
    with zipfile.ZipFile(SOURCE, "r") as source, zipfile.ZipFile(temp, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename in TAG_ENTRIES:
                value = json.loads(payload.decode("utf-8"))
                if value != {
                    "values": [
                        "tracks:track_mount",
                        "tracks:suspension_track",
                        "tracks:track_drive_wheel",
                    ]
                }:
                    raise RuntimeError(f"unexpected source tag payload: {info.filename}: {value!r}")
                payload = (json.dumps({"values": [EXPECTED_VALUE]}, indent=2) + "\n").encode("utf-8")
            clone = zipfile.ZipInfo(info.filename, info.date_time)
            clone.compress_type = info.compress_type
            clone.comment = info.comment
            clone.extra = info.extra
            clone.create_system = info.create_system
            clone.create_version = info.create_version
            clone.extract_version = info.extract_version
            clone.flag_bits = info.flag_bits
            clone.internal_attr = info.internal_attr
            clone.external_attr = info.external_attr
            clone.volume = info.volume
            target.writestr(clone, payload)
    temp.replace(output)


def verify(path: Path) -> dict[str, object]:
    if path.stat().st_size <= 0:
        raise RuntimeError("empty output")
    with zipfile.ZipFile(SOURCE, "r") as source, zipfile.ZipFile(path, "r") as patched:
        if source.testzip() is not None or patched.testzip() is not None:
            raise RuntimeError("ZIP CRC validation failed")
        source_names = source.namelist()
        patched_names = patched.namelist()
        if source_names != patched_names or len(patched_names) != len(set(patched_names)):
            raise RuntimeError("entry order/set/uniqueness changed")
        changed: list[str] = []
        for name in source_names:
            before = source.read(name)
            after = patched.read(name)
            if before != after:
                changed.append(name)
        if changed != list(TAG_ENTRIES):
            raise RuntimeError(f"unexpected changed entries: {changed}")
        for name in TAG_ENTRIES:
            value = json.loads(patched.read(name).decode("utf-8"))
            if value != {"values": [EXPECTED_VALUE]}:
                raise RuntimeError(f"patched tag mismatch: {name}: {value!r}")
            text = patched.read(name).decode("utf-8")
            if any(item in text for item in REMOVED_VALUES):
                raise RuntimeError(f"removed block ID remains in {name}")
        block_class = patched.read("dev/qwxon/tracks/index/TracksBlocks.class")
        item_class = patched.read("dev/qwxon/tracks/index/TracksItems.class")
        if b"track_mount" not in block_class:
            raise RuntimeError("track_mount block registration evidence missing")
        if b"suspension_track" in block_class or b"track_drive_wheel" in block_class:
            raise RuntimeError("disabled blocks unexpectedly registered")
        if b"suspension_track" not in item_class or b"track_drive_wheel" not in item_class:
            raise RuntimeError("item-only compatibility entries unexpectedly missing")
        return {
            "entries": len(patched_names),
            "changed_entries": changed,
            "zip_crc": "PASS",
            "block_registry": ["tracks:track_mount"],
            "item_only_compatibility": sorted(REMOVED_VALUES),
        }


def main() -> int:
    if not SOURCE.is_file() or SOURCE.stat().st_size != SOURCE_BYTES or sha256(SOURCE) != SOURCE_SHA256:
        raise RuntimeError("source Tracks candidate drifted")
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True)
    build1 = OUTPUT_ROOT / ("build1-" + OUTPUT_NAME)
    build2 = OUTPUT_ROOT / ("build2-" + OUTPUT_NAME)
    build(build1)
    first = verify(build1)
    build(build2)
    second = verify(build2)
    first_sha = sha256(build1)
    second_sha = sha256(build2)
    if first_sha != second_sha or build1.read_bytes() != build2.read_bytes():
        raise RuntimeError("two independent builds are not byte-identical")
    final = OUTPUT_ROOT / OUTPUT_NAME
    shutil.copy2(build2, final)
    result = {
        "schema": 1,
        "status": "PASS_REPRODUCIBLE_BUILD",
        "source": {"path": str(SOURCE), "bytes": SOURCE_BYTES, "sha256": SOURCE_SHA256},
        "artifact": {"path": str(final), "bytes": final.stat().st_size, "sha256": sha256(final)},
        "build1_sha256": first_sha,
        "build2_sha256": second_sha,
        "verification": first,
        "second_verification_identical": first == second,
        "side": "BOTH",
        "minecraft_started": False,
    }
    report = OUTPUT_ROOT / "tracks-block-tag-fix-result.json"
    report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
