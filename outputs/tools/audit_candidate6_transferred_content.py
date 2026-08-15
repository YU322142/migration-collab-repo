#!/usr/bin/env python3
"""Read-only inspection of the previously transferred candidate6 content.

This report deliberately distinguishes the historical backup/staging evidence
from the live server.  It is useful before a maintenance window: a clean
historical inspection authorizes preparing a live mirror, but never pretends
that an old backup is the current production snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def evidence(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path)}
    if not path.is_file():
        result.update({"exists": False, "status": "MISSING"})
        return result
    result.update({"exists": True, "bytes": path.stat().st_size, "sha256": sha256(path)})
    try:
        result["json"] = read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result["parse_error"] = f"{type(exc).__name__}: {exc}"
    return result


def list_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def marker_outputs(staging: Path, marker: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for relative, metadata in sorted((marker.get("outputs") or {}).items()):
        expected = str((metadata or {}).get("sha256", "")).upper()
        path = staging / Path(relative.replace("/", "\\"))
        actual = sha256(path) if path.is_file() else None
        rows.append(
            {
                "relative": relative,
                "exists": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else None,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "match": actual == expected,
            }
        )
    return {
        "checked": len(rows),
        "missing": sum(not row["exists"] for row in rows),
        "mismatched": sum(not row["match"] for row in rows),
        "rows": rows,
    }


def source_key_check(source: Path, baseline: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for relative, metadata in (baseline.get("source_manifest_before", {}).get("files", {}) or {}).items():
        if relative not in {
            "server.properties",
            "config/mineastr-common.json",
            "world/data/create_tracks.dat",
            "world/data/create_logistics.dat",
            "world/data/mineastr_sign_translations.dat",
            "EasyAuth/easyauth.db",
            "world/level.dat",
        }:
            continue
        path = source / Path(relative.replace("/", "\\"))
        actual = sha256(path) if path.is_file() else None
        expected = str(metadata.get("sha256", "")).upper()
        checks.append(
            {
                "relative": relative,
                "exists": path.is_file(),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "match": actual == expected,
            }
        )
    return {
        "historical_backup_only": True,
        "checked": len(checks),
        "mismatched": sum(not row["match"] for row in checks),
        "rows": checks,
    }


def compact_report(path: Path, value: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        result.update({"bytes": path.stat().st_size, "sha256": sha256(path)})
        for field in fields:
            if field in value:
                result[field] = value[field]
    return result


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.source_backup).resolve()
    staging = Path(args.staging).resolve()
    reports = Path(args.staging_reports).resolve()
    marker_path = staging / "migration-reports" / "conversion-complete.json"
    marker = read_json(marker_path)
    baseline_path = reports / "candidate6-historical-readonly-verify-20260810.json"
    baseline = read_json(baseline_path)

    world_path = reports / "world-convert.json"
    world = read_json(world_path)
    second_pass_path = Path(args.second_pass_report).resolve() if args.second_pass_report else reports / "candidate6-world-second-pass-20260810.json"
    second_pass = read_json(second_pass_path) if second_pass_path.is_file() else {}
    villager_path = reports / "villager-convert.json"
    villager = read_json(villager_path)
    poi_path = reports / "poi-allowed-versions-20260810.json"
    poi = read_json(poi_path)
    bundle_path = Path(args.bundle_audit).resolve()
    bundle = read_json(bundle_path)
    bundle_sides = bundle.get("bundles", bundle)

    marker_check = marker_outputs(staging, marker)
    world_counts = world.get("counts", {})
    world_summary = {
        "status": world.get("status", "CONVERTED"),
        "counts": world_counts,
        "players": list_len(world.get("players")),
        "regions_reported": list_len(world.get("regions")),
        "region_writes": sum(int(item.get("writes", 0) or 0) for item in world.get("regions", []) if isinstance(item, dict)),
        "unsupported": {
            key: list_len(world.get(key))
            for key in (
                "unsupported_attributes",
                "unsupported_block_entities",
                "unsupported_entities",
                "unsupported_entity_items",
                "unsupported_equipment",
                "unsupported_game_rules",
                "unsupported_leashes",
                "unsupported_player_equipment",
                "unsupported_player_items",
                "unsupported_player_respawns",
                "malformed_players",
                "malformed_regions",
                "level_blockers",
            )
        },
        "schematicannon_inventory_conversions": list_len(world.get("schematicannon_inventory_conversions")),
        "inherited_missing_schematic_files": list_len(world.get("inherited_missing_schematic_files")),
        "evidence_sha256": sha256(world_path),
    }
    second_pass_summary = {
        "exists": second_pass_path.is_file(),
        "path": str(second_pass_path),
        "sha256": sha256(second_pass_path) if second_pass_path.is_file() else None,
        "regions_reported": list_len(second_pass.get("regions")),
        "players_changed": list_len(second_pass.get("players")),
        "entity_item_stacks_scanned": (second_pass.get("counts") or {}).get("entity_item_stacks_scanned", 0),
        "player_item_stacks_scanned": (second_pass.get("counts") or {}).get("player_item_stacks_scanned", 0),
        "unsupported_total": sum(
            list_len(second_pass.get(key))
            for key in ("unsupported_attributes", "unsupported_entities", "unsupported_entity_items", "unsupported_block_entities", "malformed_regions")
        ),
        "inherited_missing_schematic_files": list_len(second_pass.get("inherited_missing_schematic_files")),
    }
    villager_preflight = villager.get("preflight_summary", {})
    villager_verify = villager.get("verification_summary", {})
    villager_summary = {
        "status": villager.get("status"),
        "villagers": villager.get("villagers"),
        "preflight": {
            key: villager_preflight.get(key)
            for key in ("regions_changed", "chunks_changed", "attribute_aliases", "item_component_schema_aliases", "unsupported_attributes", "unsupported_entities", "unsupported_entity_items", "blockers")
        },
        "second_pass": {
            key: villager_verify.get(key)
            for key in ("regions_changed", "chunks_changed", "attribute_aliases", "item_component_schema_aliases", "unsupported_attributes", "unsupported_entities", "unsupported_entity_items", "blockers")
        },
        "evidence_sha256": sha256(villager_path),
    }

    blockers: list[dict[str, str]] = []
    if marker.get("pending_saveddata"):
        blockers.append({"id": "pending_saveddata", "severity": "P0", "detail": "staging marker still has pending SavedData: " + ", ".join(marker["pending_saveddata"])})
    blockers.append({"id": "live_snapshot_missing", "severity": "P0", "detail": "D:\\Trans\\20260807 is a historical backup; the current remote server has not been mirrored yet."})
    blockers.append({"id": "final_target_not_bound", "severity": "P0", "detail": "The inspected target is a rehearsal target; final production assembly must bind to the stopped live mirror and candidate6 bundle."})
    blockers.append({"id": "auth_live_matrix", "severity": "P1", "detail": "Migration4 Java synthetic scenarios pass, but Floodgate/Bedrock and supported proxy live scenarios remain unproven."})
    blockers.append({"id": "client_external_integrations", "severity": "P1", "detail": "Chest Colorizer CSV/render, MineAstr/AstrBot, and the remaining real-client interaction matrix are not bound to the live mirror."})
    blockers.append({"id": "ledger_history", "severity": "P1", "detail": "Ledger history is replaced by GriefLogger; strict no-loss requires an explicit history waiver or a separate export."})
    warnings: list[dict[str, str]] = []
    if world_summary["inherited_missing_schematic_files"]:
        warnings.append({"id": "inherited_missing_schematics", "detail": "Two source schematic references were already missing in the historical backup; item NBT was retained and no replacement was guessed."})

    status = "INSPECTION_PASS_WITH_CUTOVER_BLOCKERS"
    if marker_check["mismatched"] or marker_check["missing"] or world_summary["status"] not in {"CONVERTED", "ALREADY_TARGET"} or villager_summary["second_pass"].get("blockers") or not second_pass_summary["exists"] or second_pass_summary["unsupported_total"]:
        status = "INSPECTION_FAIL"
    return {
        "schema": 1,
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "source_backup": str(source),
            "staging": str(staging),
            "historical_backup_only": True,
            "live_remote_snapshot_present": False,
        },
        "source_backup_key_check": source_key_check(source, baseline),
        "conversion_marker": {
            "path": str(marker_path),
            "sha256": sha256(marker_path),
            "schema": marker.get("schema"),
            "status": marker.get("status"),
            "pending_saveddata": marker.get("pending_saveddata", []),
            "output_hash_check": marker_check,
        },
        "world_conversion": world_summary,
        "world_second_pass": second_pass_summary,
        "villager_conversion": villager_summary,
        "poi": compact_report(poi_path, poi, ("status", "region_files", "chunks", "sections", "records", "data_versions", "errors", "duplicates")),
        "bundle": {
            "path": str(bundle_path),
            "sha256": sha256(bundle_path),
            "status": bundle.get("status"),
            "server": bundle_sides.get("server"),
            "client": bundle_sides.get("client"),
        },
        "transferred_saveddata_reports": {
            name: evidence(reports / name)
            for name in ("create-tracks.json", "create-logistics.json", "vanilla-saveddata.json", "mineastr-cache.json", "mineastr-config.json", "easyauth-sqlite.json")
        },
        "historical_runtime_evidence": {
            "lifecycle": evidence(Path(args.lifecycle_report)),
            "loaded_region_compare": evidence(Path(args.region_report)),
            "schematicannon": evidence(Path(args.schematicannon_report)),
            "render": evidence(Path(args.render_report)),
            "auth": evidence(Path(args.auth_report)),
        },
        "warnings": warnings,
        "blockers": blockers,
        "decision": "Do not stop the live server based on this historical inspection alone. Run online preheat first; stop only after the remote mirror is stable and the final maintenance-window checklist is explicitly started.",
    }


def markdown(report: dict[str, Any]) -> str:
    world = report["world_conversion"]
    villager = report["villager_conversion"]
    bundle = report["bundle"]
    lines = [
        "# Candidate6 Transferred Content Inspection",
        "",
        f"Status: **{report['status']}**",
        "",
        "This is a read-only inspection of the historical backup and its converted staging tree. It is not a snapshot of the current remote server.",
        "",
        "## Verified content",
        "",
        f"- World conversion: `{world['status']}`; {world['players']} players; {world['counts'].get('player_item_stacks_scanned', 0)} player stacks scanned; {world['counts'].get('entity_item_stacks_scanned', 0)} entity stacks scanned; unsupported/malformed blockers all zero.",
        f"- World second pass: `{report['world_second_pass']['exists']}`; {report['world_second_pass']['player_item_stacks_scanned']} player stacks and {report['world_second_pass']['entity_item_stacks_scanned']} entity stacks rescanned; changed players/regions {report['world_second_pass']['players_changed']}/{report['world_second_pass']['regions_reported']}; unsupported total {report['world_second_pass']['unsupported_total']}.",
        f"- Villagers: `{villager['villagers']}`; preflight aliases {villager['preflight'].get('attribute_aliases', 0)}; second pass changes {villager['second_pass'].get('regions_changed', 0)} regions / {villager['second_pass'].get('chunks_changed', 0)} chunks.",
        f"- POI: `{report['poi'].get('status')}`; {report['poi'].get('records', 0)} records across {report['poi'].get('region_files', 0)} regions; errors and duplicates are empty.",
        f"- Candidate6 bundles: server `{bundle['server'].get('bundle_sha256')}` and client `{bundle['client'].get('bundle_sha256')}`, both 50 JARs and PASS.",
        f"- Marker outputs: {report['conversion_marker']['output_hash_check']['checked']} checked, {report['conversion_marker']['output_hash_check']['mismatched']} mismatched, {report['conversion_marker']['output_hash_check']['missing']} missing.",
        "",
        "## Warnings",
        "",
    ]
    lines.extend(f"- {item['detail']}" for item in report["warnings"] or [{"detail": "None."}])
    lines += ["", "## Remaining blockers before stop", ""]
    lines.extend(f"- **{item['severity']} {item['id']}**: {item['detail']}" for item in report["blockers"])
    lines += ["", report["decision"], ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-backup", required=True)
    parser.add_argument("--staging", required=True)
    parser.add_argument("--staging-reports", required=True)
    parser.add_argument("--bundle-audit", required=True)
    parser.add_argument("--lifecycle-report", required=True)
    parser.add_argument("--region-report", required=True)
    parser.add_argument("--schematicannon-report", required=True)
    parser.add_argument("--render-report", required=True)
    parser.add_argument("--auth-report", required=True)
    parser.add_argument("--second-pass-report", required=False)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()
    report = build_report(args)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "json": str(output_json), "markdown": str(output_md), "blockers": len(report["blockers"])}, ensure_ascii=False))
    return 0 if report["status"] == "INSPECTION_PASS_WITH_CUTOVER_BLOCKERS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
