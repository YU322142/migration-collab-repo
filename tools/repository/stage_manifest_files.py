#!/usr/bin/env python3
"""Stage exactly the files listed by repository-manifest.json.

Imported upstream source trees may contain nested .gitignore files. Those
ignore rules are useful in their original projects, but they must not make a
curated collaboration snapshot silently omit source or resource files. This
tool treats the generated repository manifest as the allowlist and force-adds
only those paths, using Git's NUL-delimited pathspec input for Windows-safe
handling of long and non-ASCII paths.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "repository-manifest.json"


def git(*args: str, input_bytes: bytes | None = None) -> None:
    subprocess.run(
        ["git", "-C", str(ROOT), *args],
        input=input_bytes,
        check=True,
    )


def load_paths() -> list[str]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema") != 1:
        raise SystemExit("Unsupported repository manifest schema")

    paths: list[str] = []
    seen: set[str] = set()
    for row in payload.get("files", []):
        rel = row.get("path")
        if not isinstance(rel, str) or not rel or rel in seen:
            raise SystemExit(f"Invalid or duplicate manifest path: {rel!r}")
        candidate = ROOT / Path(rel)
        if not candidate.is_file():
            raise SystemExit(f"Manifest file is missing: {rel}")
        paths.append(rel)
        seen.add(rel)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Force-stage only repository-manifest allowlisted files"
    )
    parser.add_argument(
        "--include-manifest",
        action="store_true",
        help="also stage repository-manifest.json itself",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify that tracked paths exactly match the manifest allowlist",
    )
    args = parser.parse_args()

    if not (ROOT / ".git").is_dir():
        raise SystemExit(f"Not a Git repository: {ROOT}")

    paths = load_paths()
    if args.verify_only:
        tracked_raw = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-files", "-z"]
        )
        tracked = {
            item.decode("utf-8")
            for item in tracked_raw.split(b"\0")
            if item
        }
        expected = set(paths) | {"repository-manifest.json"}
        missing = sorted(expected - tracked)
        extra = sorted(tracked - expected)
        if missing or extra:
            for rel in missing[:20]:
                print(f"MISSING_TRACKED_PATH {rel}", file=sys.stderr)
            for rel in extra[:20]:
                print(f"EXTRA_TRACKED_PATH {rel}", file=sys.stderr)
            raise SystemExit(
                "Manifest/tracked path mismatch: "
                f"missing={len(missing)} extra={len(extra)}"
            )
        print(f"MANIFEST_TRACKING_PASS files={len(expected)}")
        return 0

    nul_pathspec = b"\0".join(path.encode("utf-8") for path in paths) + b"\0"
    git(
        "add",
        "-f",
        "--pathspec-from-file=-",
        "--pathspec-file-nul",
        input_bytes=nul_pathspec,
    )
    if args.include_manifest:
        git("add", "-f", "--", "repository-manifest.json")

    print(
        "MANIFEST_STAGE_COMPLETE "
        f"allowlisted={len(paths)} include_manifest={args.include_manifest}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
