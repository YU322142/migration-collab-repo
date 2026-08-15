#!/usr/bin/env python3
"""Read-only, double-hash estimate of the stopped-source cutover delta.

The full world conversion is preheated before maintenance. This probe measures
the remaining source delta against that frozen baseline without touching the
source or staging trees. It deliberately hashes every migration input twice so
a concurrent same-size rewrite cannot be mistaken for a stable stopped world.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from prepare_fast_migration import (
    CRITICAL_SOURCE_DELETIONS,
    assert_source_snapshot_stable,
    atomic_json,
    compare_snapshots,
    probe_session_lock,
    region_selector,
    source_input_snapshot,
    validate_baseline_manifest,
)


SCHEMA_VERSION = 1


class DeltaProbeError(ValueError):
    """The stopped-source delta cannot be accepted for refresh planning."""


def _outside(path: Path, protected: Path, label: str) -> Path:
    resolved = path.resolve()
    protected_resolved = protected.resolve()
    if resolved == protected_resolved or protected_resolved in resolved.parents:
        raise DeltaProbeError(f"{label} must be outside the source game directory")
    return resolved


def _entry_summary(entry: dict) -> dict:
    return {
        "source": entry["source"],
        "target": entry["target"],
        "kind": entry["kind"],
        "bytes": entry["bytes"],
        "sha256": entry["sha256"],
    }


def build_report(
    source: Path,
    baseline_path: Path,
    baseline: dict,
    current: dict,
    delta: dict,
    *,
    first_pass_seconds: float,
    stability_pass_seconds: float,
    lock_probe: dict,
) -> dict:
    added = [_entry_summary(entry) for entry in delta["added"]]
    modified = [
        {
            "source": entry["after"]["source"],
            "target": entry["after"]["target"],
            "kind": entry["after"]["kind"],
            "before_bytes": entry["before"]["bytes"],
            "before_sha256": entry["before"]["sha256"],
            "after_bytes": entry["after"]["bytes"],
            "after_sha256": entry["after"]["sha256"],
        }
        for entry in delta["modified"]
    ]
    deleted = [_entry_summary(entry) for entry in delta["deleted"]]
    metadata_only = [_entry_summary(entry) for entry in delta["metadata_only"]]

    changed_entries = [*delta["added"], *(item["after"] for item in delta["modified"])]
    selected_regions = sorted(
        selector
        for selector in (region_selector(entry) for entry in changed_entries)
        if selector is not None
    )
    changed_kinds = Counter(entry["kind"] for entry in changed_entries)
    deleted_sources = {entry["source"] for entry in delta["deleted"]}
    critical_deletions = sorted(deleted_sources & CRITICAL_SOURCE_DELETIONS)
    blockers: list[str] = []
    if deleted:
        blockers.append("source inputs were deleted after the preheated baseline")
    if critical_deletions:
        blockers.append("critical source inputs were deleted")

    has_content_delta = bool(added or modified or deleted)
    if blockers:
        status = "BLOCKED_SOURCE_DELETIONS"
        exit_code = 2
    elif has_content_delta:
        status = "STABLE_DELTA_READY_FOR_REFRESH"
        exit_code = 0
    else:
        status = "STABLE_NO_CONTENT_DELTA"
        exit_code = 0

    return {
        "schema": SCHEMA_VERSION,
        "status": status,
        "exit_code": exit_code,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_game_dir": str(source.resolve()),
        "baseline_manifest": str(baseline_path.resolve()),
        "staging_game_dir": baseline["staging_root"],
        "source_session_lock": lock_probe,
        "timing": {
            "first_full_hash_seconds": round(first_pass_seconds, 3),
            "stability_full_hash_seconds": round(stability_pass_seconds, 3),
            "total_seconds": round(first_pass_seconds + stability_pass_seconds, 3),
        },
        "baseline": {
            "files": baseline["files"],
            "bytes": baseline["bytes"],
            "snapshot_sha256": baseline["snapshot_sha256"],
        },
        "current": {
            "files": current["files"],
            "bytes": current["bytes"],
            "snapshot_sha256": current["snapshot_sha256"],
        },
        "delta": {
            "added_count": len(added),
            "modified_count": len(modified),
            "deleted_count": len(deleted),
            "metadata_only_count": len(metadata_only),
            "unchanged_count": delta["unchanged"],
            "changed_kinds": dict(sorted(changed_kinds.items())),
            "selected_regions": selected_regions,
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "metadata_only": metadata_only,
        },
        "critical_deletions": critical_deletions,
        "blockers": blockers,
        "note": (
            "This is a read-only stopped-source estimate. The transactional refresh "
            "repeats the same full-hash stability checks before committing anything."
        ),
    }


def probe(source: Path, baseline_path: Path) -> dict:
    source = source.resolve()
    if not source.is_dir():
        raise DeltaProbeError(f"source game directory does not exist: {source}")
    if not baseline_path.is_file():
        raise DeltaProbeError(f"baseline manifest does not exist: {baseline_path}")
    try:
        raw_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeltaProbeError(f"baseline manifest is not valid JSON: {baseline_path}") from exc
    staging = Path(str(raw_baseline.get("staging_root", "")))
    baseline = validate_baseline_manifest(raw_baseline, source, staging)
    lock_probe = probe_session_lock(source / "world")

    started = time.monotonic()
    current = source_input_snapshot(source)
    first_pass_seconds = time.monotonic() - started
    delta = compare_snapshots(baseline, current)

    stability_started = time.monotonic()
    assert_source_snapshot_stable(source, current)
    stability_pass_seconds = time.monotonic() - stability_started
    return build_report(
        source,
        baseline_path,
        baseline,
        current,
        delta,
        first_pass_seconds=first_pass_seconds,
        stability_pass_seconds=stability_pass_seconds,
        lock_probe=lock_probe,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Double-hash the stopped source and report its preheat delta"
    )
    parser.add_argument("source_game_dir", type=Path)
    parser.add_argument("baseline_manifest", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    report_path = _outside(args.report, args.source_game_dir, "report")
    try:
        report = probe(args.source_game_dir, args.baseline_manifest)
    except Exception as exc:
        failure = {
            "schema": SCHEMA_VERSION,
            "status": "DELTA_PROBE_FAILED",
            "exit_code": 2,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_game_dir": str(args.source_game_dir.resolve()),
            "baseline_manifest": str(args.baseline_manifest.resolve()),
            "blockers": [f"{type(exc).__name__}: {exc}"],
        }
        atomic_json(report_path, failure)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 2

    atomic_json(report_path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "exit_code": report["exit_code"],
                "report": str(report_path),
                "timing": report["timing"],
                "delta": {
                    key: report["delta"][key]
                    for key in (
                        "added_count",
                        "modified_count",
                        "deleted_count",
                        "metadata_only_count",
                        "unchanged_count",
                    )
                },
            },
            ensure_ascii=False,
        )
    )
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
