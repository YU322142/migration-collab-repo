#!/usr/bin/env python3
"""Crash-visible detached supervisor for one Candidate13 read-only NBT audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


WORKSPACE = Path(__file__).resolve().parents[2]
OUTPUTS = WORKSPACE / "outputs"
TOOLS = OUTPUTS / "tools"
SOURCE_WORLD = Path(r"D:\Trans\migration-audit-work\incoming-20260811-raw\20260811\world")
STAGING_WORLD = Path(r"D:\Trans\migration-audit-work\cutover-staging-incoming-20260811-candidate13-20260812\world")
SOURCE_CODE = OUTPUTS / "tmp" / "source-cookery-codec-cfr" / "com" / "github" / "ysbbbbbb" / "kaleidoscopecookery" / "entity" / "ScarecrowEntity.java"
TARGET_CODE = OUTPUTS / "tmp" / "target-cookery-codec-cfr" / "com" / "github" / "ysbbbbbb" / "kaleidoscopecookery" / "entity" / "ScarecrowEntity.java"
WORKERS = 10


AUDITS = {
    "netherite": {
        "phase": "full_source_staging_netherite_horse_armor",
        "tool": TOOLS / "audit_candidate13_netherite_horse_armor.py",
        "json": OUTPUTS / "candidate13-netherite-horse-armor-audit-20260812.json",
        "md": OUTPUTS / "candidate13-netherite-horse-armor-audit-20260812.md",
        "status": OUTPUTS / "candidate13-netherite-horse-armor-audit-20260812.status.json",
        "stdout": OUTPUTS / "candidate13-netherite-horse-armor-audit-20260812.stdout.log",
        "stderr": OUTPUTS / "candidate13-netherite-horse-armor-audit-20260812.stderr.log",
    },
    "scarecrow": {
        "phase": "full_source_staging_scarecrow_schema",
        "tool": TOOLS / "audit_candidate13_scarecrow_schema.py",
        "json": OUTPUTS / "candidate13-scarecrow-schema-audit-20260812.json",
        "md": OUTPUTS / "candidate13-scarecrow-schema-audit-20260812.md",
        "status": OUTPUTS / "candidate13-scarecrow-schema-audit-20260812.status.json",
        "stdout": OUTPUTS / "candidate13-scarecrow-schema-audit-20260812.stdout.log",
        "stderr": OUTPUTS / "candidate13-scarecrow-schema-audit-20260812.stderr.log",
    },
    "netherite_v2": {
        "phase": "full_source_staging_netherite_horse_armor_v2",
        "tool": TOOLS / "audit_candidate13_netherite_horse_armor.py",
        "json": OUTPUTS / "candidate13-netherite-horse-armor-audit-v2-20260812.json",
        "md": OUTPUTS / "candidate13-netherite-horse-armor-audit-v2-20260812.md",
        "status": OUTPUTS / "candidate13-netherite-horse-armor-audit-v2-20260812.status.json",
        "stdout": OUTPUTS / "candidate13-netherite-horse-armor-audit-v2-20260812.stdout.log",
        "stderr": OUTPUTS / "candidate13-netherite-horse-armor-audit-v2-20260812.stderr.log",
        "workers": 20,
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def status_value(
    config: dict[str, object],
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
        "phase": config["phase"],
        "read_only": True,
        "java_started": False,
        "started_at_unix": started,
        "updated_at_unix": now,
        "elapsed_seconds": round(now - started, 3),
        "supervisor_pid": os.getpid(),
        "audit_pid": audit_pid,
        "workers": int(config.get("workers", WORKERS)),
        "source_world": str(SOURCE_WORLD),
        "staging_world": str(STAGING_WORLD),
        "tool": str(config["tool"]),
        "tool_sha256": sha256(config["tool"]),
        "report_json": str(config["json"]),
        "report_md": str(config["md"]),
        "stdout": str(config["stdout"]),
        "stderr": str(config["stderr"]),
    }
    if exit_code is not None:
        value["exit_code"] = exit_code
    if error is not None:
        value["error"] = error
    for key in ("json", "md"):
        path = config[key]
        if path.is_file():
            value[f"report_{key}_bytes"] = path.stat().st_size
            value[f"report_{key}_sha256"] = sha256(path)
    return value


def command_for(name: str, config: dict[str, object]) -> list[str]:
    command = [
        sys.executable,
        "-B",
        str(config["tool"]),
        "--source",
        str(SOURCE_WORLD),
        "--staging",
        str(STAGING_WORLD),
        "--output-json",
        str(config["json"]),
        "--output-md",
        str(config["md"]),
        "--workers",
        str(int(config.get("workers", WORKERS))),
    ]
    if name == "scarecrow":
        command.extend(["--source-code", str(SOURCE_CODE), "--target-code", str(TARGET_CODE)])
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit", choices=sorted(AUDITS))
    args = parser.parse_args()
    config = AUDITS[args.audit]
    status_path = config["status"]
    started = time.time()
    audit_pid: int | None = None
    try:
        dependencies = [SOURCE_WORLD, STAGING_WORLD, config["tool"]]
        if args.audit == "scarecrow":
            dependencies.extend([SOURCE_CODE, TARGET_CODE])
        for path in dependencies:
            if not path.exists():
                raise FileNotFoundError(f"missing detached audit dependency: {path}")
        for key in ("json", "md", "status", "stdout", "stderr"):
            path = config[key]
            if path.exists():
                raise FileExistsError(f"refusing to replace detached audit output: {path}")

        atomic_json(status_path, status_value(config, "STARTING", started))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((str(TOOLS), environment.get("PYTHONPATH", "")))
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        with config["stdout"].open("wb") as stdout, config["stderr"].open("wb") as stderr:
            process = subprocess.Popen(
                command_for(args.audit, config),
                cwd=WORKSPACE,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            )
            audit_pid = process.pid
            atomic_json(status_path, status_value(config, "RUNNING", started, audit_pid=audit_pid))
            exit_code = process.wait()
        if exit_code != 0:
            raise RuntimeError(f"audit exited with code {exit_code}")
        if not config["json"].is_file() or not config["md"].is_file():
            raise RuntimeError("audit exited successfully without both reports")
        atomic_json(status_path, status_value(config, "PASS", started, audit_pid=audit_pid, exit_code=exit_code))
        return 0
    except BaseException as exc:
        atomic_json(status_path, status_value(config, "FAILED", started, audit_pid=audit_pid, error=f"{type(exc).__name__}: {exc}"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
