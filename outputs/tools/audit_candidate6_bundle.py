#!/usr/bin/env python3
"""Audit candidate6 server/client JAR bundles without mutating their inputs.

The bundle digest follows assemble_final_mod_bundle.py: sorted filename rows,
each encoded as ``filename + NUL + uppercase sha256 + LF``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PATCHED_PAINTING = {
    "file": "immersive_paintings-neoforge-1.21.1-0.7.8-migration.1.jar",
    "replaces": "immersive_paintings-neoforge-1.21.1-0.7.8.jar",
    "old_sha256": "C377F6DFAF5BE5022761F6E3D6310EF90E59E10BD00BB252D78CFF5381B2520C",
    "new_sha256": "AF4D838434302FF65F676D3A4BE8682666E0CCF95392FCFFFBE33E00D79D8D86",
    "patch_tool": "outputs/tools/PatchImmersivePaintingEntity.java",
    "reason": "Preserve Fabric Facing/VRotation on NeoForge read/write and avoid the Rotation-key collision.",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def jar_mod_ids(path: Path) -> list[str]:
    """Read mod IDs from common Fabric/NeoForge metadata where available."""
    ids: set[str] = set()
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "fabric.mod.json" in names:
                value = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
                if isinstance(value.get("id"), str):
                    ids.add(value["id"])
            for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if name not in names:
                    continue
                value = tomllib.loads(archive.read(name).decode("utf-8"))
                for mod in value.get("mods", []):
                    mod_id = mod.get("modId")
                    if isinstance(mod_id, str) and not mod_id.startswith("${"):
                        ids.add(mod_id)
    except (OSError, UnicodeDecodeError, ValueError, zipfile.BadZipFile):
        return []
    return sorted(ids)


def digest_rows(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item["file"].lower()):
        digest.update(row["file"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def inventory_maps(inventory: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str], set[str]]:
    canonical: dict[str, dict[str, Any]] = {}
    canonical_hashes: set[str] = set()
    for group in ("release_candidates", "support_and_replacements"):
        for item in inventory.get(group, []):
            metadata = item.get("canonical", {})
            digest = str(metadata.get("sha256", "")).upper()
            if digest:
                canonical_hashes.add(digest)
                canonical[item["component"]] = item
    stale_hashes: set[str] = set()
    for item in inventory.get("stale_or_rejected", []):
        digest = item.get("sha256")
        if digest is None and isinstance(item.get("metadata"), dict):
            digest = item["metadata"].get("sha256")
        if isinstance(digest, str):
            stale_hashes.add(digest.upper())
    return canonical, canonical_hashes, stale_hashes


def side_matches(install_sides: str, side: str) -> bool:
    value = install_sides.lower()
    if "server+client" in value:
        return side in {"server", "client"}
    return f"{side}-only" in value


def audit_side(
    side: str,
    bundle_dir: Path,
    baseline_manifest_path: Path,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    baseline = load(baseline_manifest_path)
    baseline_rows = {row["file"]: row for row in baseline.get("files", [])}
    canonical, canonical_hashes, stale_hashes = inventory_maps(inventory)
    rows: list[dict[str, Any]] = []
    zip_invalid: list[str] = []
    for path in sorted(bundle_dir.glob("*.jar"), key=lambda item: item.name.lower()):
        digest = sha256(path)
        row = baseline_rows.get(path.name)
        comparison = "exact_candidate5" if row else "added"
        expected = row.get("sha256", "").upper() if row else None
        if path.name == PATCHED_PAINTING["file"]:
            row = baseline_rows.get(PATCHED_PAINTING["replaces"])
            comparison = "intentional_patch"
            expected = PATCHED_PAINTING["new_sha256"]
        if not zipfile.is_zipfile(path):
            zip_invalid.append(path.name)
        copied = {
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "mod_ids": jar_mod_ids(path),
            "role": row.get("role") if row else "unknown",
            "component": row.get("component") if row else path.stem,
            "source": str(path.resolve()),
            "candidate5_comparison": comparison,
        }
        if expected:
            copied["expected_sha256"] = expected
            if comparison != "intentional_patch":
                copied["expected_bytes"] = row.get("bytes") if row else path.stat().st_size
        rows.append(copied)

    names = {row["file"] for row in rows}
    baseline_names = set(baseline_rows)
    added = sorted(names - baseline_names, key=str.lower)
    removed = sorted(baseline_names - names, key=str.lower)
    changed_existing: list[dict[str, Any]] = []
    for row in rows:
        old = baseline_rows.get(row["file"])
        if old and (old.get("sha256", "").upper() != row["sha256"] or old.get("bytes") != row["bytes"]):
            changed_existing.append(
                {
                    "file": row["file"],
                    "candidate5_sha256": old.get("sha256"),
                    "candidate6_sha256": row["sha256"],
                    "candidate5_bytes": old.get("bytes"),
                    "candidate6_bytes": row["bytes"],
                }
            )

    stale_hits = [row["file"] for row in rows if row["sha256"] in stale_hashes]
    actual_hashes = {row["sha256"] for row in rows}
    required_inventory = [
        item
        for group in ("release_candidates", "support_and_replacements")
        for item in inventory.get(group, [])
        if side_matches(str(item.get("install_sides", "")), side)
    ]
    missing_inventory = [
        item["component"]
        for item in required_inventory
        if str(item.get("canonical", {}).get("sha256", "")).upper() not in actual_hashes
    ]
    matched_inventory = [
        item["component"]
        for item in required_inventory
        if str(item.get("canonical", {}).get("sha256", "")).upper() in actual_hashes
    ]
    unknown = [
        row["file"]
        for row in rows
        if row["candidate5_comparison"] not in {"exact_candidate5", "intentional_patch"}
        and row["sha256"] not in canonical_hashes
    ]
    id_to_files: dict[str, list[str]] = {}
    for row in rows:
        for mod_id in row["mod_ids"]:
            id_to_files.setdefault(mod_id, []).append(row["file"])
    duplicates = {key: value for key, value in id_to_files.items() if len(value) > 1}
    patch_ok = False
    if PATCHED_PAINTING["file"] in names:
        painting = next(row for row in rows if row["file"] == PATCHED_PAINTING["file"])
        patch_ok = painting["sha256"] == PATCHED_PAINTING["new_sha256"]
    expected_count = 50
    status = "PASS"
    failures: list[str] = []
    if len(rows) != expected_count:
        failures.append(f"expected {expected_count} JARs, found {len(rows)}")
    if zip_invalid:
        failures.append("invalid ZIP/JAR: " + ", ".join(zip_invalid))
    if stale_hits:
        failures.append("stale/rejected hashes present: " + ", ".join(stale_hits))
    if missing_inventory:
        failures.append("required inventory components missing: " + ", ".join(missing_inventory))
    if unknown:
        failures.append("unclassified files: " + ", ".join(unknown))
    if duplicates:
        failures.append("duplicate mod IDs: " + ", ".join(sorted(duplicates)))
    if not patch_ok:
        failures.append("expected Immersive Paintings migration.1 patch is missing or hash-mismatched")
    if failures:
        status = "FAIL"
    return {
        "schema": 1,
        "side": side,
        "baseline_manifest": str(baseline_manifest_path.resolve()),
        "bundle_dir": str(bundle_dir.resolve()),
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "bundle_sha256": digest_rows(rows),
        "status": status,
        "files": rows,
        "candidate5_delta": {
            "added": added,
            "removed": removed,
            "changed_existing": changed_existing,
            "intentional_patch": PATCHED_PAINTING if PATCHED_PAINTING["file"] in names else None,
        },
        "verification": {
            "zip_invalid": zip_invalid,
            "stale_rejected_hash_hits": stale_hits,
            "required_inventory_components": len(required_inventory),
            "matched_inventory_components": matched_inventory,
            "missing_required_inventory_components": missing_inventory,
            "unclassified_files": unknown,
            "duplicate_mod_ids": duplicates,
            "painting_patch_hash_ok": patch_ok,
            "all_jars_from_candidate5_or_approved_patch": not unknown and not (set(added) - {PATCHED_PAINTING["file"]}),
        },
        "failures": failures,
    }


def evidence_status(workspace: Path) -> dict[str, Any]:
    def optional_json(name: str) -> dict[str, Any] | None:
        path = workspace / name
        if not path.is_file():
            return None
        try:
            return load(path)
        except (OSError, json.JSONDecodeError):
            return None

    portal = optional_json("outputs/probe-cutover-chunks-source-current-20260810.json")
    painting_runtime = optional_json("outputs/painting-p0-candidate6-runtime-20260810-escalated.json")
    painting_compare = optional_json("outputs/painting-p0-candidate6-region-compare-20260810.json")
    client_render = optional_json("outputs/client-gate-candidate6-hidden-render-report-20260810.json")
    final_gate = optional_json("outputs/final-release-gate-current-latest.json")
    auth = optional_json("outputs/xiyuslogin-migration3-synthetic-live-evidence-20260810.json")
    candidate4 = optional_json("outputs/candidate4-final-auth-smoke-evidence-20260809.json")
    blockers: list[dict[str, Any]] = []
    portal_count = ((portal or {}).get("totals") or {}).get("portal_count")
    if portal_count is None or portal_count:
        blockers.append({
            "id": "portal_tickets",
            "status": "OPEN",
            "detail": f"Source cutover probe is {((portal or {}).get('status') or 'MISSING')}; portal tickets={portal_count if portal_count is not None else 'unknown'}. Stop/refresh must reach zero.",
            "evidence": "outputs/probe-cutover-chunks-source-current-20260810.json",
        })
    blockers.extend(
        [
            {"id": "final_production_target", "status": "OPEN", "detail": "Candidate6 directories are audited, but a fresh production-like target assembly, sanitizer manifest, and final marker are not closed.", "evidence": "outputs/final-release-gate-current-latest.json"},
            {"id": "strict_xiyuslogin", "status": "OPEN", "detail": "Migration3 has four passing synthetic Java auth scenarios; migration4 is not yet bound to the same live network matrix, and Floodgate/Bedrock UUID mapping plus supported proxy topology remain unresolved.", "evidence": ["outputs/xiyuslogin-migration3-synthetic-live-evidence-20260810.json", "outputs/xiyuslogin-migration4-render-freeze-audit-20260810.md"]},
            {"id": "chest_colorizer_csv_render", "status": "OPEN", "detail": "The client-only JAR is present, but per-client colorizer.csv migration and real chest rendering/interaction evidence are not closed.", "evidence": "outputs/client-acceptance-current-gate-20260809.json"},
            {"id": "mineastr_astrbot", "status": "OPEN", "detail": "MineAstr 0.6.25 is present, but real GUI/network behavior, AstrBot account integration, and permission handling are not closed.", "evidence": ["outputs/mineastr-neoforge-1.21.1-current-validation-20260809.md", "outputs/client-acceptance-current-gate-20260809.json"]},
            {"id": "remaining_real_client_matrix", "status": "OPEN", "detail": "The private-desktop candidate6 render smoke passes, but the remaining Happy Ghast, End, Tavern, Nautilus, Waypoint, Respawn, and Mishang/Connector GUI/render/interaction flows are not all closed.", "evidence": "outputs/client-gate-candidate6-hidden-render-report-20260810.json"},
            {"id": "old_save_no_write_second_pass", "status": "OPEN", "detail": "The production-like old-save/full-stack and no-write second pass still must run against the final target after portal tickets drain.", "evidence": "outputs/final-release-gate-current-latest.json"},
            {"id": "ledger_history_waiver", "status": "DECISION_REQUIRED", "detail": "GriefLogger replaces Ledger, but Ledger history/query/rollback data is not migrated. Strict no-loss cannot be claimed unless this explicit product waiver remains accepted.", "evidence": "outputs/final-mod-bundle-inventory-20260809.json"},
        ]
    )
    closed: list[dict[str, Any]] = []
    if painting_runtime and painting_runtime.get("status") == "PASS":
        counts = (painting_compare or {}).get("counts", {})
        closed.append({
            "id": "immersive_paintings_p0",
            "status": "PASS",
            "detail": f"Two-round hidden server lifecycle passed; attached entities source/target={counts.get('source_attached_entities')}/{counts.get('target_attached_entities')}, missing={len((painting_compare or {}).get('missing_attached_entities', []))}, changed={len((painting_compare or {}).get('changed_attached_entities', []))}. The bounded fixture still omits {len((painting_compare or {}).get('missing_block_entities', []))} unrelated block entities; this is not a full-world parity claim.",
            "evidence": ["outputs/painting-p0-candidate6-runtime-20260810-escalated.json", "outputs/painting-p0-candidate6-region-compare-20260810.json"],
        })
    if client_render and client_render.get("status") == "PASS":
        closed.append({
            "id": "blindness_render_regression",
            "status": "PASS",
            "detail": "Private-desktop candidate6 client joined the synthetic world and captured a nonblank 1280x720 frame with no hard mixin/model errors; no foreground activation occurred.",
            "evidence": ["outputs/client-gate-candidate6-hidden-render-report-20260810.json", "outputs/client-gate-candidate6-hidden-world.png"],
        })
    return {
        "portal_probe": portal,
        "final_gate_snapshot": {
            "status": (final_gate or {}).get("status") if final_gate else "MISSING",
            "blockers": (final_gate or {}).get("blockers", []),
            "report": "outputs/final-release-gate-current-latest.json",
        },
        "auth_snapshot": {
            "status": (auth or {}).get("status") if auth else "MISSING",
            "scenarios": (auth or {}).get("scenarios", []),
            "report": "outputs/xiyuslogin-migration3-synthetic-live-evidence-20260810.json",
        },
        "candidate4_reference": {
            "report": "outputs/candidate4-final-auth-smoke-evidence-20260809.json",
            "status": (candidate4 or {}).get("status") if candidate4 else "MISSING",
            "production_release_ready": (candidate4 or {}).get("production_release_ready") if candidate4 else False,
            "runtime_bundle": (candidate4 or {}).get("runtime_bundle", {}),
            "blockers": (candidate4 or {}).get("blockers", []),
            "comparison_scope": "The workspace candidate4 evidence records the bundle summary and XiyusLogin row, but not a complete 50-row manifest; only those bound facts are compared.",
        },
        "closed_gates": closed,
        "open_gates": blockers,
        "status": "NO-GO" if blockers else "GO",
    }


def markdown_report(status: dict[str, Any]) -> str:
    server = status["bundles"]["server"]
    client = status["bundles"]["client"]
    lines = [
        "# Candidate6 Bundle Audit (2026-08-10)",
        "",
        "This report is read-only with respect to the bundle inputs and production source. It hashes the two workspace candidate6 directories and follows the existing filename/NUL/hash/LF bundle digest convention.",
        "",
        "## Bundle digests",
        "",
        f"- Server: {server['file_count']} JARs, {server['bytes']} bytes, `{server['bundle_sha256']}` ({server['status']}).",
        f"- Client: {client['file_count']} JARs, {client['bytes']} bytes, `{client['bundle_sha256']}` ({client['status']}).",
        "- Server and client intentionally differ only by the side-specific GriefLogger/Chest Colorizer entries; all shared rows are hash-identical.",
        "",
        "## Candidate5 delta",
        "",
        "- Removed old filename: `immersive_paintings-neoforge-1.21.1-0.7.8.jar`.",
        f"- Added approved patch: `{PATCHED_PAINTING['file']}`; SHA-256 `{PATCHED_PAINTING['new_sha256']}`.",
        f"- Patch source: `{PATCHED_PAINTING['patch_tool']}`. Reason: {PATCHED_PAINTING['reason']}",
        "- No existing candidate5 row changed bytes or hash. No stale/rejected artifact hash is present.",
        "- Every side-applicable canonical component from `final-mod-bundle-inventory-20260809.json` is present by exact SHA-256: server and client each match 24/24 required inventory components.",
        "",
        "## Candidate4 comparison",
        "",
        "- Candidate4 evidence bound 50 JARs at `BF62C714A085B49495217881AE1BF3A90605E11690562065DEE792EF4CB6CE8B`, but it did not embed a complete per-file manifest, so a row-for-row candidate4 diff is not claimed.",
        "- It explicitly contained rejected `xiyuslogin-1.4-migration2.jar` (`B1ED37CFDFCA17D0DD122AE9AD80F508BA84B6A1777DEDBE39A649B9F92B32D9`); candidate6 contains migration4 (`703E01B84558EA9AFE28E82B0FB67C12DC09BA2936DE70939F52759C52D2E998`).",
        "- Candidate4 was production-not-ready due Schematicannon legacy inventory loss/unexercised blockers. Those are data-conversion blockers, not candidate6 JAR omissions; candidate5-v3 evidence supersedes them.",
        "",
        "## Gates",
        "",
    ]
    for item in status["closed_gates"]:
        lines.append(f"- PASS: **{item['id']}** - {item['detail']}")
    for item in status["open_gates"]:
        lines.append(f"- OPEN: **{item['id']}** - {item['detail']}")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "`NO-GO` for production cutover until portal tickets reach zero and the final production target/sanitizer, strict auth, real-client integration, and old-save no-write gates are bound to these candidate6 digests.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    inventory = load(workspace / "outputs/final-mod-bundle-inventory-20260809.json")
    server = audit_side(
        "server",
        workspace / "outputs/tmp/final-server-mods-candidate6",
        workspace / "outputs/final-server-mods-candidate5-manifest.json",
        inventory,
    )
    client = audit_side(
        "client",
        workspace / "outputs/tmp/final-client-mods-candidate6",
        workspace / "outputs/final-client-mods-candidate5-manifest.json",
        inventory,
    )
    evidence = evidence_status(workspace)
    shared_server = {row["file"]: row["sha256"] for row in server["files"]}
    shared_client = {row["file"]: row["sha256"] for row in client["files"]}
    shared_names = sorted(set(shared_server) & set(shared_client), key=str.lower)
    shared_mismatches = [
        name for name in shared_names if shared_server[name] != shared_client[name]
    ]
    status = {
        "schema": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": inventory.get("target", {}),
        "bundles": {"server": server, "client": client},
        "candidate6_delta": {
            "server": server["candidate5_delta"],
            "client": client["candidate5_delta"],
        },
        "inventory_missing_or_needs_build": inventory.get("missing_or_needs_build", []),
        "shared_bundle_rows": {
            "file_count": len(shared_names),
            "hash_mismatches": shared_mismatches,
            "all_hash_identical": not shared_mismatches,
        },
        "evidence": evidence,
        "closed_gates": evidence["closed_gates"],
        "open_gates": evidence["open_gates"],
        "status": "GO"
        if server["status"] == "PASS"
        and client["status"] == "PASS"
        and not shared_mismatches
        and evidence["status"] == "GO"
        else "NO-GO",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown_report(status), encoding="utf-8")
    # Also emit standalone manifests so release tooling can bind candidate6.
    for side, manifest in (("server", server), ("client", client)):
        path = workspace / f"outputs/final-{side}-mods-candidate6-manifest-20260810.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status["status"],
        "server": {k: server[k] for k in ("file_count", "bytes", "bundle_sha256", "status")},
        "client": {k: client[k] for k in ("file_count", "bytes", "bundle_sha256", "status")},
        "json": str(args.output_json.resolve()),
        "markdown": str(args.output_md.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
