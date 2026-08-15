#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "repository-manifest.json"
SKIP_DIRS = {".git", "__pycache__", ".gradle", "build", "run", "logs", "tmp"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".class", ".log"}

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()

rows = []
for path in sorted(ROOT.rglob("*"), key=lambda item: item.as_posix().lower()):
    if not path.is_file():
        continue
    rel = path.relative_to(ROOT)
    # Check the filename too so copied worktree pointer files named `.git`
    # can never become part of the collaboration snapshot.
    if any(part.lower() in SKIP_DIRS for part in rel.parts):
        continue
    if path.suffix.lower() in SKIP_SUFFIXES:
        continue
    if rel.as_posix() == "repository-manifest.json":
        continue
    rows.append({"path": rel.as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})

parser = argparse.ArgumentParser(description="Refresh the repository file manifest")
parser.add_argument(
    "--generated-at",
    help="explicit ISO-8601 timestamp for reproducible snapshot creation",
)
args = parser.parse_args()

previous = None
if OUT.is_file():
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        previous = None

if args.generated_at:
    generated_at = args.generated_at
elif previous and previous.get("files") == rows:
    # A verification-only refresh of a clean tree must not make the repository
    # dirty just because the wall clock advanced.
    generated_at = previous.get("generated_at") or datetime.now(timezone.utc).isoformat()
else:
    generated_at = datetime.now(timezone.utc).isoformat()

payload = {
    "schema": 1,
    "generated_at": generated_at,
    "self_excluded": "repository-manifest.json",
    "files": rows,
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"MANIFEST_REFRESHED files={len(rows)} path={OUT}")
