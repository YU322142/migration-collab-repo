#!/usr/bin/env python3
"""Compatibility CLI for the fail-closed remote live snapshot engine.

The runbook uses this short command name. All hashing, path isolation,
stopped-source probing, manifest binding, incremental copy, deletion policy,
rollback, and final equivalence checks live in remote_live_snapshot.py.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


def _load_engine():
    path = Path(__file__).with_name("remote_live_snapshot.py")
    spec = importlib.util.spec_from_file_location("sync_live_snapshot_engine", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load snapshot engine: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ENGINE = _load_engine()
SnapshotError = _ENGINE.SnapshotError


def default_manifest(mirror: Path, report: Path) -> Path:
    return (
        Path(report).resolve().parent / f"{Path(mirror).resolve().name}-manifest.json"
    )


def _compat_status(result: dict[str, Any], success: str) -> dict[str, Any]:
    value = dict(result)
    value["engine_status"] = result.get("status")
    if result.get("exit_code") == 0:
        value["status"] = success
    return value


def _raise_if_blocked(result: dict[str, Any]) -> None:
    if result.get("exit_code") != 0:
        raise SnapshotError(
            str(
                result.get(
                    "error", f"snapshot operation blocked: {result.get('status')}"
                )
            )
        )


def preheat(
    remote: Path,
    mirror: Path,
    report: Path,
    *,
    manifest: Path | None = None,
    retries: int = _ENGINE.DEFAULT_RETRIES,
) -> dict[str, Any]:
    remote = Path(remote)
    mirror = Path(mirror)
    report = Path(report)
    manifest = default_manifest(mirror, report) if manifest is None else Path(manifest)
    result = _ENGINE.preheat(
        remote,
        mirror,
        manifest,
        label="<LIVE_SERVER>",
        retries=retries,
    )
    result = _compat_status(result, "PREHEATED")
    result["mirror_manifest"] = str(manifest.resolve())
    result["source_snapshot"] = dict(result.get("snapshot", {}))
    result["mirror_snapshot"] = dict(result.get("snapshot", {}))
    result["copied"] = int(result.get("snapshot", {}).get("file_count", 0))
    result["source_deletions"] = []
    result["source_lock"] = result.get("session_lock_after", {}).get("status")
    _ENGINE.write_report(report, result)
    _raise_if_blocked(result)
    return result


def refresh(
    remote: Path,
    mirror: Path,
    report: Path,
    *,
    manifest: Path | None = None,
    allow_source_deletions: bool = False,
    retries: int = _ENGINE.DEFAULT_RETRIES,
) -> dict[str, Any]:
    remote = Path(remote)
    mirror = Path(mirror)
    report = Path(report)
    manifest = default_manifest(mirror, report) if manifest is None else Path(manifest)
    result = _ENGINE.refresh(
        remote,
        mirror,
        manifest,
        allow_source_deletions=allow_source_deletions,
        retries=retries,
    )
    result = _compat_status(result, "READY_FOR_STAGING_REFRESH")
    result["mirror_manifest"] = str(manifest.resolve())
    source_summary = dict(result.get("source_snapshot", {}))
    mirror_summary = dict(result.get("mirror_after", {}))
    result["source_snapshot"] = source_summary
    result["mirror_snapshot"] = mirror_summary
    delta = result.get("delta", {})
    result["changed"] = [
        *(entry.get("source") for entry in delta.get("added", [])),
        *(entry.get("after", {}).get("source") for entry in delta.get("modified", [])),
    ]
    result["changed"] = sorted(
        path for path in result["changed"] if isinstance(path, str)
    )
    result["deleted"] = sorted(
        entry.get("source")
        for entry in delta.get("deleted", [])
        if isinstance(entry.get("source"), str)
    )
    result["source_lock"] = result.get("session_lock_after", {}).get(
        "status", result.get("session_lock_before", {}).get("status")
    )
    _ENGINE.write_report(report, result)
    _raise_if_blocked(result)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("preheat", "refresh"))
    parser.add_argument(
        "--remote-game-dir",
        "--source",
        dest="remote_game_dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--local-mirror",
        "--mirror",
        dest="local_mirror",
        type=Path,
        required=True,
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--retries", type=int, default=_ENGINE.DEFAULT_RETRIES)
    parser.add_argument(
        "--allow-source-deletions",
        action="store_true",
        help="apply reviewed non-critical deletions; critical deletions always block",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.retries < 1:
        print("snapshot sync blocked: --retries must be at least 1", file=sys.stderr)
        return 2
    try:
        resolved_mirror = Path(args.local_mirror).resolve(strict=False)
        if os.name == "nt" and resolved_mirror.drive.upper() != "D:":
            raise SnapshotError(
                f"local mirror must be a local D: path: {resolved_mirror}"
            )
        if args.phase == "preheat":
            if args.allow_source_deletions:
                raise SnapshotError(
                    "--allow-source-deletions is valid only for stopped refresh"
                )
            result = preheat(
                args.remote_game_dir,
                args.local_mirror,
                args.report,
                manifest=args.manifest,
                retries=args.retries,
            )
        else:
            result = refresh(
                args.remote_game_dir,
                args.local_mirror,
                args.report,
                manifest=args.manifest,
                allow_source_deletions=args.allow_source_deletions,
                retries=args.retries,
            )
    except (SnapshotError, OSError, ValueError, RuntimeError) as exc:
        print(f"snapshot sync blocked: {exc}", file=sys.stderr)
        blocked: dict[str, Any] = {
            "status": "BLOCKED",
            "exit_code": 2,
            "report": str(Path(args.report).resolve()),
            "error": str(exc),
        }
        try:
            written = json.loads(Path(args.report).read_text(encoding="utf-8"))
            if isinstance(written, dict):
                blocked["status"] = written.get("status", blocked["status"])
                blocked["engine_status"] = written.get("engine_status")
        except (OSError, json.JSONDecodeError):
            blocked["report_readable"] = False
        print(json.dumps(blocked, ensure_ascii=False, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "engine_status": result["engine_status"],
                "report": str(Path(args.report).resolve()),
                "manifest": result["mirror_manifest"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
