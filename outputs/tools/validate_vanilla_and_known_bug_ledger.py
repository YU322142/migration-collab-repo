#!/usr/bin/env python3
"""Validate the generated vanilla/known-bug ledger and its evidence locks."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


MODULE_PATH = Path(__file__).with_name("build_vanilla_and_known_bug_ledger.py")
SPEC = importlib.util.spec_from_file_location("vanilla_known_bug_builder", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def validate(ledger_path: Path, markdown_path: Path, *, verify_evidence: bool = True) -> dict[str, Any]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    builder.validate_model(ledger)

    summary = ledger["summary"]
    identifiers = ledger["new_vanilla_identifiers"]
    issues = ledger["items"]
    actual_identifier_counts: dict[str, int] = {}
    for row in identifiers:
        actual_identifier_counts[row["classification"]] = actual_identifier_counts.get(row["classification"], 0) + 1
    if summary["new_vanilla_identifiers"]["classification_counts"] != actual_identifier_counts:
        raise ValueError("identifier summary drift")
    actual_issue_counts: dict[str, int] = {}
    for row in issues:
        actual_issue_counts[row["classification"]] = actual_issue_counts.get(row["classification"], 0) + 1
    if summary["known_issue_classification_counts"] != actual_issue_counts:
        raise ValueError("issue summary drift")
    if summary["known_issue_rows"] != len(issues):
        raise ValueError("known_issue_rows drift")

    markdown = markdown_path.read_text(encoding="utf-8")
    for required_text in (
        "49 个有功能性 backport",
        "minecraft:netherite_horse_armor",
        "Nautilus",
        "Happy Ghast",
        "Locator Bar",
        "map banner",
        "87 原图 + 87 缩略图",
        "NO-GO",
    ):
        if required_text not in markdown:
            raise ValueError(f"markdown missing required text: {required_text}")

    checked = 0
    if verify_evidence:
        expected = {row["path"]: row for row in ledger["evidence_locks"]}
        for logical_path, row in expected.items():
            path = builder.evidence_path(logical_path)
            if not path.is_file():
                raise ValueError(f"evidence missing: {logical_path}")
            if path.stat().st_size != row["bytes"]:
                raise ValueError(f"evidence size drift: {logical_path}")
            if builder.sha256(path) != row["sha256"]:
                raise ValueError(f"evidence hash drift: {logical_path}")
            checked += 1

    return {
        "schema": 1,
        "status": "PASS",
        "ledger": str(ledger_path),
        "markdown": str(markdown_path),
        "identifiers": len(identifiers),
        "issues": len(issues),
        "release_gates": len(ledger["release_gates"]),
        "evidence_files_checked": checked,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=builder.OUTPUT_JSON)
    parser.add_argument("--markdown", type=Path, default=builder.OUTPUT_MD)
    parser.add_argument("--skip-evidence", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.ledger, args.markdown, verify_evidence=not args.skip_evidence)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(builder.stable_json(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
