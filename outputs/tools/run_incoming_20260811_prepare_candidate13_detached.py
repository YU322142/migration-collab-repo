#!/usr/bin/env python3
"""Detached assembly of a fresh Candidate13 disposable runtime copy."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

WORKSPACE = Path(__file__).resolve().parents[2]
PYTHON = Path(r"C:\Python314\python.exe")
STAGING = Path(r"D:\Trans\migration-audit-work\cutover-staging-incoming-20260811-candidate13-20260812")
RUNTIME = Path(r"D:\Trans\migration-audit-work\manual-test-candidate8n-20260811")
MODS = Path(r"D:\Trans\migration-audit-work\final-mod-bundles-candidate13-20260812\server-mods")
OUTPUT = Path(r"D:\Trans\migration-audit-work\manual-test-candidate13-final-20260812")
REPORT = Path(r"D:\Trans\migration-audit-work\manual-test-candidate13-final-prepare-20260812.json")
STATUS = WORKSPACE / "outputs" / "incoming-20260811-prepare-candidate13.status.json"
STDOUT = WORKSPACE / "outputs" / "incoming-20260811-prepare-candidate13.stdout.log"
STDERR = WORKSPACE / "outputs" / "incoming-20260811-prepare-candidate13.stderr.log"
PREPARE = WORKSPACE / "outputs" / "tools" / "prepare_final_fullstack_smoke.py"
WORKERS = 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(value: dict) -> None:
    temporary = STATUS.with_name(f".{STATUS.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, STATUS)


def main() -> int:
    started = time.time()
    base = {
        "schema": 1, "source_staging": str(STAGING), "runtime_template": str(RUNTIME),
        "mods": str(MODS), "output": str(OUTPUT), "report": str(REPORT),
        "workers": WORKERS, "source_read_only": True, "java_started": False,
        "supervisor_pid": os.getpid(), "started_at_unix": started,
    }
    try:
        for path in (STAGING, RUNTIME, MODS, PREPARE):
            if not path.exists():
                raise FileNotFoundError(path)
        if OUTPUT.exists() or REPORT.exists():
            raise FileExistsError("refusing to reuse Candidate13 target or report")
        command = [
            str(PYTHON), "-B", str(PREPARE),
            "--runtime-template", str(RUNTIME),
            "--staging", str(STAGING),
            "--mods", str(MODS),
            "--output", str(OUTPUT),
            "--report", str(REPORT),
            "--server-port", "12341",
            "--rcon-port", "12342",
            "--voice-port", "26341",
            "--sanitize-resources",
        ]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((r"D:\Trans\migration-audit-work\poi-nbtdeps", str(WORKSPACE / "outputs" / "tools")))
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with STDOUT.open("wb") as stdout, STDERR.open("wb") as stderr:
            child = subprocess.Popen(command, cwd=WORKSPACE, env=environment, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, creationflags=flags)
            atomic_json({**base, "status": "RUNNING", "phase": "prepare", "child_pid": child.pid,
                         "updated_at_unix": time.time()})
            code = child.wait()
        if code != 0:
            raise RuntimeError(f"prepare exited with code {code}")
        if not OUTPUT.is_dir() or not REPORT.is_file():
            raise RuntimeError("prepare exited without target/report")
        atomic_json({**base, "status": "PASS", "phase": "complete", "exit_code": 0,
                     "updated_at_unix": time.time(), "elapsed_seconds": round(time.time()-started, 3),
                     "report_sha256": sha256(REPORT)})
        return 0
    except BaseException as exc:
        atomic_json({**base, "status": "FAILED", "phase": "failed", "updated_at_unix": time.time(),
                     "elapsed_seconds": round(time.time()-started, 3), "error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
