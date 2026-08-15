#!/usr/bin/env python3
"""Finish the interrupted latest-backup conversion without rescanning regions.

The expensive world conversion has already produced a bound report in the
staging tree.  This detached helper only verifies that report/source baseline,
replays the EasyAuth export with the snapshot's exact row count, restores the
source server.properties bytes into staging, and signs a schema-2 marker.
It never writes the raw source tree and refuses to run against the historical
20260807 backup.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time


WORKSPACE = Path(__file__).resolve().parents[2]
PYTHON = Path(r"C:\Python314\python.exe")
NBT_DEPS = Path(r"D:\Trans\migration-audit-work\poi-nbtdeps")
SOURCE = Path(r"D:\Trans\migration-audit-work\incoming-20260811-raw\20260811")
STAGING = Path(r"D:\Trans\migration-audit-work\cutover-staging-incoming-20260811-candidate13-20260812")
REPORTS = Path(r"D:\Trans\migration-audit-work\cutover-staging-incoming-20260811-candidate13-20260812-reports")
BASELINE = REPORTS / "source-baseline.json"
WORLD_REPORT = REPORTS / "world-convert.json"
AUTH_DB = STAGING / "migration-input" / "EasyAuth" / "easyauth.db"
AUTH_OUTPUT = STAGING / "world" / "xiyus_player_data.json"
AUTH_MANIFEST = REPORTS / "xiyuslogin-migration.json"
AUTH_SNAPSHOT_REPORT = REPORTS / "easyauth-sqlite-resume.json"
FINAL_REPORT = REPORTS / "incoming-20260811-conversion-finalize.json"
MARKER = STAGING / "migration-reports" / "conversion-complete.json"
STATUS = WORKSPACE / "outputs" / "incoming-20260811-finalize.status.json"
STDOUT = WORKSPACE / "outputs" / "incoming-20260811-finalize.stdout.log"
STDERR = WORKSPACE / "outputs" / "incoming-20260811-finalize.stderr.log"
TOOLS = WORKSPACE / "outputs" / "tools"
AUTH_CONVERTER = Path(r"D:\Trans\migration-audit-work\XiyusLogin-migration\tools\migrate_easyauth.py")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return sha256(path)


def load_orchestrator():
    spec = importlib.util.spec_from_file_location("prepare_fast_migration", TOOLS / "prepare_fast_migration.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load prepare_fast_migration.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status(started: float, state: str, phase: str, **extra: object) -> None:
    payload = {
        "schema": 1,
        "status": state,
        "phase": phase,
        "started_at_unix": started,
        "updated_at_unix": time.time(),
        "elapsed_seconds": round(time.time() - started, 3),
        "source": str(SOURCE),
        "staging": str(STAGING),
        "reports": str(REPORTS),
        "world_report": str(WORLD_REPORT),
        "final_report": str(FINAL_REPORT),
        "marker": str(MARKER),
        "source_read_only": True,
        **extra,
    }
    atomic_json(STATUS, payload)


def verify_world_report() -> dict:
    if not WORLD_REPORT.is_file():
        raise RuntimeError(f"world report is missing: {WORLD_REPORT}")
    report = json.loads(WORLD_REPORT.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise RuntimeError("world report root is not an object")
    blocker_fields = (
        "unsupported_player_items", "unsupported_entity_items",
        "unsupported_block_entity_items", "unsupported_block_entity_components",
        "unsupported_player_equipment", "unsupported_player_respawns",
        "unsupported_entities", "unsupported_create_fluids",
        "unsupported_block_entities", "unsupported_attributes",
        "unsupported_game_rules", "level_blockers", "malformed_regions",
    )
    blockers = {key: len(value) if isinstance(value, list) else value
                for key in blocker_fields
                if (value := report.get(key, [])) not in ([], {}, None, 0, False)}
    if blockers:
        raise RuntimeError(f"world conversion blockers remain: {blockers}")
    return report


def snapshot_auth(orchestrator, temporary: Path) -> dict:
    if not AUTH_DB.is_file():
        raise RuntimeError(f"EasyAuth database missing: {AUTH_DB}")
    snapshot = temporary / "easyauth.snapshot.db"
    snapshot_report = orchestrator.snapshot_easyauth_database(AUTH_DB, snapshot, AUTH_SNAPSHOT_REPORT)
    expected = int(snapshot_report["records"])
    if expected <= 0:
        raise RuntimeError("EasyAuth snapshot has no records")
    return {"snapshot": snapshot, "records": expected, "report": snapshot_report}


def run_auth(snapshot: Path, expected_records: int, env: dict[str, str]) -> dict:
    AUTH_MANIFEST.unlink(missing_ok=True)
    AUTH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(PYTHON), "-B", str(AUTH_CONVERTER), str(snapshot), str(AUTH_OUTPUT),
        "--manifest", str(AUTH_MANIFEST), "--expected-records", str(expected_records), "--force",
    ]
    completed = subprocess.run(command, cwd=WORKSPACE, env=env, text=True,
                               capture_output=True, encoding="utf-8", check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"EasyAuth converter failed ({completed.returncode}): {completed.stderr[-2000:]}")
    output = json.loads(AUTH_OUTPUT.read_text(encoding="utf-8"))
    if not isinstance(output, dict) or len(output) != expected_records:
        raise RuntimeError(f"Xiyus output record count mismatch: {len(output) if isinstance(output, dict) else 'invalid'} vs {expected_records}")
    return {"command": command, "stdout": completed.stdout[-2000:], "records": expected_records,
            "output_sha256": sha256(AUTH_OUTPUT), "manifest_sha256": sha256(AUTH_MANIFEST)}


def restore_exact_server_properties() -> dict:
    source_file = SOURCE / "server.properties"
    target_file = STAGING / "server.properties"
    if not source_file.is_file() or not target_file.is_file():
        raise RuntimeError("server.properties source/staging file missing")
    before = sha256(target_file)
    source_hash = sha256(source_file)
    temporary = target_file.with_name(f".{target_file.name}.{os.getpid()}.tmp")
    temporary.write_bytes(source_file.read_bytes())
    os.replace(temporary, target_file)
    after = sha256(target_file)
    if after != source_hash:
        raise RuntimeError("failed to restore exact server.properties bytes")
    return {"before_sha256": before, "source_sha256": source_hash, "after_sha256": after,
            "byte_identical": True}


def main() -> int:
    started = time.time()
    orchestrator = load_orchestrator()
    try:
        if not SOURCE.is_dir() or not STAGING.is_dir() or SOURCE.resolve() == STAGING.resolve():
            raise RuntimeError("source/staging paths are invalid or overlap")
        if Path(r"D:\Trans\20260807").resolve() == SOURCE.resolve():
            raise RuntimeError("historical 20260807 backup is forbidden")
        status(started, "RUNNING", "verify-world")
        world = verify_world_report()
        baseline = orchestrator.validate_baseline_manifest(
            json.loads(BASELINE.read_text(encoding="utf-8")), SOURCE, STAGING
        )
        orchestrator.assert_source_snapshot_stable(SOURCE, baseline)
        status(started, "RUNNING", "auth")
        temporary_root = WORKSPACE / "tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="incoming-20260811-auth-resume-", dir=str(temporary_root)) as temp:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join((str(NBT_DEPS), str(TOOLS)))
            auth = snapshot_auth(orchestrator, Path(temp))
            auth_result = run_auth(auth["snapshot"], auth["records"], env)
        status(started, "RUNNING", "restore-server-properties")
        properties = restore_exact_server_properties()
        orchestrator.assert_source_snapshot_stable(SOURCE, baseline)
        status(started, "RUNNING", "sign-marker")
        final_payload = {
            "schema": 2,
            "status": "CONVERTED_STAGING",
            "source": str(SOURCE),
            "staging": str(STAGING),
            "source_baseline_sha256": sha256(BASELINE),
            "world_report": {"path": str(WORLD_REPORT), "sha256": sha256(WORLD_REPORT)},
            "auth": auth_result,
            "auth_snapshot": {"path": str(AUTH_SNAPSHOT_REPORT), "sha256": sha256(AUTH_SNAPSHOT_REPORT), "records": auth["records"]},
            "server_properties": properties,
            "converter_fingerprints": orchestrator.converter_fingerprints(TOOLS),
            "source_read_only_verified": True,
        }
        atomic_json(FINAL_REPORT, final_payload)
        marker = orchestrator.make_conversion_marker(
            SOURCE, STAGING, baseline, FINAL_REPORT, STAGING, pending_saveddata=(),
            tools_dir=TOOLS,
        )
        marker_sha = atomic_json(MARKER, marker)
        status(started, "PASS", "complete", marker_sha256=marker_sha,
               auth_records=auth["records"], server_properties_sha256=properties["after_sha256"])
        print(json.dumps({"status": "PASS", "marker": str(MARKER), "marker_sha256": marker_sha,
                          "auth_records": auth["records"]}, ensure_ascii=False))
        return 0
    except BaseException as exc:
        status(started, "FAILED", "failed", error=f"{type(exc).__name__}: {exc}")
        print(f"resume finalize failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
