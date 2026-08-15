#!/usr/bin/env python3
"""Read-only validator for the Candidate14 known-error-family OTA matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = WORKSPACE / "outputs/candidate14-ota-error-family-coverage-20260812.json"
DEFAULT_REPORT = WORKSPACE / "outputs/candidate14-ota-error-family-validation-20260812.json"
CLASSES = {"client_only_ota", "both_side_mod_update", "server_only_data_migration"}


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def validate(matrix: dict[str, Any], matrix_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    families = matrix.get("families")
    require(matrix.get("schema") == 1, errors, "schema must be 1")
    require(matrix.get("status") == "PASS_KNOWN_ERROR_FAMILY_COVERAGE", errors, "matrix status is not PASS")
    require(isinstance(families, list) and bool(families), errors, "families missing")
    ids: list[str] = []
    counts = {name: 0 for name in sorted(CLASSES)}
    if isinstance(families, list):
        for index, row in enumerate(families):
            prefix = f"families[{index}]"
            require(isinstance(row, dict), errors, f"{prefix}: not an object")
            if not isinstance(row, dict):
                continue
            item_id = row.get("id")
            route_class = row.get("route_class")
            ids.append(item_id if isinstance(item_id, str) else "")
            require(isinstance(item_id, str) and bool(item_id.strip()), errors, f"{prefix}: id missing")
            require(route_class in CLASSES, errors, f"{prefix}: invalid route_class {route_class!r}")
            if route_class in counts:
                counts[route_class] += 1
            for key in ("title", "priority", "state", "route", "startup_blocker"):
                require(isinstance(row.get(key), str) and bool(row[key].strip()), errors, f"{prefix}: {key} missing")
            require(isinstance(row.get("mcmodsync_alone"), bool), errors, f"{prefix}: mcmodsync_alone must be bool")
            require(isinstance(row.get("data_mutation"), bool), errors, f"{prefix}: data_mutation must be bool")
            require(isinstance(row.get("external_dependency"), bool), errors, f"{prefix}: external_dependency must be bool")
            for key in ("requires_client_exit", "requires_server_short_shutdown"):
                require(isinstance(row.get(key), bool), errors, f"{prefix}: {key} must be bool")
            if route_class == "client_only_ota":
                # A client-only artifact is delivered by MCModSync, but the
                # publication/supply-chain control plane may still be a
                # separate dependency (HTTPS origin, Config.jar, canary).
                # Such a family is explicitly marked external_dependency.
                require(
                    row.get("mcmodsync_alone") is True or row.get("external_dependency") is True,
                    errors,
                    f"{prefix}: client-only route must support MCModSync or declare an external publication dependency",
                )
                require(row.get("requires_client_exit") is True, errors, f"{prefix}: client-only route needs client exit")
                require(row.get("requires_server_short_shutdown") is False, errors, f"{prefix}: client-only route cannot need server stop")
                require(row.get("data_mutation") is False, errors, f"{prefix}: client-only route cannot mutate data")
            elif route_class == "both_side_mod_update":
                require(row.get("mcmodsync_alone") is False, errors, f"{prefix}: BOTH route cannot claim MCModSync alone")
                require(row.get("requires_client_exit") is True, errors, f"{prefix}: BOTH route needs client exit")
                require(row.get("requires_server_short_shutdown") is True, errors, f"{prefix}: BOTH route needs server stop")
            elif route_class == "server_only_data_migration":
                require(row.get("mcmodsync_alone") is False, errors, f"{prefix}: data route cannot claim MCModSync alone")
                require(row.get("requires_client_exit") is False, errors, f"{prefix}: data route must not require client exit")
                require(row.get("requires_server_short_shutdown") is True, errors, f"{prefix}: data route needs server stop")
                require(row.get("data_mutation") is True, errors, f"{prefix}: data route must declare mutation")
        require(len(ids) == len(set(ids)), errors, "family IDs are not unique")
        for route_class, count in counts.items():
            require(count > 0, errors, f"no family for route class {route_class}")

    invariants = matrix.get("invariants")
    require(isinstance(invariants, dict), errors, "invariants missing")
    if isinstance(invariants, dict):
        for key in (
            "every_family_has_route",
            "every_family_has_class",
            "every_data_mutation_has_snapshot_and_sidecar",
            "every_client_only_route_preserves_user_resource_pack",
            "every_both_side_route_requires_pair_lock",
            "unknown_family_is_no_go",
            "current_mod_count_is_not_a_permanent_cap",
            "production_server_properties_byte_identical",
        ):
            require(invariants.get(key) is True, errors, f"invariant {key} must be true")

    not_errors = matrix.get("not_independent_errors")
    require(isinstance(not_errors, list) and bool(not_errors), errors, "not_independent_errors missing")
    if isinstance(not_errors, list):
        for index, row in enumerate(not_errors):
            require(isinstance(row, dict), errors, f"not_independent_errors[{index}] is not an object")
            if isinstance(row, dict):
                for key in ("id", "reason", "handling"):
                    require(isinstance(row.get(key), str) and bool(row[key].strip()), errors, f"not_independent_errors[{index}].{key} missing")

    return {
        "schema": 1,
        "status": "PASS" if not errors else "NO_GO",
        "category": "candidate14_ota_error_family_static_validation",
        "read_only": True,
        "java_started": False,
        "network_used": False,
        "ports_bound": False,
        "matrix": str(matrix_path),
        "matrix_sha256": sha256(matrix_path),
        "family_count": len(families) if isinstance(families, list) else 0,
        "class_counts": counts,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    matrix_path = args.matrix.resolve()
    report = validate(load(matrix_path), matrix_path)
    if not args.check_only:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(stable_json(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
