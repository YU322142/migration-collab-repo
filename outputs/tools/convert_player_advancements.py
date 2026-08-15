#!/usr/bin/env python3
"""Fail-closed advancement ID migration with a replayable JSONL sidecar.

The stopped source is immutable.  Exact equivalents are renamed, entries with
no proven target equivalent are removed from the active target progress file
only after their complete payload is serialized to the migration ledger, and
unrelated player progress is preserved.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid


SIDECAR_RELATIVE = Path(".migration-ledger/advancement-unrecognized.v1.jsonl")
RESOURCE_LOCATION = re.compile(r"^[a-z0-9_.-]+:[a-z0-9/._-]+$")
PLAYER_FILE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json$"
)
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S %z"


class AdvancementConversionError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def stable_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise AdvancementConversionError(f"required regular JSON file is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdvancementConversionError(f"cannot parse JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdvancementConversionError(f"JSON root must be an object: {path}")
    return value


def load_policy(path: Path) -> tuple[dict, dict[str, dict], str]:
    value = load_json(path)
    if value.get("schema") != 1 or not isinstance(value.get("policy_id"), str):
        raise AdvancementConversionError("advancement policy has an unsupported schema")
    rules = value.get("rules")
    if not isinstance(rules, list):
        raise AdvancementConversionError("advancement policy rules must be a list")
    by_id: dict[str, dict] = {}
    targets: set[str] = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise AdvancementConversionError(f"policy rule {index} must be an object")
        old_id = rule.get("old_id")
        action = rule.get("action")
        reason = rule.get("reason")
        if not isinstance(old_id, str) or not RESOURCE_LOCATION.fullmatch(old_id):
            raise AdvancementConversionError(f"policy rule {index} has invalid old_id")
        if old_id in by_id:
            raise AdvancementConversionError(f"duplicate advancement policy rule: {old_id}")
        if action not in {"map", "sidecar"} or not isinstance(reason, str) or not reason:
            raise AdvancementConversionError(f"policy rule {old_id} is incomplete")
        target_id = rule.get("target_id")
        if action == "map":
            if not isinstance(target_id, str) or not RESOURCE_LOCATION.fullmatch(target_id):
                raise AdvancementConversionError(f"map rule {old_id} has invalid target_id")
            if target_id == old_id or target_id in targets:
                raise AdvancementConversionError(f"map rule has a duplicate/identity target: {old_id}")
            targets.add(target_id)
        elif target_id is not None:
            raise AdvancementConversionError(f"sidecar rule {old_id} must not have target_id")
        by_id[old_id] = copy.deepcopy(rule)
    expected = value.get("expected_rule_count")
    if expected != len(by_id):
        raise AdvancementConversionError(
            f"policy rule count mismatch: expected={expected!r}, actual={len(by_id)}"
        )
    return value, by_id, sha256(path)


def validate_progress(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise AdvancementConversionError(f"{label} must be an object")
    criteria = value.get("criteria")
    done = value.get("done")
    if not isinstance(criteria, dict) or type(done) is not bool:
        raise AdvancementConversionError(f"{label} must have criteria object and done boolean")
    for criterion, timestamp in criteria.items():
        if not isinstance(criterion, str) or not isinstance(timestamp, str):
            raise AdvancementConversionError(f"{label} criteria must map strings to timestamps")
        try:
            datetime.strptime(timestamp, TIMESTAMP_FORMAT)
        except ValueError as exc:
            raise AdvancementConversionError(
                f"{label} has an invalid criterion timestamp: {timestamp!r}"
            ) from exc
    return copy.deepcopy(value)


def earlier_timestamp(first: str, second: str) -> str:
    first_time = datetime.strptime(first, TIMESTAMP_FORMAT)
    second_time = datetime.strptime(second, TIMESTAMP_FORMAT)
    return first if first_time <= second_time else second


def merge_progress(first: dict, second: dict, label: str) -> dict:
    left = validate_progress(first, f"{label} source")
    right = validate_progress(second, f"{label} target")
    merged = copy.deepcopy(right)
    for key in set(left) | set(right):
        if key in {"criteria", "done"}:
            continue
        if key in left and key in right and left[key] != right[key]:
            raise AdvancementConversionError(
                f"{label} has conflicting unknown progress field {key!r}"
            )
        if key in left:
            merged[key] = copy.deepcopy(left[key])
    criteria = copy.deepcopy(right["criteria"])
    for name, timestamp in left["criteria"].items():
        if name in criteria:
            criteria[name] = earlier_timestamp(timestamp, criteria[name])
        else:
            criteria[name] = timestamp
    merged["criteria"] = criteria
    merged["done"] = bool(left["done"] or right["done"])
    return merged


def target_is_safe(path: Path, source_value: dict, desired_value: dict) -> None:
    if not path.exists():
        return
    target_value = load_json(path)
    if target_value not in (source_value, desired_value):
        raise AdvancementConversionError(
            "target advancement file has changes that are neither the stopped source "
            f"nor this converter's deterministic output: {path}"
        )


def sidecar_payload(records: list[dict]) -> bytes:
    return b"".join(
        (
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        for record in records
    )


def build_plan(source: Path, target: Path, policy_path: Path) -> dict:
    policy, rules, policy_hash = load_policy(policy_path)
    source_dir = source / "world" / "advancements"
    target_dir = target / "world" / "advancements"
    source_files = sorted(source_dir.glob("*.json")) if source_dir.is_dir() else []
    plans: dict[Path, bytes] = {}
    sidecar_records: list[dict] = []
    mapped_records: list[dict] = []
    occurrences = {old_id: 0 for old_id in rules}
    total_progress_entries = 0
    affected_files = 0
    for source_path in source_files:
        if source_path.is_symlink() or PLAYER_FILE.fullmatch(source_path.name) is None:
            raise AdvancementConversionError(
                f"unexpected advancement progress file name/type: {source_path}"
            )
        source_value = load_json(source_path)
        player_uuid = source_path.stem
        try:
            uuid.UUID(player_uuid)
        except ValueError as exc:
            raise AdvancementConversionError(f"invalid advancement player UUID: {player_uuid}") from exc
        desired = copy.deepcopy(source_value)
        source_hash = sha256(source_path)
        file_affected = False
        for advancement_id, progress in source_value.items():
            if advancement_id == "DataVersion":
                if type(progress) is not int:
                    raise AdvancementConversionError(
                        f"{source_path} DataVersion must be an integer"
                    )
                continue
            if not isinstance(advancement_id, str) or not RESOURCE_LOCATION.fullmatch(advancement_id):
                raise AdvancementConversionError(
                    f"{source_path} has invalid advancement ID {advancement_id!r}"
                )
            total_progress_entries += 1
            if advancement_id not in rules:
                continue
            normalized = validate_progress(progress, f"{source_path.name} {advancement_id}")
            rule = rules[advancement_id]
            occurrences[advancement_id] += 1
            file_affected = True
            if rule["action"] == "map":
                target_id = rule["target_id"]
                desired.pop(advancement_id)
                if target_id in desired:
                    desired[target_id] = merge_progress(
                        normalized,
                        desired[target_id],
                        f"{source_path.name} {advancement_id} -> {target_id}",
                    )
                else:
                    desired[target_id] = normalized
                mapped_records.append(
                    {
                        "player_uuid": player_uuid,
                        "source_file": source_path.name,
                        "source_file_sha256": source_hash,
                        "old_id": advancement_id,
                        "target_id": target_id,
                        "action": "map",
                        "reason": rule["reason"],
                    }
                )
            else:
                desired.pop(advancement_id)
                sidecar_records.append(
                    {
                        "schema": 1,
                        "record_type": "advancement_progress_waiver",
                        "policy_id": policy["policy_id"],
                        "policy_sha256": policy_hash,
                        "player_uuid": player_uuid,
                        "source_file": source_path.name,
                        "source_file_sha256": source_hash,
                        "old_id": advancement_id,
                        "classification": "no_proven_target_equivalent",
                        "reason": rule["reason"],
                        "progress": normalized,
                    }
                )
        target_path = target_dir / source_path.name
        target_is_safe(target_path, source_value, desired)
        if file_affected:
            affected_files += 1
            plans[target_path] = stable_json(desired)
    mapped_records.sort(key=lambda item: (item["player_uuid"], item["old_id"]))
    sidecar_records.sort(key=lambda item: (item["player_uuid"], item["old_id"]))
    sidecar_path = target / SIDECAR_RELATIVE
    sidecar_bytes = sidecar_payload(sidecar_records)
    if sidecar_path.exists():
        if sidecar_path.is_symlink() or not sidecar_path.is_file():
            raise AdvancementConversionError(f"invalid advancement sidecar path: {sidecar_path}")
        if sidecar_path.read_bytes() != sidecar_bytes:
            raise AdvancementConversionError(
                f"existing advancement sidecar differs from deterministic source plan: {sidecar_path}"
            )
    plans[sidecar_path] = sidecar_bytes
    return {
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_hash,
        "policy_rules": len(rules),
        "source_files": len(source_files),
        "progress_entries": total_progress_entries,
        "affected_files": affected_files,
        "occurrences": sum(occurrences.values()),
        "mapped": len(mapped_records),
        "sidecarred": len(sidecar_records),
        "absent_policy_ids": sorted(old_id for old_id, count in occurrences.items() if not count),
        "occurrences_by_id": {key: occurrences[key] for key in sorted(occurrences)},
        "mapped_records": mapped_records,
        "sidecar_records": sidecar_records,
        "sidecar_relative": SIDECAR_RELATIVE.as_posix(),
        "plans": plans,
    }


def write_transaction(plans: dict[Path, bytes], dry_run: bool) -> list[dict]:
    outputs = []
    changed: list[tuple[Path, bytes]] = []
    for path, payload in sorted(plans.items(), key=lambda item: str(item[0])):
        before = sha256(path) if path.is_file() else None
        changed_flag = not path.is_file() or path.read_bytes() != payload
        outputs.append(
            {
                "path": str(path),
                "changed": changed_flag,
                "sha256_before": before,
                "sha256": bytes_sha256(payload),
                "bytes": len(payload),
            }
        )
        if changed_flag:
            changed.append((path, payload))
    if dry_run or not changed:
        return outputs

    temporary: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    committed: list[Path] = []
    commit_complete = False
    rollback_complete = False
    try:
        for path, payload in changed:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".migration.tmp")
            backup = path.with_name(path.name + ".migration.bak")
            for stale in (temp, backup):
                if stale.exists():
                    raise AdvancementConversionError(
                        f"stale advancement transaction artifact requires recovery: {stale}"
                    )
            temp.write_bytes(payload)
            if temp.read_bytes() != payload:
                raise AdvancementConversionError(f"temporary write verification failed: {temp}")
            temporary[path] = temp
            if path.exists():
                shutil.copy2(path, backup)
                backups[path] = backup
            else:
                backups[path] = None
        for path, _ in changed:
            committed.append(path)
            os.replace(temporary[path], path)
        commit_complete = True
    except BaseException as commit_error:
        failures = []
        for path in reversed(committed):
            backup = backups.get(path)
            try:
                if backup is None:
                    path.unlink(missing_ok=True)
                elif backup.exists():
                    os.replace(backup, path)
                else:
                    failures.append(f"missing backup for {path}")
            except BaseException as rollback_error:
                failures.append(f"{path}: {type(rollback_error).__name__}: {rollback_error}")
        if failures:
            raise AdvancementConversionError(
                f"advancement commit failed and rollback is incomplete: {failures}"
            ) from commit_error
        rollback_complete = True
        raise
    finally:
        for temp in temporary.values():
            temp.unlink(missing_ok=True)
        if commit_complete or rollback_complete:
            for backup in backups.values():
                if backup is not None:
                    backup.unlink(missing_ok=True)
    return outputs


def lock_path(target: Path) -> Path:
    return target.parent / f".{target.name}.advancement-conversion.lock"


class TargetLock:
    def __init__(self, target: Path):
        self.path = lock_path(target)
        self.fd: int | None = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            self.fd = os.open(self.path, flags, 0o600)
        except FileExistsError as exc:
            raise AdvancementConversionError(
                f"advancement conversion lock already exists: {self.path}"
            ) from exc
        os.write(self.fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(self.fd)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        assert self.fd is not None
        os.close(self.fd)
        self.fd = None
        self.path.unlink()
        return False


def atomic_report(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(stable_json(value))
    os.replace(temporary, path)


def run(args: argparse.Namespace) -> int:
    source = args.source_game_dir.resolve()
    target = args.target_game_dir.resolve()
    report_path = args.report.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise AdvancementConversionError(
            "source and target game directories must be disjoint"
        )

    def execute() -> dict:
        plan = build_plan(source, target, args.policy.resolve())
        outputs = write_transaction(plan.pop("plans"), args.dry_run)
        return {
            "schema": 1,
            "status": (
                "WOULD_CONVERT"
                if args.dry_run and any(item["changed"] for item in outputs)
                else "DRY_RUN_ALREADY_TARGET"
                if args.dry_run
                else "CONVERTED"
                if any(item["changed"] for item in outputs)
                else "ALREADY_TARGET"
            ),
            "dry_run": args.dry_run,
            "source_game_dir": str(source),
            "target_game_dir": str(target),
            **plan,
            "outputs": outputs,
        }

    if args.dry_run:
        report = execute()
    else:
        with TargetLock(target):
            report = execute()
    atomic_report(report_path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(report_path),
                "source_files": report["source_files"],
                "affected_files": report["affected_files"],
                "occurrences": report["occurrences"],
                "mapped": report["mapped"],
                "sidecarred": report["sidecarred"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-game-dir", type=Path, required=True)
    parser.add_argument("--target-game-dir", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).with_name("advancement_id_policy_20260813.json"),
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return run(args)
    except AdvancementConversionError as exc:
        report = {
            "schema": 1,
            "status": "BLOCKED",
            "dry_run": args.dry_run,
            "source_game_dir": str(args.source_game_dir.resolve()),
            "target_game_dir": str(args.target_game_dir.resolve()),
            "blockers": [str(exc)],
        }
        try:
            atomic_report(args.report.resolve(), report)
        except OSError:
            pass
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
