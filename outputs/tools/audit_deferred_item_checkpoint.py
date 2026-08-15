#!/usr/bin/env python3
"""Scan one stopped runtime world for every protected deferred ItemStack.

This is the runtime-checkpoint companion to the source/staging baseline audit.
It reuses the exact per-file scanner but does not waste time rescanning the
immutable source at every graceful-stop boundary.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import audit_candidate13_netherite_horse_armor as scanner
from candidate13_nbt_audit_common import collect_world_nbt_files, sha256


def audit(root: Path, label: str, workers: int) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    paths = collect_world_nbt_files(root)
    summary = {
        "root": str(root),
        "files": 0,
        "bytes": 0,
        "containers": 0,
        "matches": 0,
        "known_non_nbt_files": 0,
        "errors": 0,
    }
    matches: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    tasks = [(label, str(root), str(path)) for path in paths]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(scanner.scan_file, task): task for task in tasks}
        for completed, future in enumerate(as_completed(futures), 1):
            result = future.result()
            summary["files"] += 1
            summary["bytes"] += result["bytes"]
            summary["containers"] += result["containers"]
            summary["matches"] += len(result["matches"])
            summary["known_non_nbt_files"] += len(result["skipped_known_non_nbt"])
            summary["errors"] += len(result["errors"])
            matches.extend(
                {"root_label": label, "file": result["path"], **record}
                for record in result["matches"]
            )
            errors.extend(
                {"root_label": label, "file": result["path"], "error": error}
                for error in result["errors"]
            )
            skipped.extend(
                {"root_label": label, "file": result["path"], **record}
                for record in result["skipped_known_non_nbt"]
            )
            if completed % 100 == 0 or completed == len(tasks):
                print(
                    json.dumps(
                        {
                            "completed": completed,
                            "total": len(tasks),
                            "matches": len(matches),
                            "errors": len(errors),
                        }
                    ),
                    flush=True,
                )
    matches.sort(
        key=lambda row: (
            row["root_label"],
            row["file"],
            row.get("mca_slot", -1),
            row["path"],
        )
    )
    return {
        "schema": 1,
        "status": "PASS" if not errors else "BLOCKED_PARSE_ERRORS",
        "category": "deferred_item_runtime_checkpoint_audit",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "read_only": True,
        "target_item": scanner.TARGET_ITEM,
        "workers": workers,
        "process_pid": os.getpid(),
        "roots": {label: summary},
        "totals": {
            "files": summary["files"],
            "bytes": summary["bytes"],
            "containers": summary["containers"],
            "matches": len(matches),
            "known_non_nbt_files": len(skipped),
            "errors": len(errors),
        },
        "matches": matches,
        "skipped_known_non_nbt": skipped,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--label", default="runtime")
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.workers <= 20:
        parser.error("--workers must be in [1,20]")
    if not args.label or any(character.isspace() for character in args.label):
        parser.error("--label must be a non-empty token without whitespace")

    report = audit(args.world, args.label, args.workers)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    scanner.write_markdown(report, args.output_md)
    print(
        json.dumps(
            {
                "status": report["status"],
                "matches": len(report["matches"]),
                "errors": len(report["errors"]),
                "json_sha256": sha256(args.output_json),
                "md_sha256": sha256(args.output_md),
            }
        ),
        flush=True,
    )
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
