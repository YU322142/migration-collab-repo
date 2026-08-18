#!/usr/bin/env python3
"""Capture a hash-locked, client-authoritative mod baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def capture(instance: Path) -> dict[str, object]:
    instance = instance.resolve()
    mods = instance / "minecraft" / "mods"
    if not mods.is_dir():
        raise SystemExit(f"mods directory is missing: {mods}")
    rows = [
        {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(mods.glob("*.jar"), key=lambda item: item.name.lower())
    ]
    return {
        "schema": 1,
        "authority": "client",
        "instance": str(instance),
        "mods_directory": str(mods),
        "mod_file_count": len(rows),
        "policy": {
            "preserve_every_listed_file": True,
            "server_may_add_missing_shared_gameplay_mods": True,
            "server_may_replace_or_downgrade_client_mods": False,
            "server_may_delete_client_mods": False,
            "newer_client_versions_waiting_for_server_update_are_authoritative": True,
            "explicit_reviewed_same_mod_replacement_required": True,
        },
        "mods": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    payload = capture(args.instance)
    if args.verify:
        if not args.output.is_file():
            raise SystemExit(f"baseline is missing: {args.output}")
        expected = json.loads(args.output.read_text(encoding="utf-8"))
        if expected.get("mods") != payload.get("mods"):
            expected_rows = {row["name"]: row for row in expected.get("mods", [])}
            actual_rows = {row["name"]: row for row in payload.get("mods", [])}
            missing = sorted(set(expected_rows) - set(actual_rows))
            added = sorted(set(actual_rows) - set(expected_rows))
            changed = sorted(
                name
                for name in set(expected_rows) & set(actual_rows)
                if expected_rows[name] != actual_rows[name]
            )
            raise SystemExit(
                "client mod baseline mismatch: "
                f"missing={missing}, added={added}, changed={changed}"
            )
        print(json.dumps({"status": "PASS", "mods": payload["mod_file_count"]}))
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "mods": payload["mod_file_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
