#!/usr/bin/env python3
"""Copy the current allowlisted handoff documents into the repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ALLOWLIST = [
    "PROTECTED-TERRAIN-OTA-OPERATOR-RUNBOOK-20260815.md",
    "MASTER-TERRAIN-BIOME-OTA-RUNBOOK-20260815.md",
    "TERRAIN-OTA-COLLAB-HANDOFF-20260815.md",
    "WORLDGEN-HEIGHT-544-AND-FRONTIER-APPENDIX-20260815.md",
    "terrain-biome-safe-ota-design-20260815.md",
    "protected-zone-terrain-ota-tool-20260815.md",
    "protected-zone-entity-relocation-ota-20260815.md",
    "heightmap-384-to-544-compat-audit-20260815.md",
    "mineastr-readonly-audit-20260815.md",
    "protected-terrain-ota-latest-c-lock-20260815.json",
    "terrain-biome-ota-current-state-20260815.json",
    "mechanomania-latest-c-ota-candidate-manifest-20260815.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


parser = argparse.ArgumentParser()
parser.add_argument("--workspace", type=Path, required=True)
parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
args = parser.parse_args()

source_root = args.workspace.resolve() / "outputs"
target_root = args.repository.resolve() / "reports" / "current-20260815"
target_root.mkdir(parents=True, exist_ok=True)
rows = []
for name in ALLOWLIST:
    source = source_root / name
    if not source.is_file():
        raise SystemExit(f"required allowlisted document missing: {source}")
    target = target_root / name
    shutil.copy2(source, target)
    rows.append({"name": name, "bytes": target.stat().st_size, "sha256": sha256(target)})

manifest = target_root / "ALLOWLIST-MANIFEST.json"
manifest.write_text(json.dumps({"schema": 1, "files": rows}, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"ALLOWLIST_SYNC_PASS files={len(rows)} target={target_root}")
