#!/usr/bin/env python3
"""Fail-closed audit of migrated player stats against a target registry dump.

The source JSON is useful evidence, but it cannot prove that a target mod has
actually registered an item/entity/block.  Therefore a registry manifest is
required for PASS.  Running without one intentionally emits a complete
inventory with BLOCKED status instead of guessing from resource-pack files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


TOOL_VERSION = "1"
STAT_TYPE_TO_REGISTRY = {
    "minecraft:mined": "minecraft:block",
    "minecraft:crafted": "minecraft:item",
    "minecraft:used": "minecraft:item",
    "minecraft:broken": "minecraft:item",
    "minecraft:picked_up": "minecraft:item",
    "minecraft:dropped": "minecraft:item",
    "minecraft:killed": "minecraft:entity_type",
    "minecraft:killed_by": "minecraft:entity_type",
    "minecraft:custom": "minecraft:custom_stat",
}
NAMESPACE_ID = re.compile(r"^[a-z0-9_.-]+:[a-z0-9/._-]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


class AuditError(Exception):
    pass


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot parse {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_source(stats_dir: Path) -> tuple[dict[str, dict[str, int]], list[dict[str, Any]], list[str]]:
    if not stats_dir.is_dir():
        raise AuditError(f"stats directory does not exist: {stats_dir}")

    inventory: dict[str, dict[str, int]] = {}
    file_records: list[dict[str, Any]] = []
    errors: list[str] = []
    files = sorted(stats_dir.glob("*.json"), key=lambda path: path.name)
    if not files:
        raise AuditError(f"no player stats JSON files found in {stats_dir}")

    for path in files:
        try:
            document = read_json(path)
            stats = document.get("stats")
            if not isinstance(stats, dict):
                raise AuditError("top-level stats object is missing")
            file_types: set[str] = set()
            for stat_type, values in stats.items():
                if stat_type not in STAT_TYPE_TO_REGISTRY:
                    raise AuditError(f"unknown statistic type {stat_type!r}")
                if not isinstance(values, dict):
                    raise AuditError(f"statistic type {stat_type!r} is not an object")
                file_types.add(stat_type)
                bucket = inventory.setdefault(stat_type, {})
                for identifier, value in values.items():
                    if not isinstance(identifier, str) or not NAMESPACE_ID.fullmatch(identifier):
                        raise AuditError(f"invalid statistic identifier {identifier!r}")
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        raise AuditError(f"invalid value for {stat_type}:{identifier}")
                    bucket[identifier] = bucket.get(identifier, 0) + 1
            file_records.append({
                "file": path.name,
                "sha256": sha256_file(path),
                "stat_types": sorted(file_types),
            })
        except AuditError as exc:
            errors.append(f"{path.name}: {exc}")

    return inventory, file_records, errors


def load_runtime_manifest(path: Path) -> tuple[dict[str, set[str]], list[str], dict[str, Any]]:
    """Read the attested target registry dump described in the report docs."""
    document = read_json(path)
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise AuditError("registry manifest schema must be integer 1")
    evidence = document.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("kind") != "runtime-registry-dump":
        raise AuditError("registry manifest evidence.kind must be runtime-registry-dump")
    evidence_hash = evidence.get("sha256")
    if not isinstance(evidence_hash, str) or not SHA256.fullmatch(evidence_hash):
        raise AuditError("registry manifest evidence.sha256 must be a 64-digit hash")

    registries = document.get("registries")
    if not isinstance(registries, dict):
        raise AuditError("registry manifest registries object is missing")
    result: dict[str, set[str]] = {}
    errors: list[str] = []
    for registry_name in sorted(set(STAT_TYPE_TO_REGISTRY.values())):
        values = registries.get(registry_name)
        if not isinstance(values, list) or not values or not all(isinstance(value, str) for value in values):
            errors.append(f"missing or invalid registry list: {registry_name}")
            continue
        invalid = [value for value in values if not NAMESPACE_ID.fullmatch(value)]
        if invalid:
            errors.append(f"invalid IDs in {registry_name}: {invalid[:3]}")
        result[registry_name] = set(values)
    return result, errors, {
        "kind": evidence["kind"],
        "sha256": evidence_hash.lower(),
    }


def load_runtime_dumps(directory: Path) -> tuple[dict[str, set[str]], list[str], dict[str, Any]]:
    """Read NeoForge `/neoforge dump registry` text files directly."""
    if not directory.is_dir():
        raise AuditError(f"registry dump directory does not exist: {directory}")
    result: dict[str, set[str]] = {}
    errors: list[str] = []
    digest = hashlib.sha256()
    for registry_name in sorted(set(STAT_TYPE_TO_REGISTRY.values())):
        namespace, path = registry_name.split(":", 1)
        dump_path = directory / namespace / f"{path}.txt"
        if not dump_path.is_file():
            errors.append(f"missing registry dump: {dump_path}")
            continue
        values: set[str] = set()
        try:
            lines = dump_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read {dump_path}: {exc}")
            continue
        for line in lines:
            value = line.strip()
            if value:
                values.add(value.split(" - ", 1)[-1])
        if not values:
            errors.append(f"empty registry dump: {dump_path}")
        result[registry_name] = values
        digest.update(str(dump_path.relative_to(directory)).replace("\\", "/").encode("utf-8"))
        digest.update(sha256_file(dump_path).encode("ascii"))
    return result, errors, {
        "kind": "runtime-registry-dump",
        "sha256": digest.hexdigest(),
        "directory": str(directory),
    }


def build_report(
    stats_dir: Path,
    manifest_path: Path | None,
    dump_directory: Path | None,
) -> tuple[dict[str, Any], int]:
    inventory, file_records, source_errors = inventory_source(stats_dir)
    blockers = list(source_errors)
    manifest_errors: list[str] = []
    registries: dict[str, set[str]] = {}
    target_evidence: dict[str, Any] | None = None
    if manifest_path is not None and dump_directory is not None:
        blockers.append("choose either --target-manifest or --target-dump-dir, not both")
    elif dump_directory is not None:
        try:
            registries, manifest_errors, target_evidence = load_runtime_dumps(dump_directory)
            blockers.extend(manifest_errors)
        except AuditError as exc:
            blockers.append(str(exc))
    elif manifest_path is None:
        blockers.append("no runtime registry manifest supplied; static resource presence is not registry proof")
    else:
        try:
            registries, manifest_errors, target_evidence = load_runtime_manifest(manifest_path)
            blockers.extend(manifest_errors)
        except AuditError as exc:
            blockers.append(str(exc))

    missing: dict[str, list[dict[str, Any]]] = {}
    if registries:
        for stat_type, values in sorted(inventory.items()):
            registry = registries.get(STAT_TYPE_TO_REGISTRY[stat_type], set())
            absent = [
                {"id": identifier, "files": count}
                for identifier, count in sorted(values.items())
                if identifier not in registry
            ]
            if absent:
                missing[stat_type] = absent
        if missing:
            blockers.append("one or more source statistic IDs are absent from the target registry manifest")

    aggregate = hashlib.sha256()
    for record in file_records:
        aggregate.update(record["file"].encode("utf-8"))
        aggregate.update(record["sha256"].encode("ascii"))

    type_summary = {}
    for stat_type, values in sorted(inventory.items()):
        type_summary[stat_type] = {
            "target_registry": STAT_TYPE_TO_REGISTRY[stat_type],
            "unique_ids": len(values),
            "references": sum(values.values()),
            "ids": [
                {"id": identifier, "files": count}
                for identifier, count in sorted(values.items())
            ],
        }

    report: dict[str, Any] = {
        "tool": "audit_player_stats_registry.py",
        "tool_version": TOOL_VERSION,
        "status": "PASS" if not blockers else "BLOCKED",
        "blockers": blockers,
        "source": {
            "stats_directory": str(stats_dir),
            "json_files": len(file_records) + len(source_errors),
            "parsed_files": len(file_records),
            "aggregate_sha256": aggregate.hexdigest(),
            "files": file_records,
            "types": type_summary,
        },
        "target": {
            "manifest": str(manifest_path) if manifest_path else None,
            "dump_directory": str(dump_directory) if dump_directory else None,
            "evidence": target_evidence,
            "required_evidence": "runtime-registry-dump with a SHA-256 attestation",
            "missing": missing,
        },
        "interpretation": {
            "custom_stat_ids_seen": {
                identifier: count
                for identifier, count in sorted(inventory.get("minecraft:custom", {}).items())
                if identifier in {"minecraft:happy_ghast_one_cm", "minecraft:nautilus_one_cm"}
            },
            "static_candidate_evidence_is_not_a_PASS": True,
        },
    }
    return report, 0 if report["status"] == "PASS" else 2


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats-dir", type=Path, required=True)
    parser.add_argument("--target-manifest", type=Path)
    parser.add_argument("--target-dump-dir", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        report, exit_code = build_report(args.stats_dir, args.target_manifest, args.target_dump_dir)
    except AuditError as exc:
        report = {
            "tool": "audit_player_stats_registry.py",
            "tool_version": TOOL_VERSION,
            "status": "BLOCKED",
            "blockers": [str(exc)],
        }
        exit_code = 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "report": str(args.report)}, ensure_ascii=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
