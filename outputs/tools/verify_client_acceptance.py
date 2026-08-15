#!/usr/bin/env python3
"""Fail-closed acceptance gate for the real NeoForge client.

This gate deliberately separates immutable bundle checks from evidence that can
only be produced by a running client and the real authentication/AstrBot
services.  A clean JAR manifest or a server smoke test is not accepted as a
substitute for a screenshot, GUI interaction, or protocol login.

The evidence document is intentionally small and contains hashes/booleans,
not credentials, passwords, player NBT, or unredacted protocol transcripts.
See ``outputs/client-acceptance-evidence-template-20260809.json``.

Exit codes:
  0: all bundle and real-client suites are PASS (client release gate closed)
  1: bundle/evidence integrity or schema failure
  2: evidence is missing/incomplete (NO-GO, but the immutable bundle is valid)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zipfile
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 1
HEX64_RE = re.compile(r"^[0-9A-Fa-f]{64}$")

REQUIRED_MOD_IDS = {
    "colorizer",
    "mineastr",
    "xiyuslogin",
}

REQUIRED_BUNDLE_MARKERS: dict[str, tuple[str, ...]] = {
    "colorizer": (
        "META-INF/neoforge.mods.toml",
        "colorizer.mixins.json",
        "net/immortaldevs/colorizer/ChestColorizer.class",
        "net/immortaldevs/colorizer/mixin/ChestRendererMixin.class",
        "assets/colorizer/textures/entity/chest/red.png",
    ),
    "mineastr": (
        "META-INF/neoforge.mods.toml",
        "com/mineastr/MineAstrClient.class",
        "com/mineastr/MineAstrNetwork.class",
        "assets/mineastr/lang/zh_cn.json",
    ),
    "xiyuslogin": (
        "META-INF/neoforge.mods.toml",
        "xiyuslogin.mixins.json",
        "org/xiyu/yee/xiyuslogin/manager/AuthManager.class",
    ),
}

# These scenario names are part of the release contract.  Keep them stable so
# a later release-gate script can consume this report without guessing what a
# human tester actually exercised.
REQUIRED_SCENARIOS: dict[str, tuple[str, ...]] = {
    "java_client": (
        "cold_start",
        "connect_target",
        "render_models_textures",
        "gui_hud_interaction",
        "sound_particles",
        "save_restart_reconnect",
    ),
    "chest_colorizer": (
        "csv_migrated_and_round_trip",
        "vanilla_chest_all_colors",
        "vanilla_barrel_all_colors",
        "open_close_and_break_drop",
        "sodium_or_vanilla_renderer",
    ),
    "mineastr_astrbot": (
        "client_gui_visible",
        "websocket_handshake",
        "capability_queries",
        "permission_and_approval",
        "reconnect_after_restart",
    ),
    "xiyuslogin": (
        "java_existing_bcrypt_correct",
        "java_existing_bcrypt_wrong_rejected",
        "java_empty_record_registration_policy",
        "java_restart_reauthentication",
        "bedrock_floodgate_uuid_mapping",
        "proxy_ip_session_policy",
    ),
}

REQUIRED_ARTIFACT_KINDS: dict[str, frozenset[str]] = {
    "java_client": frozenset({"client-log", "screenshot"}),
    "chest_colorizer": frozenset({"colorizer-csv", "screenshot"}),
    "mineastr_astrbot": frozenset(
        {"client-log", "redacted-protocol-transcript", "screenshot"}
    ),
    "xiyuslogin": frozenset({"auth-gate-report", "redacted-login-transcript"}),
}


class GateError(RuntimeError):
    """A fail-closed, reportable gate error."""

    def __init__(self, code: str, detail: str | None = None):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path, code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise GateError(code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError(code) from exc
    if not isinstance(value, dict):
        raise GateError(code)
    return value


def require_hex(value: object, code: str) -> str:
    text = str(value or "")
    if not HEX64_RE.fullmatch(text):
        raise GateError(code)
    return text.upper()


def resolve_under(path_value: object, root: Path, code: str) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise GateError(code)
    path = Path(path_value)
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise GateError(code) from exc
    return resolved


def bundle_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item.get("file", "")).lower()):
        digest.update(str(row["file"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["sha256"]).upper().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def validate_bundle(mods_dir: Path, manifest_path: Path) -> dict[str, Any]:
    if mods_dir.is_symlink() or not mods_dir.is_dir():
        raise GateError("CLIENT_MODS_DIR_MISSING_OR_SYMLINK")
    manifest = read_json(manifest_path, "CLIENT_BUNDLE_MANIFEST_INVALID")
    if manifest.get("schema") != 1 or manifest.get("side") != "client":
        raise GateError("CLIENT_BUNDLE_MANIFEST_SCHEMA_UNSUPPORTED")
    expected_rows = manifest.get("files")
    if not isinstance(expected_rows, list) or not expected_rows:
        raise GateError("CLIENT_BUNDLE_MANIFEST_FILES_INVALID")
    expected: dict[str, dict[str, Any]] = {}
    for row in expected_rows:
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            raise GateError("CLIENT_BUNDLE_MANIFEST_ROW_INVALID")
        name = row["file"]
        # A manifest is a filename contract, never a path traversal contract.
        if Path(name).name != name or name.lower() in {".", ".."}:
            raise GateError("CLIENT_BUNDLE_FILENAME_UNSAFE")
        if name in expected:
            raise GateError("CLIENT_BUNDLE_DUPLICATE_FILENAME")
        expected[name] = row
        require_hex(row.get("sha256"), "CLIENT_BUNDLE_MANIFEST_HASH_INVALID")
        if not isinstance(row.get("bytes"), int) or row["bytes"] < 1:
            raise GateError("CLIENT_BUNDLE_MANIFEST_SIZE_INVALID")
    if int(manifest.get("file_count", -1)) != len(expected):
        raise GateError("CLIENT_BUNDLE_COUNT_MISMATCH")

    actual_files = list(mods_dir.iterdir())
    if any(item.is_symlink() for item in actual_files):
        raise GateError("CLIENT_BUNDLE_SYMLINK_PRESENT")
    actual_by_name = {item.name: item for item in actual_files if item.is_file()}
    extra_nonfiles = [item.name for item in actual_files if not item.is_file()]
    if extra_nonfiles:
        raise GateError("CLIENT_BUNDLE_NONFILE_ENTRY_PRESENT")
    expected_names = set(expected)
    actual_names = set(actual_by_name)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    if missing:
        raise GateError("CLIENT_BUNDLE_MISSING:" + ",".join(missing))
    if extra:
        raise GateError("CLIENT_BUNDLE_EXTRA:" + ",".join(extra))

    rows: list[dict[str, Any]] = []
    for name in sorted(expected, key=str.lower):
        path = actual_by_name[name]
        if path.suffix.lower() != ".jar":
            raise GateError("CLIENT_BUNDLE_NON_JAR_ENTRY:" + name)
        expected_row = expected[name]
        actual_size = path.stat().st_size
        actual_hash = sha256(path)
        if actual_size != expected_row["bytes"] or actual_hash != str(expected_row["sha256"]).upper():
            raise GateError("CLIENT_BUNDLE_JAR_DIGEST_MISMATCH:" + name)
        try:
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise GateError("CLIENT_BUNDLE_JAR_CRC_FAILED:" + name)
        except (OSError, zipfile.BadZipFile) as exc:
            raise GateError("CLIENT_BUNDLE_JAR_INVALID:" + name) from exc
        rows.append({"file": name, "bytes": actual_size, "sha256": actual_hash})

    actual_digest = bundle_digest(rows)
    expected_digest = require_hex(manifest.get("bundle_sha256"), "CLIENT_BUNDLE_DIGEST_INVALID")
    if actual_digest != expected_digest:
        raise GateError("CLIENT_BUNDLE_DIGEST_MISMATCH")
    present_ids: set[str] = set()
    marker_summary: dict[str, dict[str, Any]] = {}
    for row in expected.values():
        ids = row.get("mod_ids", [])
        if isinstance(ids, list):
            present_ids.update(str(item) for item in ids)
    missing_ids = sorted(REQUIRED_MOD_IDS - present_ids)
    if missing_ids:
        raise GateError("CLIENT_REQUIRED_MOD_MISSING:" + ",".join(missing_ids))
    for mod_id, markers in REQUIRED_BUNDLE_MARKERS.items():
        matching = [
            name
            for name, row in expected.items()
            if mod_id in {str(item) for item in row.get("mod_ids", [])}
        ]
        if len(matching) != 1:
            raise GateError("CLIENT_REQUIRED_MOD_AMBIGUOUS:" + mod_id)
        jar_path = actual_by_name[matching[0]]
        try:
            with zipfile.ZipFile(jar_path) as archive:
                names = set(archive.namelist())
        except (OSError, zipfile.BadZipFile) as exc:
            raise GateError("CLIENT_BUNDLE_JAR_INVALID:" + matching[0]) from exc
        missing_markers = sorted(set(markers) - names)
        if missing_markers:
            raise GateError(
                "CLIENT_REQUIRED_ASSET_MISSING:" + mod_id + ":" + ",".join(missing_markers)
            )
        marker_summary[mod_id] = {
            "jar": matching[0],
            "required_markers": list(markers),
            "all_present": True,
        }
    return {
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": sha256(manifest_path),
        "mods_dir": str(mods_dir.resolve()),
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "bundle_sha256": actual_digest,
        "required_mod_ids": sorted(REQUIRED_MOD_IDS),
        "required_mod_ids_present": True,
        "static_markers": marker_summary,
    }


def _scenario_status(value: object) -> str:
    if isinstance(value, str):
        return value.upper()
    if isinstance(value, dict):
        return str(value.get("status", "")).upper()
    return ""


def validate_artifacts(
    artifacts: object,
    evidence_root: Path,
    suite_name: str,
) -> list[dict[str, Any]]:
    if not isinstance(artifacts, list) or not artifacts:
        raise GateError("CLIENT_SUITE_ARTIFACTS_MISSING:" + suite_name)
    result: list[dict[str, Any]] = []
    kinds: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise GateError("CLIENT_ARTIFACT_ROW_INVALID:" + suite_name)
        path = resolve_under(item.get("path"), evidence_root, "CLIENT_ARTIFACT_PATH_INVALID:" + suite_name)
        if path.is_symlink() or not path.is_file():
            raise GateError("CLIENT_ARTIFACT_MISSING:" + suite_name)
        expected_hash = require_hex(item.get("sha256"), "CLIENT_ARTIFACT_HASH_INVALID:" + suite_name)
        actual_hash = sha256(path)
        if expected_hash != actual_hash:
            raise GateError("CLIENT_ARTIFACT_HASH_MISMATCH:" + suite_name)
        if item.get("contains_secrets") is not False:
            raise GateError("CLIENT_ARTIFACT_SECRET_FLAG:" + suite_name)
        kind = str(item.get("kind", "unspecified"))
        kinds.add(kind)
        result.append(
            {
                "path": path.relative_to(evidence_root.resolve()).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": actual_hash,
                "kind": kind,
            }
        )
    missing_kinds = sorted(REQUIRED_ARTIFACT_KINDS[suite_name] - kinds)
    if missing_kinds:
        raise GateError(
            "CLIENT_ARTIFACT_KINDS_INCOMPLETE:"
            + suite_name
            + ":"
            + ",".join(missing_kinds)
        )
    return result


def validate_scenario_artifacts(
    scenario_value: object,
    evidence_root: Path,
    suite_name: str,
    scenario_name: str,
) -> list[dict[str, Any]]:
    """Require a separately hash-bound, redacted artifact for an auth scenario."""
    if not isinstance(scenario_value, dict):
        raise GateError("CLIENT_SCENARIO_ROW_INVALID:" + suite_name + ":" + scenario_name)
    artifacts = scenario_value.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise GateError("CLIENT_SCENARIO_ARTIFACTS_MISSING:" + suite_name + ":" + scenario_name)
    result: list[dict[str, Any]] = []
    for item in artifacts:
        if not isinstance(item, dict):
            raise GateError("CLIENT_SCENARIO_ARTIFACT_INVALID:" + suite_name + ":" + scenario_name)
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
            raise GateError("CLIENT_SCENARIO_ARTIFACT_PATH_INVALID:" + suite_name + ":" + scenario_name)
        candidate = evidence_root / raw_path
        if candidate.is_symlink():
            raise GateError("CLIENT_SCENARIO_ARTIFACT_SYMLINK:" + suite_name + ":" + scenario_name)
        path = resolve_under(raw_path, evidence_root, "CLIENT_SCENARIO_ARTIFACT_PATH_INVALID:" + suite_name)
        if not path.is_file():
            raise GateError("CLIENT_SCENARIO_ARTIFACT_MISSING:" + suite_name + ":" + scenario_name)
        if item.get("contains_secrets") is not False:
            raise GateError("CLIENT_SCENARIO_ARTIFACT_SECRET_FLAG:" + suite_name + ":" + scenario_name)
        expected_hash = require_hex(
            item.get("sha256"),
            "CLIENT_SCENARIO_ARTIFACT_HASH_INVALID:" + suite_name + ":" + scenario_name,
        )
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise GateError("CLIENT_SCENARIO_ARTIFACT_HASH_MISMATCH:" + suite_name + ":" + scenario_name)
        result.append(
            {
                "path": path.relative_to(evidence_root.resolve()).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": actual_hash,
                "kind": str(item.get("kind", "unspecified")),
            }
        )
    return result


def validate_suite(
    name: str,
    value: object,
    evidence_root: Path,
    expected_client_digest: str,
    expected_server_digest: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError("CLIENT_SUITE_INVALID:" + name)
    if value.get("status") != "PASS":
        raise GateError("CLIENT_SUITE_NOT_PASS:" + name)
    scenarios = value.get("scenarios")
    required = REQUIRED_SCENARIOS[name]
    if not isinstance(scenarios, dict) or set(scenarios) != set(required):
        raise GateError("CLIENT_SCENARIOS_INCOMPLETE:" + name)
    failed = [scenario for scenario in required if _scenario_status(scenarios[scenario]) != "PASS"]
    if failed:
        raise GateError("CLIENT_SCENARIO_FAILED:" + name + ":" + ",".join(failed))
    if str(value.get("client_bundle_sha256", "")).upper() != expected_client_digest:
        raise GateError("CLIENT_SUITE_BUNDLE_BINDING_MISMATCH:" + name)
    if str(value.get("server_bundle_sha256", "")).upper() != expected_server_digest:
        raise GateError("CLIENT_SUITE_SERVER_BINDING_MISMATCH:" + name)
    if value.get("tested_with_secrets") is not False:
        raise GateError("CLIENT_SUITE_SECRET_FLAG:" + name)
    artifacts = validate_artifacts(value.get("artifacts"), evidence_root, name)
    scenario_artifacts = {
        scenario: validate_scenario_artifacts(scenarios[scenario], evidence_root, name, scenario)
        for scenario in required
    } if name == "xiyuslogin" else {}
    return {
        "status": "PASS",
        "scenario_count": len(required),
        "scenarios": list(required),
        "artifacts": artifacts,
        "scenario_artifacts": scenario_artifacts,
        "notes": str(value.get("notes", "")),
    }


def validate_evidence(
    evidence_path: Path,
    evidence_root: Path,
    bundle: dict[str, Any],
    expected_server_digest: str,
) -> dict[str, Any]:
    try:
        evidence_path.resolve().relative_to(evidence_root.resolve())
    except (OSError, ValueError) as exc:
        raise GateError("CLIENT_EVIDENCE_OUTSIDE_ROOT") from exc
    evidence = read_json(evidence_path, "CLIENT_EVIDENCE_INVALID")
    if evidence.get("schema") != SCHEMA_VERSION:
        raise GateError("CLIENT_EVIDENCE_SCHEMA_UNSUPPORTED")
    if evidence.get("status") != "PASS":
        raise GateError("CLIENT_EVIDENCE_NOT_PASS")
    if evidence.get("contains_secrets") is not False:
        raise GateError("CLIENT_EVIDENCE_SECRET_FLAG")
    environment = evidence.get("environment")
    if not isinstance(environment, dict):
        raise GateError("CLIENT_EVIDENCE_ENVIRONMENT_MISSING")
    if environment.get("minecraft_version") != "1.21.1":
        raise GateError("CLIENT_EVIDENCE_MINECRAFT_VERSION_MISMATCH")
    if str(environment.get("loader", "")).lower() != "neoforge":
        raise GateError("CLIENT_EVIDENCE_LOADER_MISMATCH")
    try:
        if int(environment.get("java_major", -1)) != 21:
            raise GateError("CLIENT_EVIDENCE_JAVA_VERSION_MISMATCH")
    except (TypeError, ValueError) as exc:
        raise GateError("CLIENT_EVIDENCE_JAVA_VERSION_MISMATCH") from exc
    if environment.get("address_redacted") is not True:
        raise GateError("CLIENT_EVIDENCE_ADDRESS_NOT_REDACTED")
    if str(evidence.get("client_bundle_sha256", "")).upper() != bundle["bundle_sha256"]:
        raise GateError("CLIENT_EVIDENCE_BUNDLE_BINDING_MISMATCH")
    if str(evidence.get("server_bundle_sha256", "")).upper() != expected_server_digest:
        raise GateError("CLIENT_EVIDENCE_SERVER_BINDING_MISMATCH")
    tested_at = evidence.get("tested_at_utc")
    if not isinstance(tested_at, str) or not tested_at.endswith("Z"):
        raise GateError("CLIENT_EVIDENCE_TIMESTAMP_INVALID")
    try:
        datetime.fromisoformat(tested_at[:-1] + "+00:00")
    except ValueError as exc:
        raise GateError("CLIENT_EVIDENCE_TIMESTAMP_INVALID") from exc
    suites = evidence.get("suites")
    if not isinstance(suites, dict) or set(suites) != set(REQUIRED_SCENARIOS):
        raise GateError("CLIENT_EVIDENCE_SUITES_INCOMPLETE")
    checked: dict[str, Any] = {}
    for name in REQUIRED_SCENARIOS:
        checked[name] = validate_suite(
            name, suites[name], evidence_root, bundle["bundle_sha256"], expected_server_digest
        )
    return {
        "evidence": str(evidence_path.resolve()),
        "evidence_root": str(evidence_root.resolve()),
        "evidence_sha256": sha256(evidence_path),
        "tested_at_utc": tested_at,
        "operator": str(evidence.get("operator", "")),
        "environment": {
            "minecraft_version": environment["minecraft_version"],
            "loader": environment["loader"],
            "java_major": int(environment["java_major"]),
        },
        "suites": checked,
    }


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    evidence_root = args.evidence_root.resolve()
    if evidence_root.is_symlink() or not evidence_root.is_dir():
        raise GateError("CLIENT_EVIDENCE_ROOT_MISSING")
    expected_server = require_hex(args.expected_server_bundle_sha256, "EXPECTED_SERVER_BUNDLE_DIGEST_REQUIRED")
    mods_dir = args.client_mods.resolve()
    manifest_path = args.bundle_manifest.resolve()
    report_path = args.report.resolve()
    try:
        report_path.relative_to(mods_dir)
    except ValueError:
        pass
    else:
        raise GateError("CLIENT_REPORT_INSIDE_MODS_DIR")
    if report_path in {manifest_path, args.evidence.resolve()}:
        raise GateError("CLIENT_REPORT_OVERLAPS_INPUT")
    bundle = validate_bundle(mods_dir, manifest_path)
    try:
        evidence = validate_evidence(args.evidence.resolve(), evidence_root, bundle, expected_server)
    except GateError as exc:
        if not exc.code.startswith(
            ("CLIENT_EVIDENCE", "CLIENT_SUITE", "CLIENT_SCENARIO", "CLIENT_ARTIFACT")
        ):
            raise
        return {
            "schema": SCHEMA_VERSION,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "status": "NO_GO",
            "exit_code": 2,
            "error_code": exc.code,
            "detail": exc.detail,
            "bundle": bundle,
            "server_bundle_sha256": expected_server,
            "manual_suites_required": sorted(REQUIRED_SCENARIOS),
        }, 2
    report = {
        "schema": SCHEMA_VERSION,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": "PRODUCTION_CLIENT_GO",
        "exit_code": 0,
        "bundle": bundle,
        "server_bundle_sha256": expected_server,
        "evidence": evidence,
        "manual_suites_closed": sorted(REQUIRED_SCENARIOS),
    }
    return report, 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-mods", type=Path, required=True)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--expected-server-bundle-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report_path = args.report.resolve()
    try:
        report, code = build_report(args)
    except GateError as exc:
        report = {
            "schema": SCHEMA_VERSION,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "status": "NO_GO",
            "exit_code": 1,
            "error_code": exc.code,
            "detail": exc.detail,
        }
        code = 1
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(report_path), "exit_code": code}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
