#!/usr/bin/env python3
"""Detached focused read-only validation for the latest-source schematic region."""

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
SOURCE_GAME = Path(r"<AUDIT_ROOT>\incoming-20260811-raw\20260811")
TARGET_GAME = Path(r"<AUDIT_ROOT>\manual-test-candidate13-preflight-20260812")
TOOL = OUTPUTS / "tools" / "convert_world_nbt.py"
NBT_DEPS = Path(r"<AUDIT_ROOT>\poi-nbtdeps")
REPORT = OUTPUTS / "incoming-20260811-world-focus-rminus1-20260812.json"
STATUS = OUTPUTS / "incoming-20260811-world-focus-rminus1-20260812.status.json"
STDOUT = OUTPUTS / "incoming-20260811-world-focus-rminus1-20260812.stdout.log"
STDERR = OUTPUTS / "incoming-20260811-world-focus-rminus1-20260812.stderr.log"
WAYPOINT = OUTPUTS / "projects" / "waypoint-fire-equivalence" / "build" / "libs" / "waypoint-fire-equivalence-0.1.1+mc1.21.1.jar"
WAYPOINT_SHA = "86A85C0447315AC17D373E3708425CEB8450D9D0CB1FD9C7ABDC82CE8D8E5B92"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_status(status: str, started: float, *, supervisor_pid: int | None = None, child_pid: int | None = None, exit_code: int | None = None, error: str | None = None) -> None:
    value: dict[str, object] = {
        "schema": 1,
        "status": status,
        "phase": "latest_source_focus_schematic_validation",
        "started_at_unix": started,
        "updated_at_unix": time.time(),
        "elapsed_seconds": round(time.time() - started, 3),
        "supervisor_pid": supervisor_pid or os.getpid(),
        "child_pid": child_pid,
        "workers": 20,
        "world": str(WORLD),
        "source_game_dir": str(SOURCE_GAME),
        "target_game_dir": str(TARGET_GAME),
        "only_region": "region/r.-1.-1.mca",
        "report": str(REPORT),
        "stdout": str(STDOUT),
        "stderr": str(STDERR),
        "tool": str(TOOL),
        "tool_sha256": sha256(TOOL) if TOOL.is_file() else None,
        "waypoint_sha256": WAYPOINT_SHA,
    }
    if REPORT.is_file():
        value["report_bytes"] = REPORT.stat().st_size
        value["report_sha256"] = sha256(REPORT)
    if exit_code is not None:
        value["exit_code"] = exit_code
    if error is not None:
        value["error"] = error
    temp = STATUS.with_name(f".{STATUS.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, STATUS)


def main() -> int:
    started = time.time()
    child_pid = None
    try:
        for path in (WORLD, SOURCE_GAME, TARGET_GAME / "mods", TARGET_GAME / "schematics", TOOL, NBT_DEPS, WAYPOINT):
            if not path.exists():
                raise FileNotFoundError(f"missing focus dependency: {path}")
        for path in (REPORT, STDOUT, STDERR):
            if path.exists():
                raise FileExistsError(f"refusing to replace existing focus output: {path}")
        if sha256(WAYPOINT) != WAYPOINT_SHA:
            raise RuntimeError("waypoint compatibility JAR hash drift")
        write_status("STARTING", started)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(NBT_DEPS), str(OUTPUTS / "tools")))
        args = [
            sys.executable, "-B", str(TOOL), "dry-run",
            "--world", str(WORLD), "--source-game-dir", str(SOURCE_GAME),
            "--target-game-dir", str(TARGET_GAME),
            "--waypoint-fire-compat-jar", str(WAYPOINT),
            "--waypoint-fire-compat-sha256", WAYPOINT_SHA,
            "--only-region", "region/r.-1.-1.mca", "--workers", "20",
            "--report", str(REPORT),
        ]
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        with STDOUT.open("wb") as stdout, STDERR.open("wb") as stderr:
            child = subprocess.Popen(args, cwd=WORKSPACE, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, creationflags=flags)
            child_pid = child.pid
            write_status("RUNNING", started, child_pid=child_pid)
            exit_code = child.wait()
        if exit_code != 0 or not REPORT.is_file():
            raise RuntimeError(f"focus dry-run exit={exit_code}, report={REPORT.is_file()}")
        write_status("PASS", started, child_pid=child_pid, exit_code=exit_code)
        return 0
    except BaseException as exc:
        write_status("FAILED", started, child_pid=child_pid, error=f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
