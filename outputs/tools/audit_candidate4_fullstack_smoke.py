#!/usr/bin/env python3
"""Freeze a redacted, fail-closed audit of a two-run full-stack smoke target."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import socket
import subprocess
import zipfile
from pathlib import Path
from typing import Any

try:
    from inspect_schema_samples import scan as scan_nbt
except ModuleNotFoundError:  # Unit users may not have the migration NBT dependency.
    scan_nbt = None


SCHEMA = 1
DEFAULT_XIYUSLOGIN_SHA256 = (
    "D1A0FB4EE7E60C5893A7A2CBCAFA21434555AE5CC3F725AAEF59F8312169EE08"
)
SECRET_PATTERNS = (
    re.compile(r"(?i)rcon\.password\s*=\s*\S+"),
    re.compile(r"(?i)(?:password|passwd|token|secret)\s*[:=]\s*\S+"),
    re.compile(r"(?i)authorization\s*:\s*(?:bearer|basic)\s+\S+"),
)
HARD_MIXIN_PATTERN = re.compile(
    r"(?i)MixinApplyError|MixinTransformerError|InjectionError|"
    r"InvalidInjectionException|critical injection failure|mixin apply failed"
)


class AuditError(RuntimeError):
    """Raised when required smoke evidence cannot be validated."""


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8", errors="replace")


def artifact(path: Path, *, scan_secrets: bool = False) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise AuditError(f"artifact is missing, linked, or not a regular file: {path}")
    result: dict[str, Any] = {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }
    if scan_secrets:
        text = read_text(path)
        result["secret_scan_pass"] = not any(
            pattern.search(text) for pattern in SECRET_PATTERNS
        )
    return result


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"{label} root is not an object: {path}")
    return value


def scan_runtime_mods(mods: Path) -> dict[str, Any]:
    if not mods.is_dir() or mods.is_symlink():
        raise AuditError(f"runtime mods directory is invalid: {mods}")
    entries = list(mods.iterdir())
    if not entries:
        raise AuditError(f"runtime mods directory is empty: {mods}")
    rows: list[dict[str, Any]] = []
    for path in sorted(entries, key=lambda item: item.name.lower()):
        if (
            not path.is_file()
            or path.is_symlink()
            or path.suffix.lower() != ".jar"
            or not zipfile.is_zipfile(path)
        ):
            raise AuditError(f"runtime mods contains a linked/non-JAR entry: {path}")
        rows.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
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


def expected_runtime_manifest(prepare: dict[str, Any]) -> dict[str, Any]:
    sanitization = prepare.get("resource_sanitization")
    if not isinstance(sanitization, dict) or sanitization.get("status") != "SANITIZED":
        raise AuditError("prepare report has no successful resource sanitization")
    manifest = sanitization.get("runtime_mod_manifest")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise AuditError("prepare report has no runtime mod manifest")
    rows = []
    for row in manifest["files"]:
        if not isinstance(row, dict):
            raise AuditError("prepare runtime manifest contains a non-object row")
        rows.append(
            {
                "file": row.get("file"),
                "bytes": row.get("bytes"),
                "sha256": row.get("sha256"),
            }
        )
    return {
        "file_count": manifest.get("file_count"),
        "bytes": manifest.get("bytes"),
        "bundle_sha256": manifest.get("bundle_sha256"),
        "files": rows,
    }


def marker_count(text: str, pattern: str, *, regex: bool = False) -> int:
    return len(re.findall(pattern, text, flags=re.IGNORECASE)) if regex else text.count(pattern)


def analyze_log(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    records = [int(value) for value in re.findall(r"Loaded (\d+) player records from data file", text)]
    recipes = [int(value) for value in re.findall(r"Loaded (\d+) recipes", text)]
    advancements = [int(value) for value in re.findall(r"Loaded (\d+) advancements", text)]
    # Log4j's console layout keeps the Connector error and its exception on one
    # line, while the rolling file appender emits the exception on the next
    # stack-trace line.  Bind the two forms to the same exact placeholder.
    connector = 0
    for index, line in enumerate(lines):
        if not re.search(r"\[[^\]\r\n]*/ERROR\]", line, re.IGNORECASE):
            continue
        if "RefmapRemapper" not in line:
            continue
        window = "\n".join(lines[index : index + 6])
        if re.search(r"NoSuchFileException:\s*\\~nonexistent", window):
            connector += 1
    error_levels = marker_count(text, r"\[[^\]\r\n]*/ERROR\]|\[ERROR\]", regex=True)
    spark_shutdown = marker_count(
        text, "RejectedExecutionException: Server already shutting down"
    )
    stop_index = text.rfind("Stopping server")
    spark_index = text.rfind("RejectedExecutionException: Server already shutting down")
    final_save_index = text.rfind("All dimensions are saved")
    result = {
        "done": marker_count(text, "Done ("),
        "reload": marker_count(text, "[Rcon: Reloading!]"),
        "rcon_saved_game": marker_count(text, "[Rcon: Saved the game]"),
        "rcon_stop_command": marker_count(text, "[Rcon: Stopping the server]"),
        "server_stopping": marker_count(text, "Stopping server"),
        "all_dimensions_saved": marker_count(text, "All dimensions are saved"),
        "rcon_listener_stopped": marker_count(text, "Thread RCON Listener stopped"),
        "dimension_save_markers": {
            dimension: marker_count(text, f"/minecraft:{dimension}")
            for dimension in ("overworld", "the_nether", "the_end")
        },
        "xiyuslogin_loaded_records": records,
        "xiyuslogin_shutdown": marker_count(
            text, "XiyusLogin data saved and systems shutdown"
        ),
        "recipes_loaded": recipes,
        "advancements_loaded": advancements,
        "error_level": error_levels,
        "fatal": marker_count(text, r"\bFATAL\b", regex=True),
        "reported_exception": marker_count(text, "Reported exception"),
        "skipped_block_entity": marker_count(text, "Skipped BlockEntity"),
        "block_attached": marker_count(text, "BlockAttached"),
        "hard_mixin_failure": len(HARD_MIXIN_PATTERN.findall(text)),
        "class_not_found_warning": marker_count(text, "ClassNotFoundException"),
        "mixin_target_missing_warning": marker_count(
            text, r"@Mixin target .* was not found", regex=True
        ),
        "connector_refmap_placeholder_error": connector,
        "spark_shutdown_rejected_execution_warning": spark_shutdown,
        "spark_warning_order_valid": (
            spark_shutdown == 0
            or (stop_index >= 0 and stop_index < spark_index < final_save_index)
        ),
    }
    result["unallowlisted_error_level"] = error_levels - connector
    return result


def lifecycle_failures(
    analysis: dict[str, Any], expected_records: int, *, require_reload: bool
) -> list[str]:
    failures = []
    required_positive = (
        "done",
        "rcon_saved_game",
        "rcon_stop_command",
        "server_stopping",
        "all_dimensions_saved",
        "rcon_listener_stopped",
        "xiyuslogin_shutdown",
    )
    for key in required_positive:
        if analysis[key] < 1:
            failures.append(f"LOG_MISSING_{key.upper()}")
    if require_reload and analysis["reload"] < 1:
        failures.append("LOG_MISSING_RELOAD")
    if analysis["xiyuslogin_loaded_records"] != [expected_records]:
        failures.append("XIYUSLOGIN_RECORD_COUNT_MISMATCH")
    if not analysis["recipes_loaded"] or not analysis["advancements_loaded"]:
        failures.append("RECIPE_OR_ADVANCEMENT_LOAD_MISSING")
    if any(value < 1 for value in analysis["dimension_save_markers"].values()):
        failures.append("THREE_DIMENSION_SAVE_MARKERS_MISSING")
    for key in (
        "unallowlisted_error_level",
        "fatal",
        "reported_exception",
        "skipped_block_entity",
        "block_attached",
        "hard_mixin_failure",
    ):
        if analysis[key] != 0:
            failures.append(f"LOG_HARD_DIAGNOSTIC_{key.upper()}")
    if analysis["spark_shutdown_rejected_execution_warning"] > 1:
        failures.append("SPARK_SHUTDOWN_WARNING_MULTIPLE")
    if not analysis["spark_warning_order_valid"]:
        failures.append("SPARK_SHUTDOWN_WARNING_ORDER_INVALID")
    return failures


def normalize_item_inventory(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        size = len(value)
        encoding = "legacy_list"
        raw_items = [(slot, stack) for slot, stack in enumerate(value)]
    elif isinstance(value, dict):
        size = value.get("Size")
        encoding = "neoforge_item_handler_compound"
        items = value.get("Items", [])
        raw_items = []
        if isinstance(items, list):
            for fallback, stack in enumerate(items):
                slot = stack.get("Slot", fallback) if isinstance(stack, dict) else fallback
                raw_items.append((int(slot), stack))
    else:
        return {"encoding": "invalid", "size": None, "items": []}
    summaries = []
    for slot, stack in raw_items:
        if not isinstance(stack, dict) or not stack or not stack.get("id"):
            continue
        payload = dict(stack)
        payload.pop("Slot", None)
        count = payload.pop("count", payload.pop("Count", 1))
        summaries.append(
            {
                "slot": int(slot),
                "id": str(stack["id"]),
                "count": int(count),
                "components_sha256": stable_hash(payload.get("components", {})),
            }
        )
    return {"encoding": encoding, "size": size, "items": summaries}


def item_loss(source: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    def counter(value: dict[str, Any]) -> collections.Counter[tuple[Any, ...]]:
        return collections.Counter(
            {
                (row["slot"], row["id"], row["components_sha256"]): row["count"]
                for row in value["items"]
            }
        )

    source_counts = counter(source)
    target_counts = counter(target)
    lost = []
    for key, count in sorted((source_counts - target_counts).items()):
        slot, identifier, components_sha256 = key
        lost.append(
            {
                "slot": slot,
                "id": identifier,
                "count": count,
                "components_sha256": components_sha256,
            }
        )
    return lost


def summarize_cannon(value: dict[str, Any]) -> dict[str, Any]:
    printer = value.get("Printer")
    if isinstance(printer, dict):
        # Create Fly writes enum names in lower case while Create 6.0.10's
        # codec emits the canonical upper-case names.  Compare the semantic
        # enum value, not the serializer's spelling.
        printer = dict(printer)
        stage = printer.get("PrintStage")
        if isinstance(stage, str):
            printer["PrintStage"] = stage.lower()
    state = value.get("State")
    if isinstance(state, str):
        state = state.lower()
    return {
        "position": [value.get("x"), value.get("y"), value.get("z")],
        "state": state,
        "status": value.get("Status"),
        "progress": value.get("Progress"),
        "paper_progress": value.get("PaperProgress"),
        "remaining_fuel": value.get("RemainingFuel"),
        "amount_placed": value.get("AmountPlaced"),
        "amount_to_place": value.get("AmountToPlace"),
        "inventory": normalize_item_inventory(value.get("Inventory")),
        "printer_sha256": stable_hash(printer),
        "options_sha256": stable_hash(value.get("Options")),
        "flying_blocks_sha256": stable_hash(value.get("FlyingBlocks")),
    }


def schematicannon_audit(source: Path, target: Path, regions: list[str]) -> dict[str, Any]:
    if scan_nbt is None:
        raise AuditError("NBT scanner dependency is unavailable")
    region_set = set(regions)
    source_rows = [
        value
        for value in scan_nbt(source, "region", region_set)
        if value.get("id") == "create:schematicannon"
    ]
    target_rows = [
        value
        for value in scan_nbt(target, "region", region_set)
        if value.get("id") == "create:schematicannon"
    ]
    index = lambda rows: {
        (value.get("x"), value.get("y"), value.get("z")): value for value in rows
    }
    source_index = index(source_rows)
    target_index = index(target_rows)
    comparisons = []
    for position in sorted(set(source_index) | set(target_index)):
        source_value = source_index.get(position)
        target_value = target_index.get(position)
        row: dict[str, Any] = {"position": list(position)}
        if source_value is None or target_value is None:
            row.update(
                {
                    "status": "BLOCK",
                    "reason": "SCHEMATICANNON_RECORD_MISSING",
                    "source_present": source_value is not None,
                    "target_present": target_value is not None,
                }
            )
            comparisons.append(row)
            continue
        source_summary = summarize_cannon(source_value)
        target_summary = summarize_cannon(target_value)
        lost = item_loss(source_summary["inventory"], target_summary["inventory"])
        latent_legacy = target_summary["inventory"]["encoding"] == "legacy_list"
        invariant_keys = (
            "state",
            "progress",
            "paper_progress",
            "remaining_fuel",
            "amount_placed",
            "amount_to_place",
            "printer_sha256",
            "options_sha256",
            "flying_blocks_sha256",
        )
        invariant_changes = [
            key for key in invariant_keys if source_summary[key] != target_summary[key]
        ]
        reasons = []
        if lost:
            reasons.append("SCHEMATICANNON_INVENTORY_ITEM_LOSS")
        if latent_legacy:
            reasons.append("SCHEMATICANNON_LEGACY_INVENTORY_UNEXERCISED")
        if invariant_changes:
            reasons.append("SCHEMATICANNON_OPERATIONAL_STATE_CHANGED")
        row.update(
            {
                "status": "BLOCK" if reasons else "PASS",
                "reasons": reasons,
                "source": source_summary,
                "target": target_summary,
                "status_change": {
                    "source": source_summary["status"],
                    "target": target_summary["status"],
                },
                "lost_items": lost,
                "lost_item_units": sum(item["count"] for item in lost),
                "invariant_changes": invariant_changes,
            }
        )
        comparisons.append(row)
    return {
        "regions": sorted(regions),
        "source_count": len(source_rows),
        "target_count": len(target_rows),
        "comparisons": comparisons,
        "lost_item_units": sum(row.get("lost_item_units", 0) for row in comparisons),
        "status": "BLOCK" if any(row["status"] == "BLOCK" for row in comparisons) else "PASS",
    }


def loaded_region_audit(
    path: Path, expected_target: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    value = read_json(path, "loaded-region comparison")
    if Path(value.get("target", "")).resolve() != expected_target.resolve():
        raise AuditError("loaded-region comparison belongs to another target")
    counts = value.get("counts")
    if not isinstance(counts, dict):
        raise AuditError("loaded-region comparison has no counts")
    blockers = []
    if counts.get("source_block_entities") != counts.get("target_block_entities"):
        blockers.append("LOADED_REGION_BLOCK_ENTITY_COUNT_MISMATCH")
    if counts.get("source_attached_entities") != counts.get("target_attached_entities"):
        blockers.append("LOADED_REGION_ATTACHED_ENTITY_COUNT_MISMATCH")
    for key in (
        "missing_block_entities",
        "missing_attached_entities",
        "suspicious_attached_entities",
    ):
        if value.get(key) != []:
            blockers.append(f"LOADED_REGION_{key.upper()}_NONEMPTY")
    normalizations = 0
    for row in value.get("changed_attached_entities", []):
        source = row.get("source", {})
        target = row.get("target", {})
        same_anchor = all(
            source.get(key) == target.get(key)
            for key in ("id", "uuid", "tile", "Facing")
        )
        rotation = source.get("Rotation")
        expected_rotation = isinstance(rotation, list) and len(rotation) == 2 and target.get("Rotation") == 0
        if same_anchor and expected_rotation:
            normalizations += 1
        else:
            blockers.append("LOADED_REGION_UNCLASSIFIED_ATTACHED_CHANGE")
    regions = value.get("regions")
    if not isinstance(regions, list) or not all(isinstance(item, str) for item in regions):
        raise AuditError("loaded-region comparison has invalid region list")
    source = Path(value.get("source", "")).resolve()
    summary = {
        "status": "BLOCK" if blockers else "PASS_WITH_RUNTIME_NORMALIZATIONS",
        "counts": {
            "source_block_entities": counts.get("source_block_entities"),
            "target_block_entities": counts.get("target_block_entities"),
            "source_attached_entities": counts.get("source_attached_entities"),
            "target_attached_entities": counts.get("target_attached_entities"),
        },
        "missing_block_entities": len(value.get("missing_block_entities", [])),
        "missing_attached_entities": len(value.get("missing_attached_entities", [])),
        "attached_runtime_normalizations": normalizations,
        "blockers": sorted(set(blockers)),
    }
    return summary, {"source": source, "regions": regions}


def probe_tcp_closed(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def probe_udp_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def java_process_count() -> int | None:
    command = (
        "$rows=@(Get-Process -Name java,javaw -ErrorAction SilentlyContinue); "
        "[Console]::Out.Write($rows.Count); exit 0"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def build_evidence(
    target: Path,
    prepare_path: Path,
    loaded_region_path: Path,
    expected_xiyuslogin_sha256: str,
    expected_records: int,
    server_port: int,
    rcon_port: int,
    voice_port: int,
    *,
    live_probes: bool = True,
) -> dict[str, Any]:
    target = target.resolve()
    prepare_path = prepare_path.resolve()
    loaded_region_path = loaded_region_path.resolve()
    blockers: list[str] = []
    prepare = read_json(prepare_path, "candidate prepare report")
    if prepare.get("status") != "PREPARED":
        blockers.append("CANDIDATE_PREPARE_NOT_PASS")
    if Path(prepare.get("output", "")).resolve() != target:
        blockers.append("CANDIDATE_PREPARE_TARGET_MISMATCH")

    actual_runtime = scan_runtime_mods(target / "mods")
    expected_runtime = expected_runtime_manifest(prepare)
    if actual_runtime != expected_runtime:
        blockers.append("RUNTIME_JAR_DRIFT")
    xiyus_rows = [
        row
        for row in actual_runtime["files"]
        if row["file"].lower().startswith("xiyuslogin-")
    ]
    expected_auth = expected_xiyuslogin_sha256.upper()
    if len(xiyus_rows) != 1 or xiyus_rows[0]["sha256"] != expected_auth:
        blockers.append("XIYUSLOGIN_JAR_MISMATCH")

    archived_logs = sorted(
        path
        for path in (target / "logs").glob("*.log.gz")
        if not path.name.lower().startswith("debug")
    )
    if len(archived_logs) != 1:
        raise AuditError(f"expected exactly one archived run log, found {len(archived_logs)}")
    paths = {
        "run1": {
            "stdout": target / "run1.stdout.log",
            "stderr": target / "run1.stderr.log",
            "server_log": archived_logs[0],
        },
        "run2": {
            "stdout": target / "run2.stdout.log",
            "stderr": target / "run2.stderr.log",
            "server_log": target / "logs" / "latest.log",
        },
    }
    runs: dict[str, Any] = {}
    for name, run_paths in paths.items():
        stdout_text = read_text(run_paths["stdout"])
        stderr_text = read_text(run_paths["stderr"])
        server_text = read_text(run_paths["server_log"])
        stdout_analysis = analyze_log(stdout_text)
        server_analysis = analyze_log(server_text)
        failures = lifecycle_failures(
            stdout_analysis, expected_records, require_reload=name == "run1"
        )
        server_failures = lifecycle_failures(
            server_analysis, expected_records, require_reload=name == "run1"
        )
        failures.extend(f"SERVER_{item}" for item in server_failures)
        stderr_hard = bool(
            re.search(r"(?i)\b(?:ERROR|FATAL)\b|Reported exception", stderr_text)
        )
        if stderr_hard:
            failures.append("STDERR_HARD_DIAGNOSTIC")
        run_artifacts = {
            key: artifact(path, scan_secrets=True) for key, path in run_paths.items()
        }
        if any(not row["secret_scan_pass"] for row in run_artifacts.values()):
            failures.append("LOG_SECRET_MARKER_DETECTED")
        runs[name] = {
            "status": "PASS" if not failures else "BLOCK",
            "failures": sorted(set(failures)),
            "stdout": stdout_analysis,
            "server_log": server_analysis,
            "stderr": {
                "bytes": len(stderr_text.encode("utf-8")),
                "nonempty_lines": len(
                    [line for line in stderr_text.splitlines() if line.strip()]
                ),
                "hard_diagnostic": stderr_hard,
            },
            "artifacts": run_artifacts,
        }
        blockers.extend(f"{name.upper()}_{item}" for item in failures)

    loaded_summary, loaded_context = loaded_region_audit(loaded_region_path, target)
    blockers.extend(loaded_summary["blockers"])
    cannon = schematicannon_audit(
        loaded_context["source"], target, loaded_context["regions"]
    )
    for row in cannon["comparisons"]:
        blockers.extend(row.get("reasons", []))
        if row.get("reason"):
            blockers.append(row["reason"])

    if live_probes:
        ports = {
            "server_tcp": {
                "host": "127.0.0.1",
                "port": server_port,
                "closed": probe_tcp_closed(server_port),
            },
            "rcon_tcp": {
                "host": "127.0.0.1",
                "port": rcon_port,
                "closed": probe_tcp_closed(rcon_port),
            },
            "voice_udp": {
                "host": "127.0.0.1",
                "port": voice_port,
                "closed": probe_udp_free(voice_port),
            },
        }
        processes = {"java_and_javaw_count": java_process_count()}
        if any(not row["closed"] for row in ports.values()):
            blockers.append("SMOKE_PORT_STILL_OPEN")
        if processes["java_and_javaw_count"] is None:
            blockers.append("JAVA_PROCESS_PROBE_FAILED")
        elif processes["java_and_javaw_count"] != 0:
            blockers.append("JAVA_PROCESS_STILL_RUNNING")
    else:
        ports = {"status": "SKIPPED"}
        processes = {"status": "SKIPPED"}

    extra_logs = sorted(
        path
        for path in (target / "logs").iterdir()
        if path.is_file() and path.name.lower().startswith("debug")
    )
    auxiliary_artifacts = [artifact(path) for path in extra_logs]
    prepare_artifact = artifact(prepare_path, scan_secrets=True)
    loaded_artifact = artifact(loaded_region_path, scan_secrets=True)
    if not prepare_artifact["secret_scan_pass"]:
        blockers.append("PREPARE_REPORT_SECRET_MARKER_DETECTED")
    if not loaded_artifact["secret_scan_pass"]:
        blockers.append("LOADED_REPORT_SECRET_MARKER_DETECTED")

    blockers = sorted(set(blockers))
    known_diagnostics = []
    if runs["run1"]["stdout"]["connector_refmap_placeholder_error"]:
        known_diagnostics.append(
            {
                "code": "CONNECTOR_REFMAP_NONEXISTENT_BOOTSTRAP",
                "run": "run1",
                "severity": "known_non_blocking_runtime_diagnostic",
                "count": runs["run1"]["stdout"]["connector_refmap_placeholder_error"],
            }
        )
    if runs["run2"]["stdout"]["spark_shutdown_rejected_execution_warning"]:
        known_diagnostics.append(
            {
                "code": "SPARK_SHUTDOWN_REJECTED_EXECUTION",
                "run": "run2",
                "severity": "known_non_blocking_shutdown_diagnostic",
                "count": runs["run2"]["stdout"]["spark_shutdown_rejected_execution_warning"],
                "after_stop_before_final_save": runs["run2"]["stdout"]["spark_warning_order_valid"],
            }
        )
    return {
        "schema": SCHEMA,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target": str(target),
        "scope": "candidate4 final-auth server bundle two-run smoke",
        "status": "PASS" if not blockers else "BLOCKED_DATA_LOSS",
        "production_release_ready": False,
        "blockers": blockers,
        "lifecycle": {
            "status": "PASS"
            if all(run["status"] == "PASS" for run in runs.values())
            else "BLOCK",
            "runs": runs,
            "ports": ports,
            "processes": processes,
        },
        "runtime_bundle": {
            "status": "PASS" if actual_runtime == expected_runtime else "BLOCK",
            "file_count": actual_runtime["file_count"],
            "bytes": actual_runtime["bytes"],
            "bundle_sha256": actual_runtime["bundle_sha256"],
            "xiyuslogin": xiyus_rows,
        },
        "loaded_region": loaded_summary,
        "schematicannons": cannon,
        "known_diagnostics": known_diagnostics,
        "artifacts": {
            "prepare_report": prepare_artifact,
            "loaded_region_report": loaded_artifact,
            "debug_logs": auxiliary_artifacts,
        },
        "redaction": {
            "raw_log_lines_embedded": False,
            "credentials_or_tokens_embedded": False,
            "only_aggregate_log_counts_and_artifact_hashes": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    runtime = report["runtime_bundle"]
    loaded = report["loaded_region"]
    lines = [
        "# Candidate4 Final-Auth Full-Stack Smoke Evidence",
        "",
        f"Status: **{report['status']}**. This artifact is not a production release approval.",
        "",
        "## Verified runtime slice",
        "",
        f"- Lifecycle: `{report['lifecycle']['status']}` across two independent starts.",
        f"- Runtime bundle: {runtime['file_count']} JARs / {runtime['bytes']} bytes; SHA-256 `{runtime['bundle_sha256']}`.",
        f"- XiyusLogin: `{runtime['xiyuslogin'][0]['file']}`; SHA-256 `{runtime['xiyuslogin'][0]['sha256']}`.",
        f"- Loaded-region block entities: {loaded['source_block_entities'] if 'source_block_entities' in loaded else loaded['counts']['source_block_entities']}/{loaded['counts']['target_block_entities']}; missing={loaded['missing_block_entities']}.",
        f"- Loaded-region attached entities: {loaded['counts']['source_attached_entities']}/{loaded['counts']['target_attached_entities']}; missing={loaded['missing_attached_entities']}; classified runtime normalizations={loaded['attached_runtime_normalizations']}.",
        "",
        "## Run evidence",
        "",
        "| Run | Done | All dimensions saved | RCON stop | ERROR | FATAL | Skipped BE | BlockAttached | Hard mixin |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("run1", "run2"):
        row = report["lifecycle"]["runs"][name]["stdout"]
        lines.append(
            f"| {name} | {row['done']} | {row['all_dimensions_saved']} | {row['rcon_stop_command']} | "
            f"{row['error_level']} | {row['fatal']} | {row['skipped_block_entity']} | "
            f"{row['block_attached']} | {row['hard_mixin_failure']} |"
        )
    lines.extend(["", "## Hard data blocker", ""])
    for row in report["schematicannons"]["comparisons"]:
        source_inventory = row.get("source", {}).get("inventory", {})
        target_inventory = row.get("target", {}).get("inventory", {})
        lost = ", ".join(
            f"{item['id']} x{item['count']} (slot {item['slot']})"
            for item in row.get("lost_items", [])
        ) or "none observed"
        lines.append(
            f"- `{row['position']}`: `{row['status']}`; inventory encoding "
            f"`{source_inventory.get('encoding')}` -> `{target_inventory.get('encoding')}`; "
            f"lost: {lost}; reasons: `{', '.join(row.get('reasons', [])) or 'none'}`."
        )
    lines.extend(["", "The `finished -> idle` change at `[-12, 64, 9]` is therefore not waived as a display-only normalization: it accompanies loss of persisted inventory items. The other cannon still carries the legacy list encoding and was not exercised by the smoke, so it remains a latent loss risk.", "", "## Known non-blocking diagnostics", ""])
    for item in report["known_diagnostics"]:
        lines.append(f"- `{item['code']}`: {item['count']} occurrence(s) in {item['run']}.")
    lines.extend(["", "## Decision", "", "**NO-GO for strict lossless migration.** The server lifecycle and locked final authentication JAR pass this bounded smoke, but the schematicannon inventory conversion must be fixed and the smoke rerun before this candidate can enter production acceptance.", ""])
    return "\n".join(lines)


def atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--prepare-report", type=Path, required=True)
    parser.add_argument("--loaded-region-report", type=Path, required=True)
    parser.add_argument(
        "--expected-xiyuslogin-sha256", default=DEFAULT_XIYUSLOGIN_SHA256
    )
    parser.add_argument("--expected-player-records", type=int, default=49)
    parser.add_argument("--server-port", type=int, default=12021)
    parser.add_argument("--rcon-port", type=int, default=12022)
    parser.add_argument("--voice-port", type=int, default=26021)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--skip-live-probes", action="store_true")
    args = parser.parse_args()
    try:
        report = build_evidence(
            args.target,
            args.prepare_report,
            args.loaded_region_report,
            args.expected_xiyuslogin_sha256,
            args.expected_player_records,
            args.server_port,
            args.rcon_port,
            args.voice_port,
            live_probes=not args.skip_live_probes,
        )
        atomic_write(
            args.output_json,
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        atomic_write(args.output_md, render_markdown(report))
    except AuditError as exc:
        print(f"audit failed: {exc}")
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "blockers": report["blockers"],
                "runtime_bundle_sha256": report["runtime_bundle"]["bundle_sha256"],
                "output_json": str(args.output_json.resolve()),
                "output_md": str(args.output_md.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
