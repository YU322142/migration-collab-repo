#!/usr/bin/env python3
"""Detached supervisor for the latest stopped-source Create fluid audit.

This process is launched independently from Codex.  It owns the child audit,
captures its logs, and publishes an atomic status record on every terminal
path so a UI/network interruption cannot silently lose the long-running job.
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
OUTPUTS = WORKSPACE / "outputs"
WORLD = Path(r"<AUDIT_ROOT>\incoming-20260811-raw\20260811\world")
TOOL = OUTPUTS / "tools" / "audit_create_fluid_nbt.py"
NBT_DEPS = Path(r"<AUDIT_ROOT>\poi-nbtdeps")
REPORT = OUTPUTS / "incoming-20260811-create-fluid-source-audit-v3.json"
STATUS = OUTPUTS / "incoming-20260811-create-fluid-source-audit-v3.status.json"
STDOUT = OUTPUTS / "incoming-20260811-create-fluid-source-audit-v3.stdout.log"
STDERR = OUTPUTS / "incoming-20260811-create-fluid-source-audit-v3.stderr.log"
WORKERS = 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(value: dict[str, object]) -> None:
    temporary = STATUS.with_name(f".{STATUS.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, STATUS)


def status_value(
    status: str,
    started: float,
    *,
    audit_pid: int | None = None,
    exit_code: int | None = None,
    error: str | None = None,
) -> dict[str, object]:
    now = time.time()
    value: dict[str, object] = {
        "schema": 1,
        "status": status,
        "phase": "full_source_fluid_audit",
        "started_at_unix": started,
        "updated_at_unix": now,
        "elapsed_seconds": round(now - started, 3),
        "supervisor_pid": os.getpid(),
        "audit_pid": audit_pid,
        "workers": WORKERS,
        "world": str(WORLD),
        "report": str(REPORT),
        "stdout": str(STDOUT),
        "stderr": str(STDERR),
        "tool": str(TOOL),
        "tool_sha256": sha256(TOOL),
    }
    if exit_code is not None:
        value["exit_code"] = exit_code
    if error is not None:
        value["error"] = error
    if REPORT.is_file():
        value["report_bytes"] = REPORT.stat().st_size
        value["report_sha256"] = sha256(REPORT)
    return value


def main() -> int:
    started = time.time()
    audit_pid: int | None = None
    try:
        for path in (WORLD, TOOL, NBT_DEPS):
            if not path.exists():
                raise FileNotFoundError(f"missing detached audit dependency: {path}")
        if REPORT.exists():
            raise FileExistsError(f"refusing to replace existing report: {REPORT}")

        atomic_json(status_value("STARTING", started))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(NBT_DEPS), str(OUTPUTS / "tools"))
        )
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        command = [
            sys.executable,
            "-B",
            str(TOOL),
            "--world",
            str(WORLD),
            "--report",
            str(REPORT),
            "--workers",
            str(WORKERS),
        ]
        with STDOUT.open("wb") as stdout, STDERR.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=WORKSPACE,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            )
            audit_pid = process.pid
            atomic_json(status_value("RUNNING", started, audit_pid=audit_pid))
            exit_code = process.wait()

        if exit_code != 0:
            raise RuntimeError(f"fluid audit exited with code {exit_code}")
        if not REPORT.is_file():
            raise RuntimeError("fluid audit exited successfully without its report")
        atomic_json(
            status_value(
                "PASS",
                started,
                audit_pid=audit_pid,
                exit_code=exit_code,
            )
        )
        return 0
    except BaseException as exc:
        try:
            atomic_json(
                status_value(
                    "FAILED",
                    started,
                    audit_pid=audit_pid,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
        finally:
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
