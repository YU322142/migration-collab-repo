#!/usr/bin/env python3
"""Run the final read-only staging verification independently of Codex."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

WORKSPACE = Path(__file__).resolve().parents[2]
PYTHON = Path(r"C:\Python314\python.exe")
SOURCE = Path(r"D:\Trans\migration-audit-work\incoming-20260811-raw\20260811")
STAGING = Path(r"D:\Trans\migration-audit-work\cutover-staging-incoming-20260811-candidate13-20260812")
REPORTS = Path(r"D:\Trans\migration-audit-work\cutover-staging-incoming-20260811-candidate13-20260812-reports")
REPORT = REPORTS / "fast-verify.json"
BASELINE = REPORTS / "source-baseline.json"
WAYPOINT = WORKSPACE / "outputs" / "projects" / "waypoint-fire-equivalence" / "build" / "libs" / "waypoint-fire-equivalence-0.1.1+mc1.21.1.jar"
WAYPOINT_SHA = "86A85C0447315AC17D373E3708425CEB8450D9D0CB1FD9C7ABDC82CE8D8E5B92"
STATUS = WORKSPACE / "outputs" / "incoming-20260811-verify.status.json"
STDOUT = WORKSPACE / "outputs" / "incoming-20260811-verify.stdout.log"
STDERR = WORKSPACE / "outputs" / "incoming-20260811-verify.stderr.log"


def atomic_json(value: dict) -> None:
    temporary = STATUS.with_name(f".{STATUS.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, STATUS)


def main() -> int:
    started = time.time()
    base = {
        "schema": 1, "source": str(SOURCE), "staging": str(STAGING),
        "report": str(REPORT), "workers": 20, "source_read_only": True,
        "supervisor_pid": os.getpid(), "started_at_unix": started,
    }
    try:
        for path in (SOURCE, STAGING, BASELINE, WAYPOINT):
            if not path.exists():
                raise FileNotFoundError(path)
        command = [
            str(PYTHON), "-B", str(WORKSPACE / "outputs" / "tools" / "prepare_fast_migration.py"),
            "verify", "--source-game-dir", str(SOURCE), "--staging-game-dir", str(STAGING),
            "--report", str(REPORT), "--baseline-manifest", str(BASELINE),
            "--waypoint-fire-jar", str(WAYPOINT), "--waypoint-fire-sha256", WAYPOINT_SHA,
            "--world-workers", "20",
        ]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((r"D:\Trans\migration-audit-work\poi-nbtdeps", str(WORKSPACE / "outputs" / "tools")))
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with STDOUT.open("wb") as stdout, STDERR.open("wb") as stderr:
            child = subprocess.Popen(command, cwd=WORKSPACE, env=environment, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, creationflags=flags)
            atomic_json({**base, "status": "RUNNING", "phase": "verify", "child_pid": child.pid,
                         "updated_at_unix": time.time()})
            code = child.wait()
        if code != 0:
            raise RuntimeError(f"verify exited with code {code}")
        atomic_json({**base, "status": "PASS", "phase": "complete", "exit_code": 0,
                     "updated_at_unix": time.time(), "elapsed_seconds": round(time.time()-started, 3)})
        return 0
    except BaseException as exc:
        atomic_json({**base, "status": "FAILED", "phase": "failed", "updated_at_unix": time.time(),
                     "elapsed_seconds": round(time.time()-started, 3), "error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
