#!/usr/bin/env python3
"""Build a fresh Candidate13 disposable runtime from verified staging.

This is assembly only; it never re-runs world conversion and never touches the
read-only incoming source or the existing consumed smoke directory.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

WORKSPACE = Path(__file__).resolve().parents[2]
PYTHON = Path(r"C:\Python314\python.exe")
STAGING = Path(r"<AUDIT_ROOT>\cutover-staging-incoming-20260811-candidate13-20260812")
RUNTIME = Path(r"<AUDIT_ROOT>\manual-test-candidate8n-20260811")
MODS = Path(r"<AUDIT_ROOT>\final-mod-bundles-candidate13-20260812\server-mods")
OUTPUT = Path(r"<AUDIT_ROOT>\manual-test-candidate13-fresh2-20260812")
REPORT = Path(r"<AUDIT_ROOT>\manual-test-candidate13-fresh2-prepare-20260812.json")
STATUS = WORKSPACE / "outputs" / "incoming-20260811-prepare-candidate13-fresh2.status.json"
STDOUT = WORKSPACE / "outputs" / "incoming-20260811-prepare-candidate13-fresh2.stdout.log"
STDERR = WORKSPACE / "outputs" / "incoming-20260811-prepare-candidate13-fresh2.stderr.log"
PREPARE = WORKSPACE / "outputs" / "tools" / "prepare_final_fullstack_smoke.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_status(value: dict) -> None:
    tmp = STATUS.with_name(f".{STATUS.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STATUS)


def main() -> int:
    started = time.time()
    base = {"schema": 1, "phase": "assembly", "workers": 20,
            "source_read_only": True, "java_started": False,
            "staging": str(STAGING), "runtime_template": str(RUNTIME),
            "mods": str(MODS), "output": str(OUTPUT), "report": str(REPORT),
            "supervisor_pid": os.getpid(), "started_at_unix": started}
    try:
        for path in (STAGING, RUNTIME, MODS, PREPARE):
            if not path.exists():
                raise FileNotFoundError(path)
        if OUTPUT.exists() or REPORT.exists():
            raise FileExistsError(f"refusing to reuse fresh2 output/report: {OUTPUT} {REPORT}")
        command = [str(PYTHON), "-B", str(PREPARE),
                   "--runtime-template", str(RUNTIME), "--staging", str(STAGING),
                   "--mods", str(MODS), "--output", str(OUTPUT), "--report", str(REPORT),
                   "--server-port", "12341", "--rcon-port", "12342", "--voice-port", "26341",
                   "--sanitize-resources"]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((r"<AUDIT_ROOT>\poi-nbtdeps", str(WORKSPACE / "outputs" / "tools")))
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with STDOUT.open("wb") as stdout, STDERR.open("wb") as stderr:
            child = subprocess.Popen(command, cwd=WORKSPACE, env=env, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, creationflags=flags)
            write_status({**base, "status": "RUNNING", "child_pid": child.pid, "updated_at_unix": time.time()})
            code = child.wait()
        if code != 0 or not OUTPUT.is_dir() or not REPORT.is_file():
            raise RuntimeError(f"prepare failed code={code}")
        write_status({**base, "status": "PASS", "phase": "complete", "exit_code": 0,
                      "elapsed_seconds": round(time.time()-started, 3), "report_sha256": sha256(REPORT),
                      "updated_at_unix": time.time()})
        return 0
    except BaseException as exc:
        write_status({**base, "status": "FAILED", "phase": "failed",
                      "elapsed_seconds": round(time.time()-started, 3),
                      "error": f"{type(exc).__name__}: {exc}", "updated_at_unix": time.time()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
