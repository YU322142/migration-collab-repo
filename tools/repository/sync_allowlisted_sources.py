#!/usr/bin/env python3
"""Copy small, explicitly allowlisted source overlays into the repository."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

EXCLUDED_DIRS = {".git", ".gradle", "build", "run", "logs", "__pycache__", "tmp"}
EXCLUDED_SUFFIXES = {".jar", ".zip", ".7z", ".mca", ".nbt", ".class", ".log"}
SPECS = [
    (
        "outputs/terrain-preservation-frontier-datapack-20260813",
        "pack/terrain-preservation-frontier-datapack",
    ),
    (
        "outputs/worldgen-height-544-overlay-20260815",
        "pack/worldgen-height-544-overlay",
    ),
    (
        "outputs/xiyuslogin-auto-session-ota-20260815",
        "projects/patches/xiyuslogin-auto-session-ota",
    ),
    (
        "outputs/candidate14-mcmodsync-local-template-20260812",
        "artifacts/mcmodsync-disabled/local-template",
    ),
]


def copy_tree(source: Path, target: Path) -> tuple[int, int]:
    files = 0
    total = 0
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        if any(part.lower() in EXCLUDED_DIRS for part in rel.parts[:-1]):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        files += 1
        total += path.stat().st_size
    return files, total


parser = argparse.ArgumentParser()
parser.add_argument("--workspace", type=Path, required=True)
parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
args = parser.parse_args()

rows = []
for source_rel, target_rel in SPECS:
    source = args.workspace.resolve() / source_rel
    if not source.is_dir():
        raise SystemExit(f"required source overlay missing: {source}")
    target = args.repository.resolve() / target_rel
    count, size = copy_tree(source, target)
    rows.append((target_rel, count, size))

for target_rel, count, size in rows:
    print(f"SOURCE_SYNC {target_rel} files={count} bytes={size}")
print("SOURCE_SYNC_PASS")
