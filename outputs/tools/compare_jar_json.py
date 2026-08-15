from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any


def load_json_entries(path: Path, prefixes: tuple[str, ...]) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            if not name.endswith(".json") or not name.startswith(prefixes):
                continue
            try:
                entries[name] = json.loads(archive.read(info).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                entries[name] = {"__parse_error__": str(error)}
    return entries


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare JSON resources in two JARs using parsed JSON values."
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="Entry prefix to include; repeat as needed (default: assets/ and data/).",
    )
    args = parser.parse_args()

    prefixes = tuple(args.prefix or ["assets/", "data/"])
    reference = load_json_entries(args.reference, prefixes)
    candidate = load_json_entries(args.candidate, prefixes)

    reference_names = set(reference)
    candidate_names = set(candidate)
    reference_only = sorted(reference_names - candidate_names)
    candidate_only = sorted(candidate_names - reference_names)
    changed = sorted(
        name
        for name in reference_names & candidate_names
        if reference[name] != candidate[name]
    )

    print(f"reference={args.reference}")
    print(f"reference_sha256={sha256(args.reference)}")
    print(f"candidate={args.candidate}")
    print(f"candidate_sha256={sha256(args.candidate)}")
    print(
        "counts "
        f"reference={len(reference)} candidate={len(candidate)} "
        f"reference_only={len(reference_only)} "
        f"candidate_only={len(candidate_only)} changed={len(changed)}"
    )

    for label, names in (
        ("REFERENCE_ONLY", reference_only),
        ("CANDIDATE_ONLY", candidate_only),
        ("CHANGED", changed),
    ):
        print(f"[{label}]")
        for name in names:
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
