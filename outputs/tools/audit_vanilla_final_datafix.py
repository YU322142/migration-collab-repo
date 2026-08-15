#!/usr/bin/env python3
"""Read-only closure audit for map, advancement, and schematic migration data.

The audit deliberately never invokes a converter transaction.  It derives the
deterministic desired bytes in memory, compares them with staging, validates
the replay ledgers, and brackets all work with a full hash of the touched
source scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import stat

import convert_player_advancements as advancements
import convert_vanilla_saveddata as saveddata
import prepare_fast_migration as migration


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _regular(path: Path, label: str) -> None:
    """Reject links/devices before any read (all audit inputs are fail-closed)."""
    if path.is_symlink() or not path.exists():
        raise RuntimeError(f"{label} is missing or symbolic: {path}")
    if not stat.S_ISREG(path.stat().st_mode):
        raise RuntimeError(f"{label} is not a regular file: {path}")


def tree_manifest(paths: list[tuple[str, Path]]) -> dict:
    records = []
    digest = hashlib.sha256()
    for relative, path in sorted(paths):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"required regular source file is missing: {path}")
        before = path.stat()
        record = {
            "path": relative,
            "bytes": before.st_size,
            "sha256": sha256(path),
        }
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(f"source changed while hashing: {path}")
        records.append(record)
        for value in (record["path"], str(record["bytes"]), record["sha256"]):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
    return {
        "files": len(records),
        "bytes": sum(record["bytes"] for record in records),
        "content_sha256": digest.hexdigest().upper(),
        "entries": records,
    }


def source_scope_manifest(source: Path) -> dict:
    paths = []
    for path in sorted((source / "world" / "data").glob("map_*.dat")):
        paths.append((path.relative_to(source).as_posix(), path))
    for path in sorted((source / "world" / "advancements").glob("*.json")):
        paths.append((path.relative_to(source).as_posix(), path))
    for path in migration.iter_files(source / "schematics"):
        paths.append((path.relative_to(source).as_posix(), path))
    return tree_manifest(paths)


def expected_map_ledger(source: Path) -> tuple[bytes, dict[str, dict]]:
    records = []
    metrics = {}
    for source_path in sorted(
        (source / "world" / "data").glob("map_*.dat"),
        key=lambda path: int(saveddata.MAP_FILE_NAME.fullmatch(path.name).group(1)),
    ):
        match = saveddata.MAP_FILE_NAME.fullmatch(source_path.name)
        if match is None:
            raise RuntimeError(f"invalid source map file name: {source_path.name}")
        desired, metric = saveddata.convert_map(source_path)
        metrics[source_path.name] = metric
        if metric["banners_added"]:
            records.append(
                {
                    "schema": 1,
                    "record_type": "map_banner_missing_field",
                    "dimension": str(desired["data"].get("dimension", "unknown")),
                    "map_id": int(match.group(1)),
                    "source_file": f"world/data/{source_path.name}",
                    "source_sha256": metric["source_sha256"],
                    "banner_index": None,
                    "repair": "add-empty-banners-list",
                    "frames_preserved": metric["frames"],
                    "other_fields_preserved": True,
                }
            )
    payload = b"".join(
        (
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        for record in sorted(records, key=lambda record: record["map_id"])
    )
    return payload, metrics


def audit_maps(source: Path, staging: Path) -> dict:
    source_dir = source / "world" / "data"
    target_dir = staging / "world" / "data"
    source_paths = sorted(source_dir.glob("map_*.dat"))
    target_paths = sorted(target_dir.glob("map_*.dat"))
    for path in source_paths:
        _regular(path, "source map")
    for path in target_paths:
        _regular(path, "target map")
    source_names = {path.name for path in source_paths}
    target_names = {path.name for path in target_paths}
    if source_names != target_names:
        raise RuntimeError(
            "map file set mismatch: "
            f"missing={sorted(source_names - target_names)}, "
            f"extra={sorted(target_names - source_names)}"
        )

    expected_ledger, metrics = expected_map_ledger(source)
    mismatched = []
    staging_records = {}
    for source_path in source_paths:
        desired, _ = saveddata.convert_map(source_path)
        target_path = target_dir / source_path.name
        actual = saveddata.load_nbt(target_path)
        if saveddata.typed(actual) != saveddata.typed(desired):
            mismatched.append(source_path.name)
        staging_records[source_path.name] = {
            "sha256": sha256(target_path),
            "bytes": target_path.stat().st_size,
        }
    if mismatched:
        raise RuntimeError(f"staging maps differ from deterministic repair: {mismatched}")

    ledger_path = staging / saveddata.MAP_SIDECAR_RELATIVE
    if not ledger_path.is_file() or ledger_path.is_symlink():
        raise RuntimeError(f"map banner ledger is missing or invalid: {ledger_path}")
    actual_ledger = ledger_path.read_bytes()
    if actual_ledger != expected_ledger:
        raise RuntimeError("map banner ledger differs from the deterministic source plan")

    return {
        "status": "MATCH",
        "maps": len(source_paths),
        "missing_banners_in_source": sum(
            bool(metric["banners_added"]) for metric in metrics.values()
        ),
        "already_had_banners_in_source": sum(
            not metric["banners_added"] for metric in metrics.values()
        ),
        "semantic_mismatches": 0,
        "ledger_records": expected_ledger.count(b"\n"),
        "ledger_path": str(ledger_path),
        "ledger_sha256": sha256(ledger_path),
        "source_records": metrics,
        "staging_records": staging_records,
    }


def audit_advancements(source: Path, staging: Path, policy: Path) -> dict:
    plan = advancements.build_plan(source, staging, policy)
    planned = plan.pop("plans")
    source_dir = source / "world" / "advancements"
    target_dir = staging / "world" / "advancements"
    source_files = sorted(source_dir.glob("*.json"))
    target_files = sorted(target_dir.glob("*.json"))
    for path in source_files:
        _regular(path, "source advancement")
    for path in target_files:
        _regular(path, "target advancement")
    source_names = {path.name for path in source_files}
    target_names = {path.name for path in target_files}
    if source_names != target_names:
        raise RuntimeError(
            "advancement player file set mismatch: "
            f"missing={sorted(source_names - target_names)}, "
            f"extra={sorted(target_names - source_names)}"
        )

    outputs = []
    file_outputs = []
    affected_names = {
        path.name
        for path in planned
        if path.parent.resolve() == target_dir.resolve()
    }
    for source_path in source_files:
        target_path = target_dir / source_path.name
        source_bytes = source_path.read_bytes()
        target_bytes = target_path.read_bytes()
        if source_path.name in affected_names:
            desired_bytes = planned[target_path]
            if target_bytes != desired_bytes:
                raise RuntimeError(
                    f"affected advancement output differs from deterministic plan: {target_path}"
                )
            expected_bytes = desired_bytes
        else:
            if target_bytes != source_bytes:
                raise RuntimeError(
                    f"unaffected advancement file is not byte-exact source copy: {target_path}"
                )
            expected_bytes = source_bytes
        file_outputs.append(
            {
                "path": str(target_path),
                "player_file": source_path.name,
                "affected": source_path.name in affected_names,
                "byte_exact_source": target_bytes == source_bytes,
                "bytes": len(expected_bytes),
                "sha256": advancements.bytes_sha256(expected_bytes),
            }
        )

    for path, payload in sorted(planned.items(), key=lambda item: str(item[0])):
        outputs.append(
            {
                "path": str(path),
                "changed": not path.is_file() or path.read_bytes() != payload,
                "sha256": advancements.bytes_sha256(payload),
                "bytes": len(payload),
            }
        )
    sidecar_path = staging / advancements.SIDECAR_RELATIVE
    sidecar_output = next(
        (item for item in outputs if Path(item["path"]).resolve() == sidecar_path.resolve()),
        None,
    )
    if sidecar_output is None:
        raise RuntimeError("advancement sidecar is not part of the deterministic output plan")
    return {
        "status": "WOULD_CONVERT"
        if any(output["changed"] for output in outputs)
        else "ALREADY_TARGET",
        **plan,
        "outputs": outputs,
        "file_outputs": file_outputs,
        "source_file_set_exact": True,
        "target_file_set_exact": True,
        "unaffected_files_byte_exact": all(
            item["byte_exact_source"] for item in file_outputs if not item["affected"]
        ),
        "changed_outputs": sum(output["changed"] for output in outputs),
    }


def audit_schematic_references(source: Path, staging: Path, report_path: Path) -> dict:
    _regular(report_path, "schematic reference report")
    value = json.loads(report_path.read_text(encoding="utf-8"))
    if value.get("source_game_dir") != str(source.resolve()):
        raise RuntimeError("schematic reference report source root is not bound to current source")
    if value.get("target_game_dir") != str(staging.resolve()):
        raise RuntimeError("schematic reference report target root is not bound to current staging")
    present = value.get("schematic_files")
    inherited = value.get("inherited_missing_schematic_files")
    if not isinstance(present, list) or not isinstance(inherited, list):
        raise RuntimeError("schematic reference audit has invalid reference lists")
    verified = []
    source_schematics = (source / "schematics").resolve()
    target_schematics = (staging / "schematics").resolve()
    for index, record in enumerate(present):
        if not isinstance(record, dict):
            raise RuntimeError(f"schematic reference record {index} is not an object")
        source_path = Path(str(record.get("source_resolved", ""))).resolve()
        owner = record.get("owner")
        filename = record.get("file")
        if not isinstance(owner, str) or not isinstance(filename, str) or not owner or not filename:
            raise RuntimeError(f"schematic reference {index} has invalid owner/file")
        expected_source = (source_schematics / "uploaded" / owner / filename).resolve()
        if source_path != expected_source:
            raise RuntimeError(
                f"schematic reference path does not match owner/file: {source_path}"
            )
        try:
            relative = source_path.relative_to(source_schematics)
        except ValueError as exc:
            raise RuntimeError(
                f"schematic reference escapes the authoritative tree: {source_path}"
            ) from exc
        target_path = (target_schematics / relative).resolve()
        _regular(source_path, "source-present schematic")
        _regular(target_path, "target schematic")
        if not source_path.is_file() or not target_path.is_file():
            raise RuntimeError(
                f"source-present schematic is missing from staging: {relative.as_posix()}"
            )
        source_hash = sha256(source_path)
        target_hash = sha256(target_path)
        expected_hash = str(record.get("source_sha256", "")).upper()
        if source_hash != expected_hash or target_hash != source_hash:
            raise RuntimeError(
                f"source-present schematic hash mismatch: {relative.as_posix()}"
            )
        verified.append(
            {
                "path": relative.as_posix(),
                "bytes": source_path.stat().st_size,
                "sha256": source_hash,
            }
        )
    inherited_verified = []
    for index, record in enumerate(inherited):
        if not isinstance(record, dict):
            raise RuntimeError(f"inherited schematic record {index} is not an object")
        source_path = Path(str(record.get("source_resolved", ""))).resolve()
        owner = record.get("owner")
        filename = record.get("file")
        if not isinstance(owner, str) or not isinstance(filename, str) or not owner or not filename:
            raise RuntimeError(f"inherited schematic reference {index} has invalid owner/file")
        expected_source = (source_schematics / "uploaded" / owner / filename).resolve()
        if source_path != expected_source:
            raise RuntimeError(
                f"inherited schematic path does not match owner/file: {source_path}"
            )
        try:
            source_path.relative_to(source_schematics)
        except ValueError as exc:
            raise RuntimeError(
                f"inherited schematic path escapes source schematics: {source_path}"
            ) from exc
        if source_path.is_symlink() or source_path.is_file():
            raise RuntimeError(
                f"schematic marked inherited-missing is now present: {source_path}"
            )
        inherited_verified.append(
            {
                "owner": record.get("owner"),
                "file": record.get("file"),
                "source_exists": False,
                "reason": record.get("reason"),
            }
        )
    return {
        "status": "MATCH",
        "evidence_report": str(report_path.resolve()),
        "evidence_report_sha256": sha256(report_path),
        "source_present_references": len(verified),
        "source_present_verified": verified,
        "inherited_source_missing_references": len(inherited_verified),
        "inherited_source_missing_verified": inherited_verified,
    }


def audit(
    source: Path,
    staging: Path,
    policy: Path,
    schematic_reference_report: Path | None,
) -> dict:
    before = source_scope_manifest(source)
    result = {
        "schema": 1,
        "status": "AUDIT_IN_PROGRESS",
        "source_game_dir": str(source),
        "staging_game_dir": str(staging),
        "source_scope_before": before,
        "maps": audit_maps(source, staging),
        "advancements": audit_advancements(source, staging, policy),
        "schematics": migration.validate_schematic_tree_copy(source, staging),
    }
    if schematic_reference_report is not None:
        result["schematic_references"] = audit_schematic_references(
            source, staging, schematic_reference_report
        )
    after = source_scope_manifest(source)
    result["source_scope_after"] = after
    result["source_scope_unchanged"] = before == after
    if before != after:
        raise RuntimeError("authoritative source changed during final data-fix audit")
    result["status"] = "PASS"
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-game-dir", type=Path, required=True)
    parser.add_argument("--staging-game-dir", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).with_name("advancement_id_policy_20260813.json"),
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--schematic-reference-report", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report_path = args.report.resolve()
    try:
        result = audit(
            args.source_game_dir.resolve(),
            args.staging_game_dir.resolve(),
            args.policy.resolve(),
            args.schematic_reference_report.resolve()
            if args.schematic_reference_report is not None
            else None,
        )
    except Exception as exc:
        result = {
            "schema": 1,
            "status": "BLOCKED",
            "source_game_dir": str(args.source_game_dir.resolve()),
            "staging_game_dir": str(args.staging_game_dir.resolve()),
            "blockers": [f"{type(exc).__name__}: {exc}"],
        }
        migration.atomic_json(report_path, result)
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 2
    migration.atomic_json(report_path, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": str(report_path),
                "maps": result["maps"]["maps"],
                "map_ledger_records": result["maps"]["ledger_records"],
                "advancement_status": result["advancements"]["status"],
                "advancement_occurrences": result["advancements"]["occurrences"],
                "schematic_files": result["schematics"]["files"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
