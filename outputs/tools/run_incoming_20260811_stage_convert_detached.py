#!/usr/bin/env python3
"""Detached one-shot stage -> convert transaction for the latest stopped backup.

This is intentionally separate from the Codex process.  It copies the latest
source into a fresh staging tree, then runs the fail-closed migration converter
with 20 worker processes.  It never writes the raw backup/source tree and
publishes status/logs outside both source and staging.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


WORKSPACE = Path(__file__).resolve().parents[2]
PYTHON = Path(r"C:\Python314\python.exe")
NBT_DEPS = Path(r"D:\Trans\migration-audit-work\poi-nbtdeps")
SOURCE = Path(r"D:\Trans\migration-audit-work\incoming-20260811-raw\20260811")
STAGING = Path(r"D:\Trans\migration-audit-work\cutover-staging-incoming-20260811-candidate13-20260812")
REPORTS = Path(r"D:\Trans\migration-audit-work\cutover-staging-incoming-20260811-candidate13-20260812-reports")
REPORT = REPORTS / "fast-stage-convert.json"
STATUS = WORKSPACE / "outputs" / "incoming-20260811-stage-convert-20260812.status.json"
STDOUT = WORKSPACE / "outputs" / "incoming-20260811-stage-convert-20260812.stdout.log"
STDERR = WORKSPACE / "outputs" / "incoming-20260811-stage-convert-20260812.stderr.log"
PREPARE = WORKSPACE / "outputs" / "tools" / "prepare_fast_migration.py"
WAYPOINT = WORKSPACE / "outputs" / "projects" / "waypoint-fire-equivalence" / "build" / "libs" / "waypoint-fire-equivalence-0.1.1+mc1.21.1.jar"
WAYPOINT_SHA = "86A85C0447315AC17D373E3708425CEB8450D9D0CB1FD9C7ABDC82CE8D8E5B92"
VILLAGER_BASELINE = Path(r"D:\Trans\migration-audit-work\incoming-20260811-villagers-source-baseline-20260812.json")
WORKERS = 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(value: dict[str, object]) -> None:
    temporary = STATUS.with_name(f".{STATUS.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, STATUS)


def status_value(status: str, started: float, *, phase: str, child_pid: int | None = None, exit_code: int | None = None, error: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": 1,
        "status": status,
        "phase": phase,
        "started_at_unix": started,
        "updated_at_unix": time.time(),
        "elapsed_seconds": round(time.time() - started, 3),
        "supervisor_pid": os.getpid(),
        "child_pid": child_pid,
        "workers": WORKERS,
        "source": str(SOURCE),
        "staging": str(STAGING),
        "reports": str(REPORTS),
        "report": str(REPORT),
        "prepare_tool": str(PREPARE),
        "prepare_tool_sha256": sha256(PREPARE) if PREPARE.is_file() else None,
        "waypoint_jar": str(WAYPOINT),
        "waypoint_sha256": WAYPOINT_SHA,
        "villager_baseline": str(VILLAGER_BASELINE),
    }
    if REPORT.is_file():
        value["report_bytes"] = REPORT.stat().st_size
        value["report_sha256"] = sha256(REPORT)
    if exit_code is not None:
        value["exit_code"] = exit_code
    if error is not None:
        value["error"] = error
    return value


def run_phase(phase: str, report_path: Path, stdout, stderr, started: float) -> int:
    args = [
        "-B",
        str(PREPARE),
        phase,
        "--source-game-dir",
        str(SOURCE),
        "--staging-game-dir",
        str(STAGING),
        "--report",
        str(report_path),
        "--baseline-manifest",
        str(REPORTS / "source-baseline.json"),
        "--waypoint-fire-jar",
        str(WAYPOINT),
        "--waypoint-fire-sha256",
        WAYPOINT_SHA,
        "--villager-baseline",
        str(VILLAGER_BASELINE),
        "--world-workers",
        str(WORKERS),
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join((str(NBT_DEPS), str(WORKSPACE / "outputs" / "tools")))
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    child = subprocess.Popen(
        [str(PYTHON), *args],
        cwd=WORKSPACE,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        creationflags=flags,
    )
    atomic_json(status_value("RUNNING", started, phase=phase, child_pid=child.pid))
    return child.wait()


def main() -> int:
    started = time.time()
    child_pid = None
    try:
        for path in (SOURCE, SOURCE / "world", PREPARE, NBT_DEPS, WAYPOINT, VILLAGER_BASELINE):
            if not path.exists():
                raise FileNotFoundError(f"missing transaction dependency: {path}")
        if STAGING.exists() or REPORTS.exists():
            raise FileExistsError("refusing to reuse an existing staging/report tree")
        REPORTS.mkdir(parents=True, exist_ok=False)
        atomic_json(status_value("STARTING", started, phase="stage"))
        with STDOUT.open("wb") as stdout, STDERR.open("wb") as stderr:
            stage_report = REPORTS / "fast-stage.json"
            stage_exit = run_phase("stage", stage_report, stdout, stderr, started)
            if stage_exit != 0:
                raise RuntimeError(f"stage exited with code {stage_exit}")
            atomic_json(status_value("RUNNING", started, phase="convert"))
            convert_report = REPORTS / "fast-convert.json"
            convert_exit = run_phase("convert", convert_report, stdout, stderr, started)
            if convert_exit != 0:
                raise RuntimeError(f"convert exited with code {convert_exit}")
        marker = STAGING / "migration-reports" / "conversion-complete.json"
        if not marker.is_file():
            raise RuntimeError("conversion completed without schema2 marker")
        atomic_json(status_value("PASS", started, phase="complete", exit_code=0))
        return 0
    except BaseException as exc:
        atomic_json(status_value("FAILED", started, phase="failed", child_pid=child_pid, error=f"{type(exc).__name__}: {exc}"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
