#!/usr/bin/env python3
"""Prepare a disposable Candidate14 runtime from frozen staging and release.

This wrapper binds the generic copier/sanitizer to an explicit Candidate14
READY/build report.  It never changes the frozen staging, source backup,
published release, or production server.properties; only the fresh output copy
receives loopback test settings.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import uuid

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import candidate14_release_gate_common as release_common
import prepare_final_fullstack_smoke as smoke


ALLOWED_ROOT = Path(r"D:\Trans\migration-audit-work")
FORBIDDEN_SOURCE = Path(r"D:\Trans\20260807")


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def overlaps(first: Path, second: Path) -> bool:
    return is_within(first, second) or is_within(second, first)


def is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        attributes = 0
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) or path.is_symlink()


def prepare(args: argparse.Namespace) -> dict:
    release = release_common.validate_release(
        args.release_root,
        args.ready_sha256,
        args.build_report,
        args.build_report_sha256,
    )
    runtime_template = args.runtime_template.resolve()
    staging = args.staging.resolve()
    output = args.output.resolve()
    report = args.report.resolve()
    for path, label in (
        (runtime_template, "runtime template"),
        (staging, "frozen staging"),
        (output, "runtime output"),
        (report, "prepare report"),
    ):
        if not is_within(path, ALLOWED_ROOT) or is_within(path, FORBIDDEN_SOURCE):
            raise ValueError(f"{label} is outside the audited migration area: {path}")
    release_root = args.release_root.resolve()
    if any(overlaps(output, protected) for protected in (runtime_template, staging, release_root)):
        raise ValueError("runtime output must not overlap template, staging, or release")
    if is_reparse(output):
        raise ValueError("runtime output may not already be a junction/reparse point")
    if (args.server_port, args.rcon_port, args.voice_port) != (12341, 12342, 26341):
        raise ValueError("Candidate14 private runtime ports are 12341/12342/26341")
    mods = Path(release["root"]) / "server-mods"
    if output.exists():
        raise FileExistsError(f"refusing to overwrite runtime output: {output}")
    if report.exists():
        raise FileExistsError(f"refusing to overwrite prepare report: {report}")
    temporary = output.with_name(
        output.name + ".candidate14." + uuid.uuid4().hex + ".tmp"
    )
    published = False
    try:
        result = smoke.prepare(
            smoke.ensure_d_path(runtime_template, "runtime-template"),
            smoke.ensure_d_path(staging, "staging"),
            smoke.ensure_d_path(mods, "mods"),
            smoke.ensure_d_path(temporary, "temporary output"),
            args.server_port,
            args.rcon_port,
            args.voice_port,
            True,
        )
        observed = result.get("resource_sanitization", {}).get("runtime_mod_manifest", {})
        expected = release["runtime_server_identity"]
        identity = {
            "files": observed.get("file_count"),
            "bytes": observed.get("bytes"),
            "bundle_sha256": str(observed.get("bundle_sha256", "")).upper(),
        }
        expected_core = {
            key: expected[key] for key in ("files", "bytes", "bundle_sha256")
        }
        if identity != expected_core:
            raise ValueError(
                f"prepared runtime identity mismatch: {identity} != {expected_core}"
            )
        changed_jars = sorted(
            Path(str(row.get("path", ""))).name
            for row in result.get("resource_sanitization", {}).get("changes", [])
            if isinstance(row, dict) and row.get("kind") == "jar-resource-sanitize"
        )
        if changed_jars != sorted(release_common.SANITIZER_JARS):
            raise ValueError(f"prepared runtime changed unexpected JARs: {changed_jars}")
        # Rebase evidence paths before the atomic publication rename.
        old_prefix = str(temporary)
        new_prefix = str(output)
        result = json.loads(
            json.dumps(result, ensure_ascii=False).replace(old_prefix, new_prefix)
        )
        result["output"] = str(output)
        result["candidate14_release"] = {
            "root": release["root"],
            "ready_sha256": release["ready"]["sha256"],
            "build_report_sha256": release["build_report"]["sha256"],
            "server_manifest_sha256": release["server_manifest"]["sha256"],
            "runtime_server_identity": expected,
            "release_scoped_exactness": True,
            "permanent_mod_count_cap": False,
        }
        result["safety"] = {
            "source_or_staging_written": False,
            "published_release_written": False,
            "production_server_properties_modified": False,
            "disposable_server_properties_modified": True,
            "loopback_only": True,
            "java_started": False,
            "atomic_publication": True,
        }
        os.replace(temporary, output)
        published = True
        smoke.atomic_json(report, result)
        return result
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if published and output.exists() and not report.exists():
            shutil.rmtree(output, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--ready-sha256", required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--build-report-sha256", required=True)
    parser.add_argument("--runtime-template", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--server-port", type=int, default=12341)
    parser.add_argument("--rcon-port", type=int, default=12342)
    parser.add_argument("--voice-port", type=int, default=26341)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prepare(args)
    except Exception as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": result["output"],
                "java_started": False,
                "production_server_properties_modified": False,
                "permanent_mod_count_cap": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
