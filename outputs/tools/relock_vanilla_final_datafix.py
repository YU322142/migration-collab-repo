#!/usr/bin/env python3
"""Adopt an audited converted staging tree without re-baselining from it.

This narrowly-scoped helper upgrades the raw authority baseline from a fresh
full source snapshot, binds every current derived output and converter/policy
fingerprint, and atomically installs the new baseline/marker only after the
candidate pair validates in isolation.  It never reads raw baseline bytes from
the already-converted staging tree.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import audit_vanilla_final_datafix as closure_audit
import prepare_fast_migration as migration


EXPECTED_SEMANTIC_REPLAY = {
    "world/data/chunks.dat": "convert_vanilla_saveddata.py",
    "world/DIM-1/data/chunks.dat": "convert_vanilla_saveddata.py",
    "world/DIM1/data/chunks.dat": "convert_vanilla_saveddata.py",
    "world/data/WorldUUID.dat": "convert_vanilla_saveddata.py",
    "world/level.dat": "convert_vanilla_saveddata.py",
    "world/data/raids.dat": "convert_vanilla_saveddata.py",
    "world/DIM-1/data/raids.dat": "convert_vanilla_saveddata.py",
    "world/DIM1/data/raids_end.dat": "convert_vanilla_saveddata.py",
    "world/data/scoreboard.dat": "convert_vanilla_saveddata.py",
    "world/data/create_tracks.dat": "convert_create_saveddata.py",
    "world/data/create_logistics.dat": "convert_create_saveddata.py",
}


def _regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} must be a regular non-symbolic file: {path}")


def _guard_paths(
    source: Path,
    staging: Path,
    work: Path,
    baseline: Path,
    report: Path,
    current_snapshot: Path,
    closure_report: Path,
    semantic_replay_report: Path,
) -> None:
    migration.ensure_distinct(source, staging)
    for root, label in ((source, "source"), (staging, "staging"), (work, "work")):
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError(f"{label} root must be a real directory: {root}")
    for path, label in (
        (baseline, "baseline manifest"),
        (report, "relock report"),
        (current_snapshot, "source snapshot"),
        (closure_report, "closure report"),
        (semantic_replay_report, "semantic replay report"),
    ):
        migration.ensure_outside_source(source, path, label)
    migration.ensure_outside_source(source, work, "work directory")
    if migration._paths_overlap(staging, work):
        raise RuntimeError("work directory must not overlap staging")
    if migration._paths_overlap(staging, baseline.parent):
        raise RuntimeError("baseline directory must not overlap staging")
    if report.resolve() in {baseline.resolve(), migration.conversion_marker_path(staging).resolve()}:
        raise RuntimeError("relock report must not overwrite baseline or marker")
    for path, label in (
        (current_snapshot, "source snapshot"),
        (closure_report, "closure report"),
        (semantic_replay_report, "semantic replay report"),
    ):
        _regular_file(path, label)


def atomic_pair(
    first_path: Path,
    first_value: dict,
    second_path: Path,
    second_value: dict,
    validate_installed,
) -> None:
    paths = (first_path, second_path)
    values = (first_value, second_value)
    temporary: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    committed: list[Path] = []
    commit_complete = False
    rollback_complete = False
    try:
        for path, value in zip(paths, values, strict=True):
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".migration.tmp")
            backup = path.with_name(path.name + ".migration.bak")
            if temp.exists() or backup.exists():
                raise RuntimeError(f"stale marker transaction artifact requires recovery: {path}")
            temp.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            json.loads(temp.read_text(encoding="utf-8"))
            temporary[path] = temp
            if path.exists():
                shutil.copy2(path, backup)
                backups[path] = backup
            else:
                backups[path] = None
        for path in paths:
            committed.append(path)
            os.replace(temporary[path], path)
        validate_installed()
        commit_complete = True
    except BaseException as commit_error:
        failures = []
        for path in reversed(committed):
            backup = backups.get(path)
            try:
                if backup is None:
                    path.unlink(missing_ok=True)
                elif backup.exists():
                    os.replace(backup, path)
                else:
                    failures.append(f"missing backup for {path}")
            except BaseException as rollback_error:
                failures.append(f"{path}: {type(rollback_error).__name__}: {rollback_error}")
        if failures:
            raise RuntimeError(
                f"baseline/marker commit failed and rollback is incomplete: {failures}"
            ) from commit_error
        rollback_complete = True
        raise
    finally:
        for temp in temporary.values():
            temp.unlink(missing_ok=True)
        if commit_complete or rollback_complete:
            for backup in backups.values():
                if backup is not None:
                    backup.unlink(missing_ok=True)


def validate_semantic_replay(value: object, staging: Path) -> None:
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise RuntimeError("current-tool semantic replay report has an unsupported schema")
    rows = value.get("rows")
    if (
        value.get("status") != "MATCH"
        or value.get("mismatch_count") != 0
        or not isinstance(rows, list)
        or len(rows) != len(EXPECTED_SEMANTIC_REPLAY)
    ):
        raise RuntimeError("current-tool semantic replay report is not a complete match")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("semantic replay contains a non-object row")
        relative = row.get("path")
        if relative in seen or EXPECTED_SEMANTIC_REPLAY.get(relative) != row.get("converter"):
            raise RuntimeError(f"semantic replay has an unexpected/duplicate row: {relative!r}")
        if row.get("semantic_match") is not True:
            raise RuntimeError(f"semantic replay mismatch: {relative}")
        target = migration.safe_join(staging, relative)
        _regular_file(target, f"semantic replay target {relative}")
        if str(row.get("staging_sha256", "")).upper() != migration.sha256(target).upper():
            raise RuntimeError(f"semantic replay staging hash is stale: {relative}")
        seen.add(relative)
    if seen != set(EXPECTED_SEMANTIC_REPLAY):
        raise RuntimeError("semantic replay row set is incomplete")


def relock(args: argparse.Namespace) -> dict:
    source = args.source_game_dir.resolve()
    staging = args.staging_game_dir.resolve()
    current_snapshot_path = args.current_source_snapshot.resolve()
    closure_report = args.closure_report.resolve()
    baseline_path = args.baseline_manifest.resolve()
    marker_path = migration.conversion_marker_path(staging)
    tools_dir = Path(__file__).resolve().parent
    work_dir = args.work_dir.resolve()
    report_path = args.report.resolve()
    semantic_replay_report = args.semantic_replay_report.resolve()
    _guard_paths(
        source,
        staging,
        work_dir,
        baseline_path,
        report_path,
        current_snapshot_path,
        closure_report,
        semantic_replay_report,
    )

    snapshot = json.loads(current_snapshot_path.read_text(encoding="utf-8"))
    if snapshot != migration.source_input_snapshot(source):
        raise RuntimeError("authoritative source no longer matches the fresh full snapshot")
    baseline = {
        **snapshot,
        "kind": "staged-raw-source-baseline",
        "root": str(source),
        "source_root": str(source),
        "staging_root": str(staging),
    }
    baseline = migration.validate_baseline_manifest(baseline, source, staging)
    migration.verify_unchanged_staging_inputs(
        staging,
        baseline["entries"],
        {"added": [], "modified": [], "deleted": [], "metadata_only": []},
    )

    closure = json.loads(closure_report.read_text(encoding="utf-8"))
    if (
        Path(str(closure.get("source_game_dir", ""))).resolve() != source
        or Path(str(closure.get("staging_game_dir", ""))).resolve() != staging
        or closure.get("source_scope_before") != closure.get("source_scope_after")
    ):
        raise RuntimeError("closure report is not bound to the current source/staging scope")
    if (
        closure.get("status") != "PASS"
        or closure.get("source_scope_unchanged") is not True
        or closure.get("maps", {}).get("status") != "MATCH"
        or closure.get("maps", {}).get("semantic_mismatches") != 0
        or closure.get("advancements", {}).get("status") != "ALREADY_TARGET"
        or closure.get("schematics", {}).get("status") != "MATCH"
        or closure.get("schematic_references", {}).get("status") != "MATCH"
    ):
        raise RuntimeError("closure report is not a complete passing final-datafix audit")

    # Re-run the deterministic read-only closure instead of trusting a stale PASS
    # document. This binds all map/advancement/schematic bytes to this invocation.
    reference_value = closure.get("schematic_references", {})
    reference_path_value = reference_value.get("evidence_report")
    if not isinstance(reference_path_value, str) or not reference_path_value:
        raise RuntimeError("closure report has no schematic reference evidence path")
    reference_path = Path(reference_path_value).resolve()
    _regular_file(reference_path, "schematic reference evidence")
    policy_path = tools_dir / "advancement_id_policy_20260813.json"
    live_closure = closure_audit.audit(source, staging, policy_path, reference_path)
    for key in ("maps", "advancements", "schematics", "schematic_references"):
        if live_closure.get(key) != closure.get(key):
            raise RuntimeError(f"closure report is stale for current {key}")

    semantic_replay = json.loads(semantic_replay_report.read_text(encoding="utf-8"))
    validate_semantic_replay(semantic_replay, staging)

    marker = migration.make_conversion_marker(
        source,
        staging,
        baseline,
        closure_report,
        staging,
        tools_dir=tools_dir,
    )
    parent_marker = None
    if marker_path.is_file():
        old = json.loads(marker_path.read_text(encoding="utf-8"))
        parent_marker = {
            "path": str(marker_path),
            "sha256": migration.sha256(marker_path),
            "source_root": old.get("source_root"),
            "staging_root": old.get("staging_root"),
            "baseline_snapshot_sha256": old.get("baseline_snapshot_sha256"),
        }
    marker["adoption"] = {
        "schema": 1,
        "mode": "authoritative-source-relock",
        "raw_baseline_source": str(current_snapshot_path),
        "raw_baseline_source_sha256": migration.sha256(current_snapshot_path),
        "closure_report": str(closure_report),
        "closure_report_sha256": migration.sha256(closure_report),
        "semantic_replay_report": str(semantic_replay_report),
        "semantic_replay_report_sha256": migration.sha256(semantic_replay_report),
        "parent_marker": parent_marker,
        "never_rebaselined_from_converted_staging": True,
    }

    candidate_root = Path(
        tempfile.mkdtemp(prefix="vanilla-final-datafix-relock-", dir=str(work_dir))
    )
    candidate_baseline = candidate_root / "source-baseline.json"
    candidate_marker = candidate_root / migration.CONVERSION_MARKER_RELATIVE
    try:
        migration.atomic_json(candidate_baseline, baseline)
        migration.atomic_json(candidate_marker, marker)
        candidate_baseline_value = migration.validate_baseline_manifest(
            json.loads(candidate_baseline.read_text(encoding="utf-8")), source, staging
        )
        migration.validate_conversion_marker(
            candidate_marker, source, staging, candidate_baseline_value, tools_dir
        )

        # Close the source/tool/report TOCTOU window immediately before commit.
        if snapshot != migration.source_input_snapshot(source):
            raise RuntimeError("authoritative source changed before relock commit")
        migration.assert_converter_fingerprints_stable(marker["converter_fingerprints"], tools_dir)
        if migration.sha256(closure_report) != marker["adoption"]["closure_report_sha256"]:
            raise RuntimeError("closure report changed before relock commit")
        if migration.sha256(semantic_replay_report) != marker["adoption"]["semantic_replay_report_sha256"]:
            raise RuntimeError("semantic replay report changed before relock commit")

        def validate_installed() -> None:
            installed_baseline = migration.validate_baseline_manifest(
                json.loads(baseline_path.read_text(encoding="utf-8")), source, staging
            )
            migration.validate_conversion_marker(
                marker_path, source, staging, installed_baseline, tools_dir
            )
            if snapshot != migration.source_input_snapshot(source):
                raise RuntimeError("authoritative source changed during relock commit")

        atomic_pair(
            baseline_path,
            baseline,
            marker_path,
            marker,
            validate_installed,
        )
    finally:
        shutil.rmtree(candidate_root, ignore_errors=True)

    return {
        "schema": 1,
        "status": "RELOCKED",
        "source_game_dir": str(source),
        "staging_game_dir": str(staging),
        "baseline_manifest": str(baseline_path),
        "baseline_manifest_sha256": migration.sha256(baseline_path),
        "baseline_snapshot_sha256": baseline["snapshot_sha256"],
        "baseline_files": baseline["files"],
        "baseline_bytes": baseline["bytes"],
        "conversion_marker": str(marker_path),
        "conversion_marker_sha256": migration.sha256(marker_path),
        "marker_outputs": len(marker["outputs"]),
        "converter_fingerprints": marker["converter_fingerprints"],
        "closure_report": str(closure_report),
        "closure_report_sha256": migration.sha256(closure_report),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-game-dir", type=Path, required=True)
    parser.add_argument("--staging-game-dir", type=Path, required=True)
    parser.add_argument("--current-source-snapshot", type=Path, required=True)
    parser.add_argument("--closure-report", type=Path, required=True)
    parser.add_argument("--semantic-replay-report", type=Path, required=True)
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = relock(args)
    except Exception as exc:
        result = {"schema": 1, "status": "BLOCKED", "blockers": [f"{type(exc).__name__}: {exc}"]}
        migration.atomic_json(args.report.resolve(), result)
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 2
    migration.atomic_json(args.report.resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
