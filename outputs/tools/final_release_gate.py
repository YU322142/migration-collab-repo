#!/usr/bin/env python3
"""Fail-closed, read-only production release gate for the migration target.

The gate does not start or stop either server and never writes to source,
staging, or target.  It combines the independently produced cutover evidence
and rechecks mutable inputs (the source lock, chunks files, marker outputs, and
runtime JARs) before returning ``READY_FOR_PRODUCTION``.  A missing, malformed,
stale, conditional, or non-PASS input returns ``NO-GO`` with exit status 2.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import zipfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
READY = "READY_FOR_PRODUCTION"
NO_GO = "NO-GO"
HEX_256 = re.compile(r"^[0-9a-fA-F]{64}$")
CANONICAL_CHUNKS = {
    "overworld": "data/chunks.dat",
    "the_nether": "DIM-1/data/chunks.dat",
    "the_end": "DIM1/data/chunks.dat",
}
PASS_CATEGORIES = ("client", "auth", "integration")
LEGACY_ROOTS = ["world_nether", "world_the_end"]
REQUIRED_INTEGRATION_CHECKS = {
    "fullstack_cold_start",
    "reload_save_stop_restart",
    "semantic_world_compare",
    "villager_poi_gate",
    "create_saveddata_gate",
    "resource_sanitizer_gate",
    "mineastr_data_gate",
    "source_read_only_gate",
}
REQUIRED_AUTH_SCENARIOS = {
    "java_existing_bcrypt_correct",
    "java_existing_bcrypt_wrong_rejected",
    "java_empty_record_registration_policy",
    "java_restart_reauthentication",
    "bedrock_floodgate_uuid_mapping",
    "proxy_ip_session_policy",
}
TARGET_READY_MARKER_RELATIVE = Path("migration-reports/production-target-ready.json")
TRANSACTION_ID = re.compile(r"^[0-9a-fA-F]{32}$")


class GateError(RuntimeError):
    """An input cannot be accepted as production release evidence."""


def _load_tool(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise GateError(f"cannot load required tool: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_file_summary(path: Path, label: str) -> dict[str, Any]:
    raw_path = Path(path)
    reject_reparse_components(raw_path, label)
    path = raw_path.resolve()
    if not path.is_file():
        raise GateError(f"{label} is missing or is not a regular file: {path}")
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    reject_reparse_components(raw_path, label)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise GateError(f"{label} changed while it was hashed: {path}")
    return {"path": str(path), "bytes": after.st_size, "sha256": digest}


def read_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    raw_path = Path(path)
    reject_reparse_components(raw_path, label)
    path = raw_path.resolve()
    if not path.is_file():
        raise GateError(f"{label} is missing or is not a regular file: {path}")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    reject_reparse_components(raw_path, label)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise GateError(f"{label} changed while it was read: {path}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise GateError(f"{label} root must be a JSON object: {path}")
    return value, hashlib.sha256(raw).hexdigest().upper()


def require_hex(value: object, label: str) -> str:
    if not isinstance(value, str) or not HEX_256.fullmatch(value):
        raise GateError(f"{label} must be a 64-character SHA-256")
    return value.upper()


def require_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise GateError(f"{label} must be a non-negative integer")
    return value


def resolved_report_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise GateError(f"{label} path is missing")
    return Path(value).resolve()


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def reject_reparse_components(path: Path, label: str) -> None:
    candidate = path if path.is_absolute() else Path.cwd() / path
    for component in (candidate, *candidate.parents):
        try:
            is_junction = getattr(component, "is_junction", lambda: False)
            unsafe = component.is_symlink() or is_junction()
        except OSError as exc:
            raise GateError(
                f"cannot inspect {label} path component: {component}"
            ) from exc
        if unsafe:
            raise GateError(
                f"{label} contains a symbolic link or junction: {component}"
            )


def validate_production_assembly(
    assembly_report: Path,
    source: Path,
    staging: Path,
    target: Path,
    sanitizer_report: Path,
) -> dict[str, Any]:
    """Require both halves of the assembler's crash-safe commit contract."""
    source = source.resolve()
    staging = staging.resolve()
    target_input = Path(target)
    reject_reparse_components(target_input, "production target game directory")
    target = target_input.resolve()
    report_input = Path(assembly_report)
    marker_input = target / TARGET_READY_MARKER_RELATIVE
    for path, label in (
        (report_input, "production assembly report"),
        (marker_input, "production target ready marker"),
    ):
        reject_reparse_components(path, label)

    report_path = report_input.resolve()
    if any(path_is_within(report_path, root) for root in (source, staging, target)):
        raise GateError(
            "production assembly report must be outside source, staging, and target"
        )
    report, report_sha256 = read_json(report_input, "production assembly report")
    marker, marker_sha256 = read_json(marker_input, "production target ready marker")
    for value, label in (
        (report, "production assembly report"),
        (marker, "production target ready marker"),
    ):
        if value.get("schema") != 1:
            raise GateError(f"{label} has an unsupported schema")
        if value.get("status") != "ASSEMBLED_PRODUCTION_TARGET":
            raise GateError(f"{label} is not ASSEMBLED_PRODUCTION_TARGET")
        if value.get("ready_to_start") is not True:
            raise GateError(f"{label} is not ready_to_start")

    report_target = resolved_report_path(
        report.get("target_game_dir"), "assembly report target_game_dir"
    )
    marker_target = resolved_report_path(
        marker.get("target_game_dir"), "ready marker target_game_dir"
    )
    if report_target != target or marker_target != target:
        raise GateError("production assembly evidence belongs to a different target")
    if (
        resolved_report_path(
            report.get("target_ready_marker"), "assembly report target_ready_marker"
        )
        != marker_input.resolve()
    ):
        raise GateError("production assembly report points to a different ready marker")
    if (
        resolved_report_path(
            marker.get("external_report"), "ready marker external_report"
        )
        != report_path
    ):
        raise GateError("production target ready marker points to a different report")

    report_transaction = report.get("transaction_id")
    marker_transaction = marker.get("transaction_id")
    if (
        not isinstance(report_transaction, str)
        or not TRANSACTION_ID.fullmatch(report_transaction)
        or marker_transaction != report_transaction
    ):
        raise GateError(
            "production assembly transaction IDs are missing or inconsistent"
        )
    expected_report_sha256 = require_hex(
        marker.get("assembly_report_sha256"),
        "ready marker assembly_report_sha256",
    )
    if expected_report_sha256 != report_sha256:
        raise GateError(
            "production assembly report hash does not match the ready marker"
        )

    sanitizer_path = Path(sanitizer_report).resolve()
    expected_sanitizer_path = (
        target / "migration-reports" / "resource-sanitization.json"
    ).resolve()
    if sanitizer_path != expected_sanitizer_path:
        raise GateError(
            "sanitizer report must be the assembler-emitted target-local report"
        )
    if (
        resolved_report_path(
            report.get("sanitizer_report"), "assembly report sanitizer_report"
        )
        != sanitizer_path
    ):
        raise GateError("production assembly report binds a different sanitizer report")
    if (
        resolved_report_path(
            marker.get("sanitizer_report"), "ready marker sanitizer_report"
        )
        != sanitizer_path
    ):
        raise GateError(
            "production target ready marker binds a different sanitizer report"
        )

    if (
        stable_file_summary(report_input, "production assembly report")["sha256"]
        != report_sha256
    ):
        raise GateError("production assembly report changed during final gate")
    if (
        stable_file_summary(marker_input, "production target ready marker")["sha256"]
        != marker_sha256
    ):
        raise GateError("production target ready marker changed during final gate")

    return {
        "status": "PASS",
        "transaction_id": report_transaction,
        "target_game_dir": str(target),
        "assembly_report": str(report_path),
        "assembly_report_sha256": report_sha256,
        "target_ready_marker": str(marker_input.resolve()),
        "target_ready_marker_sha256": marker_sha256,
    }


def validate_probe_payload(
    value: dict[str, Any], source_world: Path, label: str
) -> dict[str, Any]:
    if value.get("schema") != 1:
        raise GateError(f"{label} has an unsupported schema")
    if value.get("status") != "READY_PORTAL_ZERO" or value.get("exit_code") != 0:
        raise GateError(
            f"{label} is not READY_PORTAL_ZERO: status={value.get('status')!r}, "
            f"exit_code={value.get('exit_code')!r}"
        )
    if value.get("blockers") != []:
        raise GateError(f"{label} contains blockers")
    if (
        resolved_report_path(value.get("source_world"), f"{label}.source_world")
        != source_world
    ):
        raise GateError(f"{label} belongs to a different world")

    dimensions = value.get("dimensions")
    if not isinstance(dimensions, list) or len(dimensions) != len(CANONICAL_CHUNKS):
        raise GateError(f"{label} must contain exactly three canonical dimensions")
    by_name: dict[str, dict[str, Any]] = {}
    for row in dimensions:
        if not isinstance(row, dict) or not isinstance(row.get("dimension"), str):
            raise GateError(f"{label} contains an invalid dimension record")
        name = row["dimension"]
        if name in by_name:
            raise GateError(f"{label} duplicates dimension {name}")
        by_name[name] = row
    if set(by_name) != set(CANONICAL_CHUNKS):
        raise GateError(f"{label} does not contain the canonical dimension set")

    ticket_total = forced_total = 0
    signatures: dict[str, dict[str, Any]] = {}
    for name, relative in CANONICAL_CHUNKS.items():
        row = by_name[name]
        if row.get("relative") != relative or row.get("status") != "OK":
            raise GateError(f"{label}.{name} has the wrong path or status")
        expected_path = (source_world / PurePosixPath(relative)).resolve()
        if (
            resolved_report_path(row.get("path"), f"{label}.{name}.path")
            != expected_path
        ):
            raise GateError(f"{label}.{name} points outside the canonical world")
        if row.get("portal_count") != 0 or row.get("portal") != []:
            raise GateError(f"{label}.{name} still contains portal tickets")
        ticket_count = require_nonnegative_int(
            row.get("ticket_count"), f"{label}.{name}.ticket_count"
        )
        forced_count = require_nonnegative_int(
            row.get("forced_count"), f"{label}.{name}.forced_count"
        )
        if ticket_count < forced_count:
            raise GateError(f"{label}.{name} ticket count is inconsistent")
        data_version = row.get("data_version")
        if data_version not in {3955, 4671}:
            raise GateError(
                f"{label}.{name} has unsupported DataVersion {data_version!r}"
            )
        digest = require_hex(row.get("sha256"), f"{label}.{name}.sha256")
        size = require_nonnegative_int(row.get("bytes"), f"{label}.{name}.bytes")
        ticket_total += ticket_count
        forced_total += forced_count
        signatures[name] = {
            "relative": relative,
            "data_version": data_version,
            "schema": row.get("schema"),
            "bytes": size,
            "sha256": digest,
            "ticket_count": ticket_count,
            "forced_count": forced_count,
            "portal_count": 0,
        }

    totals = value.get("totals")
    if not isinstance(totals, dict):
        raise GateError(f"{label}.totals must be an object")
    expected_totals = {
        "ticket_count": ticket_total,
        "forced_count": forced_total,
        "portal_count": 0,
    }
    if totals != expected_totals:
        raise GateError(f"{label}.totals do not match its dimensions")
    return {"dimensions": signatures, "totals": expected_totals}


def validate_chunks_report(path: Path, source_world: Path) -> dict[str, Any]:
    source_world = source_world.resolve()
    value, report_digest = read_json(path, "chunks probe report")
    recorded = validate_probe_payload(value, source_world, "chunks probe report")

    probe = _load_tool("probe_cutover_chunks.py", "final_gate_chunks_probe")
    current_value = probe.probe_world(source_world)
    current = validate_probe_payload(
        current_value, source_world, "current chunks probe"
    )
    if recorded != current:
        raise GateError(
            "chunks probe report is stale; canonical chunks changed after it was written"
        )
    return {
        "status": "PASS",
        "report": str(path.resolve()),
        "report_sha256": report_digest,
        "source_world": str(source_world),
        "totals": current["totals"],
        "dimensions": current["dimensions"],
    }


def validate_source_lock(source_world: Path) -> dict[str, Any]:
    source_world = source_world.resolve()
    migration = _load_tool("prepare_fast_migration.py", "final_gate_migration_lock")
    try:
        result = migration.probe_session_lock(source_world)
    except Exception as exc:
        raise GateError(f"source session lock probe failed: {exc}") from exc
    status = result.get("status") if isinstance(result, dict) else None
    if status not in {"ABSENT", "UNLOCKED_READ_ONLY_PROBE"}:
        raise GateError(f"source session lock probe did not pass: {status!r}")
    return {"status": "PASS", "probe_status": status, "path": result.get("path")}


def validate_conversion_marker(
    source: Path, staging: Path, baseline_path: Path, marker_path: Path
) -> dict[str, Any]:
    source = source.resolve()
    staging = staging.resolve()
    marker_path = marker_path.resolve()
    if marker_path.is_symlink():
        raise GateError("conversion marker must not be a symbolic link")
    migration = _load_tool("prepare_fast_migration.py", "final_gate_migration_marker")
    canonical_marker = migration.conversion_marker_path(staging).resolve()
    if marker_path != canonical_marker:
        raise GateError(
            f"conversion marker is not the staging canonical marker: {canonical_marker}"
        )
    try:
        baseline, marker = migration.validate_final_conversion_gate(
            marker_path, source, staging, baseline_path.resolve()
        )
    except Exception as exc:
        raise GateError(
            f"conversion marker is incomplete, stale, or invalid: {exc}"
        ) from exc
    if marker.get("pending_saveddata") != []:
        raise GateError("conversion marker pending_saveddata must be exactly empty")
    return {
        "status": "PASS",
        "marker": str(marker_path),
        "marker_sha256": sha256(marker_path),
        "baseline": str(baseline_path.resolve()),
        "baseline_snapshot_sha256": require_hex(
            baseline.get("snapshot_sha256"), "baseline.snapshot_sha256"
        ),
        "pending_saveddata": [],
        "output_count": len(marker.get("outputs", {})),
    }


def physical_manifest(value: dict[str, Any], label: str) -> dict[str, Any]:
    rows = value.get("files")
    if not isinstance(rows, list) or not rows:
        raise GateError(f"{label}.files must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    bundle = hashlib.sha256()
    for index, row in enumerate(rows):
        row_label = f"{label}.files[{index}]"
        if not isinstance(row, dict):
            raise GateError(f"{row_label} must be an object")
        filename = row.get("file")
        if (
            not isinstance(filename, str)
            or not filename.lower().endswith(".jar")
            or Path(filename).name != filename
            or filename in seen
        ):
            raise GateError(f"{row_label}.file is invalid or duplicated")
        size = require_nonnegative_int(row.get("bytes"), f"{row_label}.bytes")
        digest = require_hex(row.get("sha256"), f"{row_label}.sha256")
        seen.add(filename)
        normalized.append({"file": filename, "bytes": size, "sha256": digest})
        bundle.update(filename.encode("utf-8"))
        bundle.update(b"\0")
        bundle.update(digest.encode("ascii"))
        bundle.update(b"\n")
    if [row["file"] for row in normalized] != sorted(
        seen, key=lambda name: name.lower()
    ):
        raise GateError(f"{label}.files are not in deterministic order")
    if value.get("file_count") != len(normalized):
        raise GateError(f"{label}.file_count does not match files")
    if value.get("bytes") != sum(row["bytes"] for row in normalized):
        raise GateError(f"{label}.bytes does not match files")
    bundle_digest = require_hex(value.get("bundle_sha256"), f"{label}.bundle_sha256")
    if bundle.hexdigest().upper() != bundle_digest:
        raise GateError(f"{label}.bundle_sha256 does not match files")
    return {
        "file_count": len(normalized),
        "bytes": sum(row["bytes"] for row in normalized),
        "bundle_sha256": bundle_digest,
        "files": normalized,
    }


def scan_target_mods(mods_dir: Path) -> dict[str, Any]:
    mods_dir = mods_dir.resolve()
    if mods_dir.is_symlink() or not mods_dir.is_dir():
        raise GateError(f"target mods directory is missing or linked: {mods_dir}")
    rows = []
    for path in sorted(mods_dir.glob("*.jar"), key=lambda item: item.name.lower()):
        if path.is_symlink() or not path.is_file():
            raise GateError(f"runtime JAR must be a regular non-linked file: {path}")
        if not zipfile.is_zipfile(path):
            raise GateError(f"runtime artifact is not a ZIP/JAR: {path}")
        rows.append(
            {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        )
    bundle = hashlib.sha256()
    for row in rows:
        bundle.update(row["file"].encode("utf-8"))
        bundle.update(b"\0")
        bundle.update(row["sha256"].encode("ascii"))
        bundle.update(b"\n")
    return {
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "bundle_sha256": bundle.hexdigest().upper(),
        "files": rows,
    }


def extract_runtime_manifest(value: dict[str, Any], label: str) -> dict[str, Any]:
    if "runtime_mod_manifest" in value:
        manifest = value["runtime_mod_manifest"]
    elif isinstance(value.get("resource_sanitization"), dict):
        manifest = value["resource_sanitization"].get("runtime_mod_manifest")
    elif {"file_count", "bytes", "bundle_sha256", "files"} <= set(value):
        manifest = value
    else:
        raise GateError(f"{label} has no runtime_mod_manifest")
    if not isinstance(manifest, dict):
        raise GateError(f"{label}.runtime_mod_manifest must be an object")
    return physical_manifest(manifest, f"{label}.runtime_mod_manifest")


def validate_sanitizer(
    source: Path,
    staging: Path,
    target: Path,
    mods: Path,
    report_path: Path,
    expected_manifest_path: Path | None,
) -> dict[str, Any]:
    migration = _load_tool("prepare_fast_migration.py", "final_gate_migration_sanitize")
    try:
        target, mods = migration.ensure_target_copy_isolated(
            source, staging, target, mods
        )
    except Exception as exc:
        raise GateError(f"target copy isolation check failed: {exc}") from exc
    value, report_digest = read_json(report_path, "target sanitizer report")
    if value.get("schema") != 1 or value.get("status") != "SANITIZED_TARGET_COPY":
        raise GateError("target sanitizer outer status is not SANITIZED_TARGET_COPY")
    if value.get("protected_tree_unchanged") is not True:
        raise GateError("target sanitizer did not prove protected_tree_unchanged=true")
    if (
        resolved_report_path(value.get("target_game_dir"), "sanitizer target_game_dir")
        != target
    ):
        raise GateError("target sanitizer report belongs to a different target")
    if (
        resolved_report_path(value.get("target_mods_dir"), "sanitizer target_mods_dir")
        != mods
    ):
        raise GateError("target sanitizer report belongs to a different mods directory")
    if value.get("source_guard_before") != value.get("source_guard_after"):
        raise GateError("target sanitizer source guards differ")
    if value.get("staging_guard_before") != value.get("staging_guard_after"):
        raise GateError("target sanitizer staging guards differ")

    inner = value.get("resource_sanitization")
    if not isinstance(inner, dict) or inner.get("schema") != 1:
        raise GateError("target sanitizer nested report is missing or invalid")
    if inner.get("status") not in {"SANITIZED", "ALREADY_CLEAN"}:
        raise GateError("target sanitizer nested status is not successful")
    changed_files = require_nonnegative_int(
        inner.get("changed_files"), "resource_sanitization.changed_files"
    )
    if inner.get("status") == "ALREADY_CLEAN" and changed_files != 0:
        raise GateError("ALREADY_CLEAN sanitizer report has non-zero changed_files")
    if (
        resolved_report_path(inner.get("world"), "resource_sanitization.world")
        != (target / "world").resolve()
    ):
        raise GateError("nested sanitizer report belongs to a different world")
    if (
        resolved_report_path(
            inner.get("server_properties"), "resource_sanitization.server_properties"
        )
        != (target / "server.properties").resolve()
    ):
        raise GateError(
            "nested sanitizer report belongs to different server.properties"
        )
    if resolved_report_path(inner.get("mods"), "resource_sanitization.mods") != mods:
        raise GateError("nested sanitizer report belongs to a different mods directory")
    changes = inner.get("changes")
    if not isinstance(changes, list) or len(changes) != changed_files:
        raise GateError("nested sanitizer changes do not match changed_files")
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("path"), str):
            raise GateError("nested sanitizer contains an invalid change record")
        if not path_is_within(Path(change["path"]), target):
            raise GateError("nested sanitizer records a change outside target")

    recorded = extract_runtime_manifest(inner, "resource_sanitization")
    actual = scan_target_mods(mods)
    if recorded != actual:
        raise GateError("target runtime JARs do not exactly match sanitizer manifest")
    expected_digest = None
    if expected_manifest_path is not None:
        expected_value, expected_report_digest = read_json(
            expected_manifest_path, "expected runtime manifest"
        )
        expected = extract_runtime_manifest(expected_value, "expected runtime manifest")
        if expected != actual:
            raise GateError(
                "target runtime JARs do not match the expected runtime manifest"
            )
        expected_digest = expected_report_digest
    return {
        "status": "PASS",
        "report": str(report_path.resolve()),
        "report_sha256": report_digest,
        "target": str(target),
        "mods": str(mods),
        "nested_status": inner["status"],
        "changed_files": changed_files,
        "runtime_mod_manifest": {
            key: actual[key] for key in ("file_count", "bytes", "bundle_sha256")
        },
        "expected_manifest": str(expected_manifest_path.resolve())
        if expected_manifest_path is not None
        else None,
        "expected_manifest_sha256": expected_digest,
    }


def validate_legacy_policy(
    path: Path, source: Path, staging: Path, target: Path
) -> dict[str, Any]:
    value, marker_digest = read_json(path, "legacy policy marker")
    if value.get("schema") != 1 or value.get("status") != "PASS":
        raise GateError("legacy policy marker status must be exactly PASS")
    if value.get("decision") != "ARCHIVE_ONLY_DO_NOT_MERGE":
        raise GateError("legacy policy decision must be ARCHIVE_ONLY_DO_NOT_MERGE")
    if value.get("merge_into_canonical") is not False:
        raise GateError("legacy policy must explicitly set merge_into_canonical=false")
    if value.get("roots") != LEGACY_ROOTS:
        raise GateError(f"legacy policy must name exactly {LEGACY_ROOTS}")
    if (
        resolved_report_path(
            value.get("source_game_dir"), "legacy policy source_game_dir"
        )
        != source.resolve()
    ):
        raise GateError("legacy policy marker belongs to a different source")
    audit_path = resolved_report_path(
        value.get("audit_report"), "legacy policy audit_report"
    )
    if audit_path.is_symlink() or not audit_path.is_file():
        raise GateError(f"legacy dimension audit report is missing: {audit_path}")
    audit_before = audit_path.stat()
    audit_raw = audit_path.read_bytes()
    audit_after = audit_path.stat()
    if (audit_before.st_size, audit_before.st_mtime_ns) != (
        audit_after.st_size,
        audit_after.st_mtime_ns,
    ):
        raise GateError("legacy dimension audit report changed while it was read")
    audit_digest = hashlib.sha256(audit_raw).hexdigest().upper()
    expected_digest = require_hex(
        value.get("audit_report_sha256"), "legacy policy audit_report_sha256"
    )
    if audit_digest != expected_digest:
        raise GateError("legacy policy audit report hash does not match")
    try:
        decoded_audit = audit_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateError("legacy dimension audit report is not UTF-8") from exc
    try:
        audit_json = json.loads(decoded_audit)
    except json.JSONDecodeError:
        audit_json = None
    supported_audit_status = False
    if isinstance(audit_json, dict):
        supported_audit_status = audit_json.get("status") in {
            "BLOCKED_LEGACY_WORLD_POLICY_REQUIRED",
            "PASS",
        }
    else:
        supported_audit_status = bool(
            re.search(
                r"(?im)^Status:\s*(?:\*\*)?"
                r"(?:BLOCKED_LEGACY_WORLD_POLICY_REQUIRED|PASS)(?:\*\*)?\s*$",
                decoded_audit,
            )
        )
    if not supported_audit_status:
        raise GateError("legacy dimension audit report has an unsupported status")
    archives = value.get("archives")
    if not isinstance(archives, dict) or set(archives) != set(LEGACY_ROOTS):
        raise GateError("legacy policy must bind exactly two archive artifacts")
    archive_tool = _load_tool(
        "archive_legacy_roots.py", "final_gate_archive_legacy_roots"
    )
    archive_summaries: dict[str, Any] = {}
    for name in LEGACY_ROOTS:
        record = archives[name]
        if not isinstance(record, dict):
            raise GateError(f"legacy archive record is invalid: {name}")
        archive_path = resolved_report_path(
            record.get("path"), f"legacy archive {name}.path"
        )
        if any(
            path_is_within(archive_path, protected)
            for protected in (source, staging, target)
        ):
            raise GateError(f"legacy archive must be outside protected trees: {name}")
        actual = stable_file_summary(archive_path, f"legacy archive {name}")
        if actual["bytes"] != require_nonnegative_int(
            record.get("bytes"), f"legacy archive {name}.bytes"
        ):
            raise GateError(f"legacy archive byte size changed: {name}")
        if actual["sha256"] != require_hex(
            record.get("sha256"), f"legacy archive {name}.sha256"
        ):
            raise GateError(f"legacy archive hash changed: {name}")
        expected_source_root = (source / name).resolve()
        if (
            resolved_report_path(
                record.get("source_root"), f"legacy archive {name}.source_root"
            )
            != expected_source_root
        ):
            raise GateError(
                f"legacy archive belongs to a different source root: {name}"
            )
        try:
            current_tree = archive_tool.scan_tree(expected_source_root)
            archived_tree = archive_tool.scan_archive(archive_path)
        except Exception as exc:
            raise GateError(
                f"legacy source/archive scan failed for {name}: {exc}"
            ) from exc
        tree_keys = (
            "directory_count",
            "file_count",
            "bytes",
            "tree_sha256",
            "directories",
            "files",
        )
        if any(current_tree.get(key) != archived_tree.get(key) for key in tree_keys):
            raise GateError(f"legacy archive content is stale for source tree: {name}")
        if (
            require_hex(
                record.get("source_tree_sha256"),
                f"legacy archive {name}.source_tree_sha256",
            )
            != current_tree["tree_sha256"]
        ):
            raise GateError(f"legacy source tree hash changed after archiving: {name}")
        if (
            require_nonnegative_int(
                record.get("source_file_count"),
                f"legacy archive {name}.source_file_count",
            )
            != current_tree["file_count"]
        ):
            raise GateError(f"legacy source file count changed after archiving: {name}")
        if (
            require_nonnegative_int(
                record.get("source_bytes"), f"legacy archive {name}.source_bytes"
            )
            != current_tree["bytes"]
        ):
            raise GateError(f"legacy source byte count changed after archiving: {name}")
        archive_summaries[name] = {
            **actual,
            "source_root": str(expected_source_root),
            "source_file_count": current_tree["file_count"],
            "source_bytes": current_tree["bytes"],
            "source_tree_sha256": current_tree["tree_sha256"],
        }
    return {
        "status": "PASS",
        "marker": str(path.resolve()),
        "marker_sha256": marker_digest,
        "decision": value["decision"],
        "audit_report": str(audit_path),
        "audit_report_sha256": audit_digest,
        "archives": archive_summaries,
    }


def _validate_check_list(value: object, category: str) -> list[str]:
    checks = value
    if not isinstance(checks, list) or not checks:
        raise GateError(f"{category} report must contain a non-empty checks list")
    names: set[str] = set()
    for index, check in enumerate(checks):
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("name"), str)
            or not check["name"]
            or check.get("status") != "PASS"
            or check["name"] in names
        ):
            raise GateError(
                f"{category}.checks[{index}] is invalid, duplicated, or not PASS"
            )
        names.add(check["name"])
    return sorted(names)


def validate_integration_report(
    path: Path,
    source: Path,
    staging: Path,
    target: Path,
    bundle_sha256: str,
) -> dict[str, Any]:
    verifier = _load_tool(
        "verify_integration_acceptance.py", "final_gate_integration_acceptance"
    )
    try:
        bound_result, bound_code = verifier.validate_bound_report(
            path, source, staging, target, bundle_sha256
        )
    except Exception as exc:
        raise GateError(f"integration bound report revalidation failed: {exc}") from exc
    if bound_code != 0 or bound_result.get("status") != "VERIFIED_PASS":
        raise GateError("integration bound report did not revalidate to VERIFIED_PASS")

    value, digest = read_json(path, "integration PASS report")
    bound_report = bound_result.get("report")
    if (
        not isinstance(bound_report, dict)
        or require_hex(bound_report.get("sha256"), "bound integration report sha256")
        != digest
    ):
        raise GateError("integration report changed after bound evidence revalidation")
    if value.get("schema") != 1 or value.get("status") != "PASS":
        raise GateError("integration report status must be exactly PASS")
    if value.get("category") != "integration":
        raise GateError("integration report has the wrong category")
    if value.get("blockers") != []:
        raise GateError("integration report blockers must be explicitly empty")
    if (
        resolved_report_path(
            value.get("target_game_dir"), "integration.target_game_dir"
        )
        != target.resolve()
    ):
        raise GateError("integration report belongs to a different target")
    report_bundle = require_hex(
        value.get("runtime_bundle_sha256"), "integration.runtime_bundle_sha256"
    )
    if report_bundle != bundle_sha256.upper():
        raise GateError("integration report belongs to a different runtime bundle")
    checks = value.get("checks")
    names = set(_validate_check_list(checks, "integration"))
    if names != REQUIRED_INTEGRATION_CHECKS:
        missing = REQUIRED_INTEGRATION_CHECKS - names
        unexpected = names - REQUIRED_INTEGRATION_CHECKS
        details = []
        if missing:
            details.append("missing=" + ",".join(sorted(missing)))
        if unexpected:
            details.append("unexpected=" + ",".join(sorted(unexpected)))
        raise GateError("integration checks are incomplete: " + "; ".join(details))

    evidence: dict[str, Any] = {}
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        name = check["name"]
        if (
            resolved_report_path(
                check.get("target_game_dir"), f"integration.{name}.target_game_dir"
            )
            != target.resolve()
        ):
            raise GateError(f"integration check belongs to a different target: {name}")
        if (
            require_hex(
                check.get("runtime_bundle_sha256"),
                f"integration.{name}.runtime_bundle_sha256",
            )
            != bundle_sha256.upper()
        ):
            raise GateError(
                f"integration check belongs to a different runtime bundle: {name}"
            )
        artifact = check.get("artifact")
        if not isinstance(artifact, dict):
            raise GateError(f"integration check has no bound artifact: {name}")
        artifact_path = resolved_report_path(
            artifact.get("path"), f"integration.{name}.artifact.path"
        )
        if any(
            path_is_within(artifact_path, protected)
            for protected in (source, staging, target)
        ):
            raise GateError(
                f"integration evidence must be outside protected trees: {name}"
            )
        current = stable_file_summary(artifact_path, f"integration evidence {name}")
        if current["bytes"] != require_nonnegative_int(
            artifact.get("bytes"), f"integration.{name}.artifact.bytes"
        ):
            raise GateError(f"integration evidence byte size changed: {name}")
        if current["sha256"] != require_hex(
            artifact.get("sha256"), f"integration.{name}.artifact.sha256"
        ):
            raise GateError(f"integration evidence hash changed: {name}")
        evidence[name] = current
    return {
        "path": str(path.resolve()),
        "sha256": digest,
        "checks": sorted(names),
        "evidence": evidence,
        "bound_revalidation": bound_result,
    }


def validate_client_report(path: Path, server_bundle_sha256: str) -> dict[str, Any]:
    value, digest = read_json(path, "client acceptance report")
    if value.get("schema") != 1 or value.get("status") != "PRODUCTION_CLIENT_GO":
        raise GateError("client report must be PRODUCTION_CLIENT_GO")
    if value.get("exit_code") != 0:
        raise GateError("client report exit_code must be zero")
    if (
        require_hex(value.get("server_bundle_sha256"), "client.server_bundle_sha256")
        != server_bundle_sha256.upper()
    ):
        raise GateError("client report belongs to a different server bundle")
    verifier = _load_tool("verify_client_acceptance.py", "final_gate_client_acceptance")
    required = set(verifier.REQUIRED_SCENARIOS)
    suites = value.get("manual_suites_closed")
    if not isinstance(suites, list) or set(suites) != required:
        raise GateError("client report does not close the required client suites")

    recorded_bundle = value.get("bundle")
    if not isinstance(recorded_bundle, dict):
        raise GateError("client report is missing its bundle summary")
    mods_dir = resolved_report_path(
        recorded_bundle.get("mods_dir"), "client.bundle.mods_dir"
    )
    manifest = resolved_report_path(
        recorded_bundle.get("manifest"), "client.bundle.manifest"
    )
    try:
        current_bundle = verifier.validate_bundle(mods_dir, manifest)
    except Exception as exc:
        raise GateError(f"client bundle revalidation failed: {exc}") from exc
    if current_bundle != recorded_bundle:
        raise GateError("client bundle changed after the client gate report")

    recorded_evidence = value.get("evidence")
    if not isinstance(recorded_evidence, dict):
        raise GateError("client report is missing bound suite evidence")
    evidence_path = resolved_report_path(
        recorded_evidence.get("evidence"), "client.evidence.evidence"
    )
    evidence_root = resolved_report_path(
        recorded_evidence.get("evidence_root"), "client.evidence.evidence_root"
    )
    evidence_before = stable_file_summary(evidence_path, "client evidence")
    if evidence_before["sha256"] != require_hex(
        recorded_evidence.get("evidence_sha256"), "client.evidence.evidence_sha256"
    ):
        raise GateError("client evidence hash changed after the client gate report")
    try:
        current_evidence = verifier.validate_evidence(
            evidence_path,
            evidence_root,
            current_bundle,
            server_bundle_sha256.upper(),
        )
    except Exception as exc:
        raise GateError(f"client evidence suite revalidation failed: {exc}") from exc
    if current_evidence != recorded_evidence:
        raise GateError("client evidence summary changed after the client gate report")
    if stable_file_summary(evidence_path, "client evidence") != evidence_before:
        raise GateError("client evidence changed while the final release gate ran")
    return {
        "path": str(path.resolve()),
        "sha256": digest,
        "status": value["status"],
        "server_bundle_sha256": server_bundle_sha256.upper(),
        "client_bundle_sha256": current_bundle["bundle_sha256"],
        "suites": sorted(required),
        "evidence_sha256": evidence_before["sha256"],
    }


def validate_auth_report(
    path: Path, staging: Path, target: Path, mods: Path
) -> dict[str, Any]:
    value, digest = read_json(path, "auth readiness report")
    if value.get("schema") != 1 or value.get("status") != "READY_AUTH_CUTOVER":
        raise GateError("auth report must be READY_AUTH_CUTOVER")
    if value.get("exit_code") != 0:
        raise GateError("auth report exit_code must be zero")
    accounts = value.get("accounts")
    if not isinstance(accounts, dict) or accounts.get("records", 0) <= 0:
        raise GateError("auth report has no account summary")
    if accounts.get("plaintext_stored") is not False:
        raise GateError("auth report does not prove plaintext_passwords=false")
    idem = value.get("idempotence")
    if (
        not isinstance(idem, dict)
        or not all(
            idem.get(key) is True
            for key in (
                "hashes_equal",
                "manifest_summaries_equal",
                "output_matches_converter",
            )
        )
        or idem.get("passes") != 2
    ):
        raise GateError("auth report idempotence is incomplete")
    live = value.get("live_login")
    if (
        not isinstance(live, dict)
        or live.get("status") != "PASS"
        or live.get("evidence_bound") is not True
    ):
        raise GateError("auth live login matrix is not PASS")
    if set(live.get("required_scenarios", [])) != REQUIRED_AUTH_SCENARIOS:
        raise GateError("auth live login scenarios are incomplete")

    source_summary = value.get("source")
    source_path = (staging / "migration-input/EasyAuth/easyauth.db").resolve()
    if not isinstance(source_summary, dict):
        raise GateError("auth source summary is missing")
    source_file_label = str(source_summary.get("file", "")).replace("\\", "/")
    if not source_file_label.endswith("migration-input/EasyAuth/easyauth.db"):
        raise GateError("auth report is not bound to the staged EasyAuth snapshot")
    if (
        source_summary.get("read_only") is not True
        or source_summary.get("unchanged_during_gate") is not True
    ):
        raise GateError(
            "auth report does not prove the source was read-only and unchanged"
        )
    current_source = stable_file_summary(source_path, "staged EasyAuth source")
    if current_source["bytes"] != source_summary.get("bytes") or current_source[
        "sha256"
    ] != require_hex(source_summary.get("sha256"), "auth.source.sha256"):
        raise GateError("staged EasyAuth source changed after the auth gate")

    output = value.get("output")
    if not isinstance(output, dict):
        raise GateError("auth output summary is missing")
    if str(output.get("file", "")).replace("\\", "/") != "world/xiyus_player_data.json":
        raise GateError("auth output path is not world/xiyus_player_data.json")
    if output.get("semantics_match_source") is not True:
        raise GateError("auth report does not prove output semantics match source")
    output_path = (target / "world/xiyus_player_data.json").resolve()
    current_output = stable_file_summary(output_path, "target XiyusLogin output")
    if current_output["bytes"] != output.get("bytes") or current_output[
        "sha256"
    ] != require_hex(output.get("sha256"), "auth.output.sha256"):
        raise GateError("target XiyusLogin output changed after the auth gate")

    jar = value.get("candidate_jar")
    if not isinstance(jar, dict):
        raise GateError("auth candidate JAR summary is missing")
    runtime_rows = [
        row
        for row in scan_target_mods(mods)["files"]
        if "xiyuslogin" in row["file"].lower()
    ]
    if len(runtime_rows) != 1:
        raise GateError("expected exactly one runtime XiyusLogin JAR")
    runtime_jar = runtime_rows[0]
    jar_hash = require_hex(jar.get("sha256"), "auth.candidate_jar.sha256")
    if (
        jar_hash != runtime_jar["sha256"]
        or jar.get("bytes") != runtime_jar["bytes"]
        or jar.get("file") != runtime_jar["file"]
    ):
        raise GateError("auth report JAR is not the runtime XiyusLogin JAR")

    live_report_path = resolved_report_path(
        live.get("report"), "auth.live_login.report"
    )
    auth_verifier = _load_tool("verify_auth_readiness.py", "final_gate_auth_readiness")
    try:
        current_live = auth_verifier.validate_live_report(
            live_report_path,
            current_source["sha256"],
            current_output["sha256"],
            jar_hash,
        )
    except Exception as exc:
        raise GateError(f"auth live login evidence revalidation failed: {exc}") from exc
    if current_live != live:
        raise GateError("auth live login evidence changed after the auth gate report")
    live_digest = current_live["report_sha256"]
    return {
        "path": str(path.resolve()),
        "sha256": digest,
        "status": value["status"],
        "records": accounts["records"],
        "live_scenarios": sorted(REQUIRED_AUTH_SCENARIOS),
        "source_sha256": current_source["sha256"],
        "output_sha256": current_output["sha256"],
        "candidate_jar_sha256": jar_hash,
        "live_evidence_sha256": live_digest,
        "scenario_evidence": current_live["scenario_evidence"],
    }


def validate_required_reports(
    paths: list[Path],
    category: str,
    source: Path,
    target: Path,
    staging: Path,
    mods: Path,
    bundle_sha256: str,
) -> dict[str, Any]:
    if not paths:
        raise GateError(f"at least one --{category}-report is required")
    if category in {"client", "auth"} and len(paths) != 1:
        raise GateError(f"exactly one --{category}-report is required")
    if not isinstance(bundle_sha256, str):
        raise GateError("runtime bundle digest is required before category reports")
    if category == "client":
        reports = [validate_client_report(paths[0], bundle_sha256)]
    elif category == "auth":
        reports = [validate_auth_report(paths[0], staging, target, mods)]
    else:
        reports = [
            validate_integration_report(path, source, staging, target, bundle_sha256)
            for path in paths
        ]
    return {
        "status": "PASS",
        "reports": reports,
    }


def evaluate_release(args: argparse.Namespace) -> dict[str, Any]:
    gates: dict[str, Any] = {}
    blockers: list[str] = []

    def check(name: str, function: Callable[[], dict[str, Any]]) -> None:
        try:
            gates[name] = function()
        except Exception as exc:  # noqa: BLE001 - every gate must fail closed
            gates[name] = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
            blockers.append(f"{name}: {type(exc).__name__}: {exc}")

    required_paths = {
        "source_game_dir": args.source_game_dir,
        "staging_game_dir": args.staging_game_dir,
        "baseline_manifest": args.baseline_manifest,
        "conversion_marker": args.conversion_marker,
        "chunks_report": args.chunks_report,
        "target_game_dir": args.target_game_dir,
        "target_mods_dir": args.target_mods_dir,
        "assembly_report": args.assembly_report,
        "sanitizer_report": args.sanitizer_report,
        "legacy_policy_marker": args.legacy_policy_marker,
    }
    missing = sorted(name for name, value in required_paths.items() if value is None)
    if missing:
        blockers.append("missing required input(s): " + ", ".join(missing))
        gates["required_inputs"] = {"status": "FAIL", "missing": missing}
        return {
            "schema": SCHEMA_VERSION,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": NO_GO,
            "exit_code": 2,
            "read_only": True,
            "gates": gates,
            "blockers": blockers,
        }

    source = args.source_game_dir.resolve()
    staging = args.staging_game_dir.resolve()
    target = args.target_game_dir.resolve()
    mods = args.target_mods_dir.resolve()
    source_world = source / "world"
    check(
        "production_assembly",
        lambda: validate_production_assembly(
            args.assembly_report,
            source,
            staging,
            args.target_game_dir,
            args.sanitizer_report,
        ),
    )
    check("source_session_lock", lambda: validate_source_lock(source_world))
    check(
        "canonical_chunks",
        lambda: validate_chunks_report(args.chunks_report, source_world),
    )
    check(
        "conversion_marker",
        lambda: validate_conversion_marker(
            source, staging, args.baseline_manifest, args.conversion_marker
        ),
    )
    check(
        "target_sanitizer_and_runtime_mods",
        lambda: validate_sanitizer(
            source,
            staging,
            target,
            mods,
            args.sanitizer_report,
            args.expected_runtime_manifest,
        ),
    )
    check(
        "legacy_policy",
        lambda: validate_legacy_policy(
            args.legacy_policy_marker, source, staging, target
        ),
    )

    runtime_gate = gates.get("target_sanitizer_and_runtime_mods", {})
    bundle_sha256 = (
        runtime_gate.get("runtime_mod_manifest", {}).get("bundle_sha256")
        if runtime_gate.get("status") == "PASS"
        else None
    )
    for category in PASS_CATEGORIES:
        paths = list(getattr(args, f"{category}_report") or [])
        check(
            f"{category}_reports",
            lambda paths=paths, category=category: (
                validate_required_reports(
                    paths, category, source, target, staging, mods, bundle_sha256
                )
                if isinstance(bundle_sha256, str)
                else (_ for _ in ()).throw(
                    GateError(
                        "runtime manifest gate must pass before PASS reports can be bound"
                    )
                )
            ),
        )

    status = READY if not blockers else NO_GO
    return {
        "schema": SCHEMA_VERSION,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "exit_code": 0 if status == READY else 2,
        "read_only": True,
        "source_game_dir": str(source),
        "staging_game_dir": str(staging),
        "target_game_dir": str(target),
        "gates": gates,
        "blockers": blockers,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-game-dir", type=Path)
    parser.add_argument("--staging-game-dir", type=Path)
    parser.add_argument("--baseline-manifest", type=Path)
    parser.add_argument("--conversion-marker", type=Path)
    parser.add_argument("--chunks-report", type=Path)
    parser.add_argument("--target-game-dir", type=Path)
    parser.add_argument("--target-mods-dir", type=Path)
    parser.add_argument("--assembly-report", type=Path)
    parser.add_argument("--sanitizer-report", type=Path)
    parser.add_argument("--expected-runtime-manifest", type=Path)
    parser.add_argument("--legacy-policy-marker", type=Path)
    parser.add_argument(
        "--client-report",
        "--client-acceptance-report",
        dest="client_report",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--auth-report",
        "--auth-readiness-report",
        dest="auth_report",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--integration-report",
        "--integration-acceptance-report",
        dest="integration_report",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="optional output outside source, staging, and target; stdout is always emitted",
    )
    return parser.parse_args(argv)


def _input_report_paths(args: argparse.Namespace) -> list[Path]:
    paths = [
        args.baseline_manifest,
        args.conversion_marker,
        args.chunks_report,
        args.assembly_report,
        args.sanitizer_report,
        args.expected_runtime_manifest,
        args.legacy_policy_marker,
        *args.client_report,
        *args.auth_report,
        *args.integration_report,
    ]
    return [path.resolve() for path in paths if path is not None]


def write_gate_report(
    path: Path, report: dict[str, Any], args: argparse.Namespace
) -> None:
    destination = path.resolve()
    protected = [
        root.resolve()
        for root in (args.source_game_dir, args.staging_game_dir, args.target_game_dir)
        if root is not None
    ]
    if any(path_is_within(destination, root) for root in protected):
        raise GateError("--report must be outside source, staging, and target")
    if destination in _input_report_paths(args):
        raise GateError("--report must not overwrite an input evidence file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = evaluate_release(args)
    if args.report is not None:
        report["report"] = str(args.report.resolve())
        try:
            write_gate_report(args.report, report, args)
        except Exception as exc:  # noqa: BLE001 - report errors are release blockers
            report["status"] = NO_GO
            report["exit_code"] = 2
            blocker = f"report_output: {type(exc).__name__}: {exc}"
            report["blockers"].append(blocker)
            report["gates"]["report_output"] = {
                "status": "FAIL",
                "error": blocker,
            }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
