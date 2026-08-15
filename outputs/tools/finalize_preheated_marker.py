#!/usr/bin/env python3
"""Finalize an interrupted preheat without rescanning the world NBT.

The expensive world converter writes its own report before the orchestration
process assembles the completion marker.  This helper only validates those
reports, rechecks the immutable source snapshot, and creates an explicit
preheated marker with ``chunks`` still pending.  It never edits the source.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def load_orchestrator():
    path = Path(__file__).with_name("prepare_fast_migration.py")
    spec = importlib.util.spec_from_file_location("prepare_fast_migration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"report root is not an object: {path}")
    return value


def require_report(path: Path, allowed_statuses: set[str]) -> dict:
    if not path.is_file():
        raise RuntimeError(f"required sub-report is missing: {path}")
    value = read_json(path)
    status = value.get("status")
    if status not in allowed_statuses:
        raise RuntimeError(f"unexpected status {status!r} in {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-game-dir", type=Path, required=True)
    parser.add_argument("--staging-game-dir", type=Path, required=True)
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--additional-report",
        action="append",
        default=[],
        type=Path,
        help="supplemental conversion reports to bind into the marker (for targeted follow-up fixes)",
    )
    args = parser.parse_args()

    source = args.source_game_dir.resolve()
    staging = args.staging_game_dir.resolve()
    reports = args.reports_dir.resolve()
    report_path = args.report.resolve()
    if source == staging or not source.is_dir() or not staging.is_dir():
        raise RuntimeError("source and staging must be distinct existing directories")

    orchestrator = load_orchestrator()
    baseline = orchestrator.validate_baseline_manifest(
        read_json(args.baseline_manifest), source, staging
    )
    # This is deliberately a full source hash check.  A preheat marker is only
    # useful if it is tied to the exact bytes from which the region output came.
    orchestrator.assert_source_snapshot_stable(source, baseline)

    world_report_path = reports / "world-convert.json"
    if not world_report_path.is_file():
        raise RuntimeError(f"required sub-report is missing: {world_report_path}")
    world_report = read_json(world_report_path)
    if not isinstance(world_report.get("world"), str) or not isinstance(
        world_report.get("counts"), dict
    ):
        raise RuntimeError(f"world conversion report has an invalid shape: {world_report_path}")
    blockers = []
    for key in (
        "level_blockers",
        "unsupported_attributes",
        "unsupported_entities",
        "unsupported_entity_items",
        "unsupported_equipment",
        "unsupported_leashes",
        "unsupported_player_equipment",
        "unsupported_player_items",
        "unsupported_player_respawns",
        "unsupported_game_rules",
        "malformed_regions",
    ):
        value = world_report.get(key, [])
        if value:
            blockers.append({"field": key, "count": len(value)})
    if blockers:
        raise RuntimeError(f"world conversion has blocking records: {blockers}")

    saveddata = require_report(reports / "vanilla-saveddata.json", {"CONVERTED", "ALREADY_TARGET"})
    tracks = require_report(reports / "create-tracks.json", {"CONVERTED", "ALREADY_TARGET"})
    logistics = require_report(reports / "create-logistics.json", {"CONVERTED", "ALREADY_TARGET"})
    for name in ("mineastr-config.json", "mineastr-cache.json", "xiyuslogin-migration.json"):
        if not (reports / name).is_file():
            raise RuntimeError(f"required migration report is missing: {reports / name}")

    supplemental_reports = []
    for path in args.additional_report:
        path = path.resolve()
        value = read_json(path)
        blockers = []
        for key in (
            "unsupported_block_entities",
            "unsupported_entities",
            "unsupported_attributes",
            "malformed_regions",
            "level_blockers",
        ):
            records = value.get(key, [])
            if records:
                blockers.append({"field": key, "count": len(records)})
        if blockers:
            raise RuntimeError(f"supplemental conversion report has blocking records: {blockers}")
        supplemental_reports.append(
            {"path": str(path), "sha256": sha256(path), "summary": {
                "regions": len(value.get("regions", [])),
                "block_entity_print_stage_aliases": len(value.get("block_entity_print_stage_aliases", [])),
                "unsupported_block_entities": len(value.get("unsupported_block_entities", [])),
            }}
        )

    pending = ["chunks"]
    summary = {
        "schema": 1,
        "phase": "convert-finalize-preheat",
        "status": "PREHEATED_STAGING_PENDING_SAVEDDATA",
        "source_root": str(source),
        "staging_root": str(staging),
        "baseline_snapshot_sha256": baseline["snapshot_sha256"],
        "pending_saveddata": pending,
        "source_stability": "PASS",
        "world_report": {"path": str(world_report_path), "sha256": sha256(world_report_path)},
        "world_summary": {
            "regions": len(world_report.get("regions", [])),
            "players": len(world_report.get("players", [])),
            "entities": world_report.get("counts", {}).get("entities"),
            "unsupported": 0,
            "inherited_missing_schematic_files": len(world_report.get("inherited_missing_schematic_files", [])),
        },
        "subreports": {
            name: {"path": str(reports / name), "sha256": sha256(reports / name)}
            for name in (
                "vanilla-saveddata.json",
                "create-tracks.json",
                "create-logistics.json",
                "mineastr-config.json",
                "mineastr-cache.json",
                "xiyuslogin-migration.json",
            )
        },
        "supplemental_reports": supplemental_reports,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    orchestrator.atomic_json(report_path, summary)
    marker = orchestrator.make_conversion_marker(
        source,
        staging,
        baseline,
        report_path,
        staging,
        pending_saveddata=pending,
    )
    marker_path = orchestrator.conversion_marker_path(staging)
    orchestrator.atomic_json(marker_path, marker)
    print(json.dumps({"status": summary["status"], "report": str(report_path), "marker": str(marker_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
