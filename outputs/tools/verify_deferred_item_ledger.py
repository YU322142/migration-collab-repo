#!/usr/bin/env python3
"""Bind deferred-item audit checkpoints and reject semantic drift.

The expensive full-world scanner is intentionally separate.  This verifier
consumes its immutable JSON reports and compares the protected ItemStack by
owner identity and exact canonical stack bytes.  Region/entity ordering and a
horse moving between MCA slots are recorded but are not treated as data loss.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import uuid
from typing import Any


TARGET_ITEM = "minecraft:netherite_horse_armor"
EXPECTED_OWNER_ID = "minecraft:horse"
SOURCE_SLOT_SUFFIX = ".equipment.body"
TARGET_SLOT_SUFFIX = ".body_armor_item"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def uuid_from_owner(owner: dict[str, Any]) -> str:
    raw = owner.get("UUID")
    if isinstance(raw, list) and len(raw) == 4 and all(isinstance(v, int) for v in raw):
        value = 0
        for part in raw:
            value = (value << 32) | (part & 0xFFFFFFFF)
        return str(uuid.UUID(int=value))
    most = owner.get("UUIDMost")
    least = owner.get("UUIDLeast")
    if isinstance(most, int) and isinstance(least, int):
        return str(uuid.UUID(int=((most & ((1 << 64) - 1)) << 64) | (least & ((1 << 64) - 1))))
    raise ValueError("protected item owner has no supported UUID representation")


def occurrence(record: dict[str, Any]) -> dict[str, Any]:
    stack = record.get("stack")
    owner = record.get("owner")
    if not isinstance(stack, dict) or not isinstance(owner, dict):
        raise ValueError("protected occurrence lacks complete stack/owner context")
    if stack.get("id") != TARGET_ITEM:
        raise ValueError(f"unexpected protected item ID: {stack.get('id')!r}")
    if owner.get("id") != EXPECTED_OWNER_ID:
        raise ValueError(f"protected item owner is not a horse: {owner.get('id')!r}")
    count = record.get("count")
    if count != 1:
        raise ValueError(f"protected item count must remain exactly one, got {count!r}")
    path = record.get("path")
    if not isinstance(path, str):
        raise ValueError("protected occurrence path is missing")
    stack_payload = canonical_json(stack)
    return {
        "item_id": TARGET_ITEM,
        "count": count,
        "canonical_stack_sha256": sha256_bytes(stack_payload),
        "canonical_stack": stack,
        "owner_id": owner["id"],
        "owner_uuid": uuid_from_owner(owner),
        "owner_position": owner.get("Pos"),
        "file": record.get("file"),
        "mca_slot": record.get("mca_slot"),
        "nbt_path": path,
        "slot": record.get("slot"),
    }


def select_checkpoint(report_path: Path, root_label: str) -> dict[str, Any]:
    report = read_json(report_path)
    if report.get("status") != "PASS" or report.get("read_only") is not True:
        raise ValueError(f"audit is not a read-only PASS: {report_path}")
    if report.get("target_item") != TARGET_ITEM:
        raise ValueError(f"audit target item mismatch: {report_path}")
    totals = report.get("totals")
    if not isinstance(totals, dict) or totals.get("errors") != 0:
        raise ValueError(f"audit contains parse errors: {report_path}")
    rows = [
        row for row in report.get("matches", [])
        if isinstance(row, dict) and row.get("root_label") == root_label
    ]
    if len(rows) != 1:
        raise ValueError(
            f"checkpoint {root_label!r} must contain exactly one occurrence, got {len(rows)}"
        )
    return {
        "audit_path": str(report_path.resolve()),
        "audit_sha256": sha256(report_path),
        "audit_root_label": root_label,
        **occurrence(rows[0]),
    }


def _require_slot(checkpoint: dict[str, Any], suffix: str, label: str) -> None:
    path = checkpoint["nbt_path"]
    if not path.endswith(suffix):
        raise ValueError(f"{label} protected slot mismatch: {path!r} does not end with {suffix!r}")


def _compare(reference: dict[str, Any], candidate: dict[str, Any], label: str) -> None:
    for key in (
        "item_id",
        "count",
        "canonical_stack_sha256",
        "owner_id",
        "owner_uuid",
    ):
        if candidate[key] != reference[key]:
            raise ValueError(
                f"{label} protected occurrence drift in {key}: "
                f"{candidate[key]!r} != {reference[key]!r}"
            )
    _require_slot(candidate, TARGET_SLOT_SUFFIX, label)


def parse_checkpoint(value: str) -> tuple[str, Path, str]:
    if "=" not in value or "::" not in value:
        raise argparse.ArgumentTypeError(
            "checkpoint must be NAME=REPORT.json::ROOT_LABEL"
        )
    name, binding = value.split("=", 1)
    path_text, root_label = binding.rsplit("::", 1)
    if not name or not path_text or not root_label:
        raise argparse.ArgumentTypeError(
            "checkpoint must be NAME=REPORT.json::ROOT_LABEL"
        )
    return name, Path(path_text), root_label


def verify(
    baseline_path: Path,
    checkpoint_bindings: list[tuple[str, Path, str]],
) -> dict[str, Any]:
    source = select_checkpoint(baseline_path, "source")
    staging = select_checkpoint(baseline_path, "staging")
    _require_slot(source, SOURCE_SLOT_SUFFIX, "stopped_source")
    _compare(source, staging, "converted_staging")

    checkpoints: dict[str, dict[str, Any]] = {
        "stopped_source": source,
        "converted_staging": staging,
    }
    for name, report_path, root_label in checkpoint_bindings:
        if name in checkpoints:
            raise ValueError(f"duplicate checkpoint name: {name}")
        value = select_checkpoint(report_path, root_label)
        _compare(staging, value, name)
        checkpoints[name] = value

    expected_runtime = {"runtime_round_1_after_stop", "runtime_round_2_after_stop"}
    present_runtime = expected_runtime.intersection(checkpoints)
    status = "PASS" if present_runtime == expected_runtime else "BASELINE_LOCKED_RUNTIME_PENDING"
    return {
        "schema": 1,
        "status": status,
        "category": "deferred_item_semantic_ledger",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "target_item": TARGET_ITEM,
        "protected_owner_uuid": source["owner_uuid"],
        "allowed_path_alias": {
            "source": SOURCE_SLOT_SUFFIX.removeprefix("."),
            "target": TARGET_SLOT_SUFFIX.removeprefix("."),
        },
        "required_runtime_checkpoints": sorted(expected_runtime),
        "checkpoints": checkpoints,
        "blockers": [] if status == "PASS" else sorted(expected_runtime - present_runtime),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument(
        "--checkpoint",
        action="append",
        default=[],
        type=parse_checkpoint,
        metavar="NAME=REPORT.json::ROOT_LABEL",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-pending-runtime", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(args.baseline, args.checkpoint)
    except Exception as exc:
        report = {
            "schema": 1,
            "status": "NO_GO",
            "category": "deferred_item_semantic_ledger",
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "target_item": TARGET_ITEM,
            "blockers": [f"{type(exc).__name__}: {exc}"],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "output_sha256": sha256(args.output)}))
    if report["status"] == "PASS":
        return 0
    if report["status"] == "BASELINE_LOCKED_RUNTIME_PENDING" and args.allow_pending_runtime:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
