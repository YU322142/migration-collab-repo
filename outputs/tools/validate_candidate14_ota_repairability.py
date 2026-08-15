#!/usr/bin/env python3
"""Fail-closed static validator for Candidate14 OTA repairability.

This tool is deliberately read-only. It does not launch Java, bind ports, or
touch production/staging/world data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = WORKSPACE / "outputs/candidate14-ota-repairability-contract-20260812.json"
DEFAULT_REPORT = WORKSPACE / "outputs/candidate14-ota-repairability-validation-20260812.json"

VALID_CLASSES = {"client_only_ota", "both_side_mod_update", "server_only_data_migration"}
VALID_SIDES = {"client", "server", "both"}
DATA_CLASS = "server_only_data_migration"
BOTH_CLASS = "both_side_mod_update"
CLIENT_CLASS = "client_only_ota"


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _non_empty_strings(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def _validate_item(item: dict[str, Any], index: int, errors: list[str]) -> None:
    prefix = f"known_error_coverage[{index}]"
    item_id = item.get("id")
    _require(isinstance(item_id, str) and bool(item_id.strip()), errors, f"{prefix}: missing id")
    repair_class = item.get("class")
    side = item.get("affected_side")
    _require(repair_class in VALID_CLASSES, errors, f"{prefix}: invalid class {repair_class!r}")
    _require(side in VALID_SIDES, errors, f"{prefix}: invalid affected_side {side!r}")
    _require(_non_empty_strings(item.get("startup_blockers")), errors, f"{prefix}: startup_blockers missing")

    stable = item.get("stable_identity")
    _require(isinstance(stable, dict) and bool(stable), errors, f"{prefix}: stable_identity missing")
    _require(
        isinstance(stable, dict) and isinstance(stable.get("sidecar"), str) and bool(stable["sidecar"].strip()),
        errors,
        f"{prefix}: stable_identity.sidecar missing",
    )

    evidence = item.get("evidence")
    _require(isinstance(evidence, list) and bool(evidence), errors, f"{prefix}: evidence missing")
    if isinstance(evidence, list):
        for eindex, row in enumerate(evidence):
            _require(isinstance(row, dict), errors, f"{prefix}.evidence[{eindex}]: not an object")
            if not isinstance(row, dict):
                continue
            path = row.get("path")
            _require(isinstance(path, str) and bool(path.strip()), errors, f"{prefix}.evidence[{eindex}]: path missing")
            if isinstance(path, str) and path.startswith("outputs/"):
                _require((WORKSPACE / path).is_file(), errors, f"{prefix}.evidence[{eindex}]: missing local evidence {path}")

    route = item.get("ota_route")
    _require(isinstance(route, dict), errors, f"{prefix}: ota_route missing")
    if isinstance(route, dict):
        for key in (
            "delivery",
            "artifact_kind",
            "requires_client_exit",
            "requires_server_short_shutdown",
            "world_mutation_allowed",
            "world_snapshot_required",
        ):
            _require(key in route, errors, f"{prefix}: ota_route.{key} missing")

    repair = item.get("repair_contract")
    _require(isinstance(repair, dict), errors, f"{prefix}: repair_contract missing")
    if isinstance(repair, dict):
        for key in ("preconditions", "actions", "postconditions", "rollback"):
            _require(_non_empty_strings(repair.get(key)), errors, f"{prefix}: repair_contract.{key} missing")
        marker = repair.get("idempotency_marker")
        _require(isinstance(marker, str) and bool(marker.strip()), errors, f"{prefix}: idempotency_marker missing")

    dependencies = item.get("dependencies")
    _require(isinstance(dependencies, dict), errors, f"{prefix}: dependencies missing")
    if isinstance(dependencies, dict):
        _require(dependencies.get("minecraft") == "1.21.1", errors, f"{prefix}: Minecraft version not locked")
        loader = dependencies.get("loader")
        _require(isinstance(loader, str) and loader.startswith("NeoForge "), errors, f"{prefix}: NeoForge dependency not locked")
        _require(isinstance(dependencies.get("required_mod_ids"), list), errors, f"{prefix}: required_mod_ids missing")
        _require(isinstance(dependencies.get("counterpart_required"), bool), errors, f"{prefix}: counterpart_required missing")

    mcmodsync_alone = item.get("mcmodsync_alone")
    _require(isinstance(mcmodsync_alone, bool), errors, f"{prefix}: mcmodsync_alone must be boolean")

    if repair_class == CLIENT_CLASS:
        _require(side == "client", errors, f"{prefix}: client_only_ota must affect client")
        _require(mcmodsync_alone is True, errors, f"{prefix}: client_only_ota must be deliverable by MCModSync")
        if isinstance(route, dict):
            _require(route.get("requires_client_exit") is True, errors, f"{prefix}: client OTA must require game exit")
            _require(route.get("requires_server_short_shutdown") is False, errors, f"{prefix}: client-only OTA cannot require server shutdown")
            _require(route.get("world_mutation_allowed") is False, errors, f"{prefix}: client-only OTA cannot mutate world data")
            _require(route.get("world_snapshot_required") is False, errors, f"{prefix}: client-only OTA should not claim a world snapshot")
    elif repair_class == BOTH_CLASS:
        _require(side == "both", errors, f"{prefix}: both_side_mod_update must affect both")
        _require(mcmodsync_alone is False, errors, f"{prefix}: BOTH-side repair cannot claim MCModSync alone")
        if isinstance(route, dict):
            _require(route.get("requires_client_exit") is True, errors, f"{prefix}: BOTH repair must require client exit")
            _require(route.get("requires_server_short_shutdown") is True, errors, f"{prefix}: BOTH repair must require server shutdown")
        if isinstance(dependencies, dict):
            _require(dependencies.get("counterpart_required") is True, errors, f"{prefix}: BOTH repair needs counterpart lock")
    elif repair_class == DATA_CLASS:
        _require(side == "server", errors, f"{prefix}: server/data migration must affect server")
        _require(mcmodsync_alone is False, errors, f"{prefix}: data migration cannot claim MCModSync alone")
        if isinstance(route, dict):
            _require(route.get("requires_server_short_shutdown") is True, errors, f"{prefix}: data migration must require stopped server")
            _require(route.get("world_mutation_allowed") is True, errors, f"{prefix}: data migration must explicitly authorize bounded mutation")
            _require(route.get("world_snapshot_required") is True, errors, f"{prefix}: data migration must require a snapshot")


def validate_contract(contract: dict[str, Any], contract_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    _require(contract.get("schema") == 1, errors, "schema must be 1")
    _require(contract.get("status") == "PASS_REPAIRABILITY_CONTRACT", errors, "contract status is not PASS")
    runtime = contract.get("runtime")
    _require(isinstance(runtime, dict), errors, "runtime lock missing")
    if isinstance(runtime, dict):
        _require(runtime.get("minecraft") == "1.21.1", errors, "runtime Minecraft mismatch")
        _require(runtime.get("loader") == "NeoForge", errors, "runtime loader mismatch")
        _require(runtime.get("loader_version") == "21.1.241", errors, "runtime loader version mismatch")
        _require(runtime.get("bundle_revision") == "candidate14-r3", errors, "bundle revision mismatch")

    classes = contract.get("repairability_classes")
    _require(isinstance(classes, dict), errors, "repairability_classes missing")
    if isinstance(classes, dict):
        _require(set(classes) == VALID_CLASSES, errors, "repairability_classes must contain exactly the three supported classes")

    items = contract.get("known_error_coverage")
    _require(isinstance(items, list) and bool(items), errors, "known_error_coverage missing")
    ids: list[str] = []
    counts = {name: 0 for name in sorted(VALID_CLASSES)}
    if isinstance(items, list):
        for index, item in enumerate(items):
            _require(isinstance(item, dict), errors, f"known_error_coverage[{index}]: not an object")
            if not isinstance(item, dict):
                continue
            _validate_item(item, index, errors)
            if isinstance(item.get("id"), str):
                ids.append(item["id"])
            if item.get("class") in counts:
                counts[item["class"]] += 1
        _require(len(ids) == len(set(ids)), errors, "known error IDs are not unique")
        for repair_class, count in counts.items():
            _require(count > 0, errors, f"no covered item for class {repair_class}")

    global_invariants = contract.get("global_invariants")
    _require(isinstance(global_invariants, dict), errors, "global_invariants missing")
    if isinstance(global_invariants, dict):
        required_true = (
            "source_data_never_deleted",
            "unknown_payloads_preserved_in_sidecar",
            "stable_registry_ids_never_reused",
            "stable_mod_ids_never_reused",
            "every_data_migration_has_idempotency_marker",
            "every_data_migration_has_world_snapshot",
            "every_ota_release_has_immutable_catalog_version",
            "every_ota_release_has_sha256_and_md5_per_object",
            "every_ota_release_has_independent_catalog_sha256",
            "rollback_keeps_prior_catalog_and_backups",
            "carrier_and_full_implementation_never_coexist",
            "production_server_properties_byte_identical",
        )
        for key in required_true:
            _require(global_invariants.get(key) is True, errors, f"global invariant {key} must be true")
        _require(global_invariants.get("resource_pack_ota") is False, errors, "resource pack OTA must remain disabled")
        _require(global_invariants.get("server_list_ota") is False, errors, "server-list OTA must remain disabled")
        _require(
            global_invariants.get("unknown_error_policy") == "NO_GO_AND_STARTUP_BLOCKED_UNTIL_CLASSIFIED",
            errors,
            "unknown errors must fail closed",
        )

    capability = contract.get("mcmodsync_capability_audit")
    _require(isinstance(capability, dict), errors, "mcmodsync_capability_audit missing")
    if isinstance(capability, dict):
        unsupported = capability.get("does_not_support")
        _require(isinstance(unsupported, list), errors, "MCModSync unsupported-capability list missing")
        if isinstance(unsupported, list):
            joined = "\n".join(str(row).lower() for row in unsupported)
            for phrase in ("server jar", "world/player nbt", "recipe-book", "advancement"):
                _require(phrase in joined, errors, f"MCModSync boundary missing: {phrase}")

    evidence_locks = contract.get("evidence_locks")
    _require(isinstance(evidence_locks, dict), errors, "evidence_locks missing")
    if isinstance(evidence_locks, dict):
        for key in ("readiness_json", "first_release_policy_json", "deferred_item_ledger_json", "deferred_guard_audit_json"):
            value = evidence_locks.get(key)
            _require(isinstance(value, str) and (WORKSPACE / value).is_file(), errors, f"evidence lock missing: {key}")
        _require(
            evidence_locks.get("production_properties_sha256")
            == "A71887512304BB526A125BD4F2CC835502456A3C8CB407AE73C8D02F1442552C",
            errors,
            "production server.properties lock mismatch",
        )

    if contract.get("deployment_status") != "INDEPENDENT_RUNTIME_GATE_PENDING":
        warnings.append("This validator does not prove runtime deployment readiness.")

    return {
        "schema": 1,
        "status": "PASS" if not errors else "NO_GO",
        "category": "candidate14_ota_repairability_static_validation",
        "read_only": True,
        "java_started": False,
        "network_used": False,
        "ports_bound": False,
        "contract": str(contract_path),
        "contract_sha256": sha256(contract_path),
        "known_error_count": len(items) if isinstance(items, list) else 0,
        "class_counts": counts,
        "errors": errors,
        "warnings": warnings,
        "runtime_gate_independent": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check-only", action="store_true")
    arguments = parser.parse_args(argv)

    contract_path = arguments.contract.resolve()
    report = validate_contract(load_json(contract_path), contract_path)
    if not arguments.check_only:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_bytes(stable_json(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
