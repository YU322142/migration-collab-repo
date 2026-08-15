#!/usr/bin/env python3
"""Validate the frozen Candidate11 release or its sanitized server copy."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = Path(
    r"D:\Trans\migration-audit-work\final-mod-bundles-candidate11-20260811"
)
AUDIT_PATH = WORKSPACE / "outputs" / "candidate11-bundle-full-audit-20260811.json"
AUDIT_SHA256 = "C3C96146A488DDBC5054F3A7B721AE9EA8031C83615B817D07FA453981D40A4F"
EXPECTED_RUNTIME_COUNT = 52
EXPECTED_RUNTIME_BYTES = 164_649_980
EXPECTED_RUNTIME_BUNDLE_SHA256 = (
    "2A4714F177A8FE7CE199E5143AAF619050BF161A2C946053B6A39DA318FBB18C"
)


def load_builder():
    path = Path(__file__).with_name("build_candidate11_guard_cc_bundles.py")
    spec = importlib.util.spec_from_file_location("candidate11_runtime_builder", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def read_audit() -> dict[str, Any]:
    if builder.sha256(AUDIT_PATH) != AUDIT_SHA256:
        raise ValueError("Candidate11 bundle audit hash mismatch")
    value = builder.read_json(AUDIT_PATH)
    runtime = value.get("expected_disposable_server_runtime")
    if (
        value.get("status") != "PASS"
        or not isinstance(runtime, dict)
        or runtime.get("file_count") != EXPECTED_RUNTIME_COUNT
        or runtime.get("bytes") != EXPECTED_RUNTIME_BYTES
        or runtime.get("bundle_sha256") != EXPECTED_RUNTIME_BUNDLE_SHA256
    ):
        raise ValueError("Candidate11 bundle audit runtime binding mismatch")
    return value


def published(mods: Path | None = None) -> dict[str, Any]:
    audit = read_audit()
    result = builder.validate_published_candidate11(BUNDLE_ROOT)
    expected_mods = (BUNDLE_ROOT / "server-mods").resolve()
    if mods is not None and mods.resolve() != expected_mods:
        raise ValueError(f"published mods must be exactly {expected_mods}")
    if (
        result["server"]["bundle_sha256"]
        != audit["server"]["bundle_sha256"]
        or result["server"]["manifest_sha256"]
        != audit["server"]["manifest_sha256"]
        or result["ready_sha256"] != audit["release"]["ready_sha256"]
    ):
        raise ValueError("Candidate11 published release/audit binding mismatch")
    return {
        "status": "PASS",
        "bundle_root": str(BUNDLE_ROOT.resolve()),
        "mods_path": str(expected_mods),
        "file_count": len(result["server"]["rows"]),
        "bytes": result["server"]["manifest"]["bytes"],
        "bundle_sha256": result["server"]["bundle_sha256"],
        "manifest_sha256": result["server"]["manifest_sha256"],
        "ready_sha256": result["ready_sha256"],
        "release_lock_sha256": result["release_lock_sha256"],
        "bundle_pair_sha256": result["bundle_pair_sha256"],
        "cc_guard_sha256": result["cc_compat"]["sha256"],
        "create_guard_sha256": result["guard"]["sha256"],
        "audit_path": str(AUDIT_PATH.resolve()),
        "audit_sha256": AUDIT_SHA256,
        "jars": {
            row["file"]: {
                "path": str(row["_path"]),
                "bytes": row["bytes"],
                "sha256": row["sha256"].lower(),
            }
            for row in result["server"]["rows"]
        },
    }


def runtime(mods: Path, prepare_report: Path) -> dict[str, Any]:
    source = published()
    audit = read_audit()
    expected = audit["expected_disposable_server_runtime"]
    mods = mods.resolve()
    prepare_report = prepare_report.resolve()
    if not mods.is_dir() or mods.is_symlink():
        raise ValueError(f"runtime mods is not a real directory: {mods}")
    if not prepare_report.is_file() or prepare_report.is_symlink():
        raise ValueError(f"prepare report is not a real file: {prepare_report}")
    value = builder.read_json(prepare_report)
    if (
        value.get("status") != "PREPARED"
        or Path(str(value.get("output", ""))).resolve() != mods.parent
    ):
        raise ValueError("Candidate11 prepare report status/output binding mismatch")
    sanitization = value.get("resource_sanitization")
    if not isinstance(sanitization, dict) or (
        sanitization.get("status") != "SANITIZED"
        or Path(str(sanitization.get("mods", ""))).resolve() != mods
        or sanitization.get("changed_files") != 5
    ):
        raise ValueError("Candidate11 sanitizer status/path/change-count mismatch")
    runtime_manifest = sanitization.get("runtime_mod_manifest")
    if not isinstance(runtime_manifest, dict) or any(
        runtime_manifest.get(key) != expected.get(key)
        for key in ("file_count", "bytes", "bundle_sha256")
    ):
        raise ValueError("Candidate11 runtime manifest aggregate mismatch")
    expected_rows = expected.get("files")
    actual_rows = runtime_manifest.get("files")
    if not isinstance(expected_rows, list) or not isinstance(actual_rows, list):
        raise ValueError("Candidate11 runtime manifest rows are absent")
    expected_by_name = {row["file"].casefold(): row for row in expected_rows}
    actual_by_name = {row["file"].casefold(): row for row in actual_rows}
    if len(expected_by_name) != 52 or set(actual_by_name) != set(expected_by_name):
        raise ValueError("Candidate11 runtime manifest JAR set mismatch")
    entries = sorted(mods.iterdir(), key=lambda path: path.name.casefold())
    if len(entries) != 52 or any(
        entry.is_symlink() or not entry.is_file() or entry.suffix.lower() != ".jar"
        for entry in entries
    ):
        raise ValueError("Candidate11 runtime mods must be a flat exact 52-JAR set")
    files = {entry.name.casefold(): entry for entry in entries}
    digest_rows: list[dict[str, Any]] = []
    mod_owners: dict[str, str] = {}
    for key in sorted(expected_by_name):
        expected_row = expected_by_name[key]
        actual_row = actual_by_name[key]
        path = files.get(key)
        if path is None:
            raise ValueError(f"Candidate11 runtime JAR missing: {expected_row['file']}")
        actual_hash = builder.sha256(path)
        actual_ids = sorted(builder.jar_mod_ids(path))
        if (
            actual_row.get("file") != expected_row["file"]
            or actual_row.get("bytes") != expected_row["bytes"]
            or str(actual_row.get("sha256", "")).upper() != expected_row["sha256"]
            or actual_row.get("mod_ids") != expected_row["mod_ids"]
            or path.stat().st_size != expected_row["bytes"]
            or actual_hash != expected_row["sha256"]
            or actual_ids != expected_row["mod_ids"]
        ):
            raise ValueError(f"Candidate11 runtime row/byte/metadata mismatch: {path.name}")
        for mod_id in actual_ids:
            if mod_id.casefold() in mod_owners:
                raise ValueError(f"Candidate11 runtime duplicate mod ID: {mod_id}")
            mod_owners[mod_id.casefold()] = path.name
        digest_rows.append(expected_row)
    digest_rows.sort(key=lambda row: row["file"].casefold())
    if builder.bundle_digest(digest_rows) != EXPECTED_RUNTIME_BUNDLE_SHA256:
        raise ValueError("Candidate11 computed runtime bundle digest mismatch")

    approved = {
        item["file"]: item for item in expected["approved_jar_transforms"]
    }
    jar_changes = [
        item
        for item in sanitization.get("changes", [])
        if isinstance(item, dict) and item.get("kind") == "jar-resource-sanitize"
    ]
    if len(jar_changes) != 2 or {
        Path(str(item.get("path", ""))).name for item in jar_changes
    } != set(approved):
        raise ValueError("Candidate11 sanitizer JAR-change set mismatch")
    for item in jar_changes:
        name = Path(str(item["path"])).name
        contract = approved[name]
        if (
            Path(str(item["path"])).resolve() != mods / name
            or str(item.get("before_sha256", "")).upper()
            != contract["before_sha256"]
            or str(item.get("after_sha256", "")).upper()
            != contract["after_sha256"]
        ):
            raise ValueError(f"Candidate11 sanitizer evidence mismatch: {name}")
    for guard_name in (
        builder.CC_COMPAT_LOCK.file,
        builder.GUARD_LOCK.file,
    ):
        runtime_row = expected_by_name[guard_name.casefold()]
        source_row = source["jars"][guard_name]
        if (
            runtime_row["source_comparison"] != "byte_identical"
            or runtime_row["bytes"] != source_row["bytes"]
            or runtime_row["sha256"].lower() != source_row["sha256"]
        ):
            raise ValueError(f"Candidate11 guard changed during sanitization: {guard_name}")
    return {
        "status": "PASS",
        "source_bundle_sha256": source["bundle_sha256"],
        "runtime_bundle_sha256": EXPECTED_RUNTIME_BUNDLE_SHA256,
        "mods_path": str(mods),
        "prepare_report": str(prepare_report),
        "file_count": 52,
        "bytes": EXPECTED_RUNTIME_BYTES,
        "approved_jar_transforms": sorted(approved),
        "new_guards_byte_identical": True,
        "duplicate_mod_ids": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    published_parser = subparsers.add_parser("published")
    published_parser.add_argument("--mods", type=Path)
    runtime_parser = subparsers.add_parser("runtime")
    runtime_parser.add_argument("--mods", type=Path, required=True)
    runtime_parser.add_argument("--prepare-report", type=Path, required=True)
    args = parser.parse_args()
    result = (
        published(args.mods)
        if args.command == "published"
        else runtime(args.mods, args.prepare_report)
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
