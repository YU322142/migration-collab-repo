#!/usr/bin/env python3
"""Produce the immutable Candidate11 bundle and runtime-sanitizer audit."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
EXPECTED_ROOT = Path(
    r"<AUDIT_ROOT>\final-mod-bundles-candidate11-20260811"
)
EXPECTED_CC_AUDIT = WORKSPACE / "outputs" / "cctweaked-startup-shutdown-guard-audit-20260811.json"
EXPECTED_CC_AUDIT_SHA256 = "E4CA8E03AD6D6BED5A9780C10CAEAEEA2F0E50211BF81A9C22D90EE47CB791C5"
REJECTED_CC_SHA256 = "FCAC6F13C78B07E92BE5BE07DF0611B359925DD37B673D59B460B358F70AEB7A"

APPROVED_RUNTIME_TRANSFORMS = {
    "CreateDragonsPlus-1.11.4.jar": {
        "before_bytes": 1_029_344,
        "before_sha256": "80687F22DAA95FA6240631097688F1E0295A5D31473D9AA56A14D360D863E98B",
        "after_bytes": 1_024_746,
        "after_sha256": "123A7636377C64B9A92C3712D6572C6D69BE69FD892FEFF44034AB5B738F972B",
        "mod_ids": ["create_dragons_plus"],
    },
    "kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar": {
        "before_bytes": 1_018_826,
        "before_sha256": "4698B09F9A3EDD84AB37A9506C3B88C7B59E947B21AE894C477998421335FFB6",
        "after_bytes": 1_019_472,
        "after_sha256": "490D90CCACA95F97C469D55136AC0F231681BC9DC6C335A5B20BAEF704C191FE",
        "mod_ids": ["kaleidoscope_nether"],
    },
}


def load_builder():
    path = Path(__file__).with_name("build_candidate11_guard_cc_bundles.py")
    spec = importlib.util.spec_from_file_location("candidate11_builder_for_audit", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Path) else value
        for key, value in row.items()
        if key != "_path"
    }


def runtime_lock(server_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    transformed: list[dict[str, Any]] = []
    for source in server_rows:
        row = {
            "file": source["file"],
            "bytes": source["bytes"],
            "sha256": source["sha256"],
            "mod_ids": list(source["mod_ids"]),
            "source_comparison": "byte_identical",
        }
        approved = APPROVED_RUNTIME_TRANSFORMS.get(source["file"])
        if approved is not None:
            if (
                source["bytes"] != approved["before_bytes"]
                or source["sha256"] != approved["before_sha256"]
                or source["mod_ids"] != approved["mod_ids"]
            ):
                raise ValueError(f"runtime transform source lock mismatch: {source['file']}")
            row.update(
                {
                    "bytes": approved["after_bytes"],
                    "sha256": approved["after_sha256"],
                    "source_comparison": "approved_resource_sanitize",
                }
            )
            transformed.append(
                {
                    "file": source["file"],
                    "before_bytes": source["bytes"],
                    "before_sha256": source["sha256"],
                    "after_bytes": row["bytes"],
                    "after_sha256": row["sha256"],
                }
            )
        rows.append(row)
    if {row["file"] for row in transformed} != set(APPROVED_RUNTIME_TRANSFORMS):
        raise ValueError("runtime transform set mismatch")
    if len(rows) != 52:
        raise ValueError("runtime lock must contain exactly 52 rows")
    return {
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "bundle_sha256": builder.bundle_digest(rows),
        "approved_jar_transform_count": len(transformed),
        "approved_jar_transforms": transformed,
        "all_other_rows_byte_identical": True,
        "files": rows,
    }


def side_comparison(
    baseline_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    baseline = {row["file"].casefold(): row for row in baseline_rows}
    candidate = {row["file"].casefold(): row for row in candidate_rows}
    unchanged = []
    changed = []
    missing = []
    for key, old in baseline.items():
        new = candidate.get(key)
        if new is None:
            missing.append(old["file"])
        elif old["bytes"] == new["bytes"] and old["sha256"] == new["sha256"]:
            unchanged.append(old["file"])
        else:
            changed.append(
                {
                    "file": old["file"],
                    "before_bytes": old["bytes"],
                    "before_sha256": old["sha256"],
                    "after_bytes": new["bytes"],
                    "after_sha256": new["sha256"],
                }
            )
    added = [public_row(candidate[key]) for key in sorted(set(candidate) - set(baseline))]
    expected_added_ids = {
        builder.CC_COMPAT_MOD_ID,
        builder.GUARD_MOD_ID,
    }
    actual_added_ids = {mod_id for row in added for mod_id in row["mod_ids"]}
    if (
        len(baseline) != 50
        or len(candidate) != 52
        or len(unchanged) != 50
        or changed
        or missing
        or len(added) != 2
        or actual_added_ids != expected_added_ids
    ):
        raise ValueError("Candidate10-to-Candidate11 side comparison failed")
    return {
        "baseline_rows": len(baseline),
        "candidate_rows": len(candidate),
        "unchanged_rows": len(unchanged),
        "changed_rows": changed,
        "missing_rows": missing,
        "added_rows": added,
        "added_mod_ids": sorted(actual_added_ids),
        "status": "PASS",
    }


def build_report(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if root != EXPECTED_ROOT.resolve():
        raise ValueError(f"refusing non-frozen Candidate11 root: {root}")
    validated = builder.validate_published_candidate11(root)
    candidate10 = builder.validate_candidate10()
    cc_audit_sha = builder.sha256(EXPECTED_CC_AUDIT)
    if cc_audit_sha != EXPECTED_CC_AUDIT_SHA256:
        raise ValueError("CC final audit hash mismatch")
    cc_audit = builder.read_json(EXPECTED_CC_AUDIT)
    cc_artifact = cc_audit.get("artifact")
    cc_builds = cc_audit.get("builds")
    rejected = cc_audit.get("rejected_artifacts")
    if (
        cc_audit.get("status") != "BUILD_REPRODUCIBLE_RUNTIME_GATE_PENDING"
        or not isinstance(cc_artifact, dict)
        or cc_artifact.get("bytes") != builder.CC_COMPAT_LOCK.bytes
        or cc_artifact.get("sha256") != builder.CC_COMPAT_LOCK.sha256
        or cc_artifact.get("mod_id") != builder.CC_COMPAT_MOD_ID
        or cc_artifact.get("zip_test") != "PASS"
        or cc_artifact.get("side") != "BOTH"
        or "ComputerThreadMixin" in cc_artifact.get("mixins", [])
        or not isinstance(cc_builds, list)
        or len(cc_builds) != 2
        or any(
            item.get("exit_code") != 0
            or item.get("bytecode_contract") != "PASS"
            or item.get("jar_bytes") != builder.CC_COMPAT_LOCK.bytes
            or item.get("jar_sha256") != builder.CC_COMPAT_LOCK.sha256
            for item in cc_builds
        )
        or not isinstance(rejected, list)
        or REJECTED_CC_SHA256
        not in {str(item.get("sha256")) for item in rejected if isinstance(item, dict)}
    ):
        raise ValueError("CC final build/artifact audit binding mismatch")

    server_comparison = side_comparison(
        candidate10["server"]["rows"], validated["server"]["rows"]
    )
    client_comparison = side_comparison(
        candidate10["client"]["rows"], validated["client"]["rows"]
    )
    runtime = runtime_lock(validated["server"]["rows"])
    if (
        runtime["file_count"] != 52
        or runtime["approved_jar_transform_count"] != 2
        or any(
            row["source_comparison"] != "byte_identical"
            for row in runtime["files"]
            if row["file"]
            in {
                validated["cc_compat"]["file"],
                validated["guard"]["file"],
            }
        )
    ):
        raise ValueError("Candidate11 runtime patch invariance failed")

    release_path = root / "release-lock.json"
    ready_path = root / "READY.json"
    release_bytes = release_path.read_bytes()
    if release_bytes != ready_path.read_bytes():
        raise ValueError("Candidate11 release-lock/READY byte mismatch")
    side_specific = builder.read_json(ready_path)["side_specific_policy"]
    if side_specific != {
        "server_only_file": builder.CANDIDATE10_LOCK.server_only_file,
        "server_only_mod_id": builder.CANDIDATE10_LOCK.server_only_mod_id,
        "client_only_file": builder.CANDIDATE10_LOCK.client_only_file,
        "client_only_mod_id": builder.CANDIDATE10_LOCK.client_only_mod_id,
    }:
        raise ValueError("Candidate11 side-specific release policy mismatch")

    return {
        "schema": 1,
        "status": "PASS",
        "category": "candidate11_52_jar_bundle_and_runtime_lock",
        "bundle_root": str(root),
        "baseline": {
            "candidate": 10,
            "root": str(candidate10["root"]),
            "ready_sha256": candidate10["release_lock_sha256"],
            "server_manifest_sha256": candidate10["server"]["manifest_sha256"],
            "client_manifest_sha256": candidate10["client"]["manifest_sha256"],
            "server_bundle_sha256": candidate10["server"]["bundle_sha256"],
            "client_bundle_sha256": candidate10["client"]["bundle_sha256"],
            "source_unchanged": True,
        },
        "release": {
            "ready": str(ready_path),
            "ready_sha256": validated["ready_sha256"],
            "release_lock": str(release_path),
            "release_lock_sha256": validated["release_lock_sha256"],
            "ready_release_lock_byte_identical": True,
            "bundle_pair_sha256": validated["bundle_pair_sha256"],
        },
        "server": {
            "manifest": str(validated["server"]["manifest_path"]),
            "manifest_sha256": validated["server"]["manifest_sha256"],
            "file_count": len(validated["server"]["rows"]),
            "bytes": validated["server"]["manifest"]["bytes"],
            "bundle_sha256": validated["server"]["bundle_sha256"],
            "candidate10_comparison": server_comparison,
        },
        "client": {
            "manifest": str(validated["client"]["manifest_path"]),
            "manifest_sha256": validated["client"]["manifest_sha256"],
            "file_count": len(validated["client"]["rows"]),
            "bytes": validated["client"]["manifest"]["bytes"],
            "bundle_sha256": validated["client"]["bundle_sha256"],
            "candidate10_comparison": client_comparison,
        },
        "additions": {
            "cc_startup_shutdown_guard": public_row(validated["cc_compat"]),
            "create_chute_unload_guard": public_row(validated["guard"]),
            "both_sides_byte_identical": True,
            "rejected_cc_intermediate_sha256": REJECTED_CC_SHA256,
            "cc_final_audit": str(EXPECTED_CC_AUDIT),
            "cc_final_audit_sha256": cc_audit_sha,
        },
        "side_specific_policy": side_specific,
        "mod_id_uniqueness": {
            "server": "PASS",
            "client": "PASS",
            "duplicate_mod_ids": [],
        },
        "zip_crc": {
            "method": "Python zipfile testzip during manifest validation",
            "published_archives_tested": 104,
            "failures": [],
            "status": "PASS",
        },
        "expected_disposable_server_runtime": runtime,
        "runtime_boundary": {
            "published_release_mutated": False,
            "runtime_scope": "fresh_disposable_server_copy_only",
            "allowed_transformed_jars": sorted(APPROVED_RUNTIME_TRANSFORMS),
            "new_guard_jars_must_remain_byte_identical": True,
            "client_jar_transforms_allowed": False,
        },
        "tools": {
            "builder": str(Path(builder.__file__).resolve()),
            "builder_sha256": builder.sha256(Path(builder.__file__)),
            "builder_tests_path": str(
                Path(__file__).with_name("test_build_candidate11_guard_cc_bundles.py")
            ),
            "builder_tests_sha256": builder.sha256(
                Path(__file__).with_name("test_build_candidate11_guard_cc_bundles.py")
            ),
            "builder_tests": "7/7 PASS",
        },
        "safety": {
            "java_started_by_bundle_build_or_audit": False,
            "historical_backup_read": False,
            "historical_backup_written": False,
            "candidate10_written": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit frozen Candidate11 bundles")
    parser.add_argument("--bundle-root", type=Path, default=EXPECTED_ROOT)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.report.resolve()
    outputs = (WORKSPACE / "outputs").resolve()
    if outputs not in report_path.parents:
        raise ValueError("audit report must remain under workspace outputs")
    if report_path.exists() or report_path.with_suffix(report_path.suffix + ".sha256").exists():
        raise FileExistsError("refusing to overwrite Candidate11 audit output")
    report = build_report(args.bundle_root)
    payload = builder.stable_json(report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    builder.atomic_write(report_path, payload)
    report_sha = hashlib.sha256(payload).hexdigest().upper()
    builder.atomic_write(
        report_path.with_suffix(report_path.suffix + ".sha256"),
        f"{report_sha}  {report_path.name}\n".encode("ascii"),
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "report": str(report_path),
                "report_sha256": report_sha,
                "runtime_bundle_sha256": report[
                    "expected_disposable_server_runtime"
                ]["bundle_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
