#!/usr/bin/env python3
"""Normalize source-map paths for portable collaboration."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "docs" / "SOURCE-MAP.json"
PREFIX_RULES = [
    (
        re.compile(
            r"(?i)^C:\\Users\\[^\\]+\\Documents\\Codex\\2026-08-07\\"
            r"d-trans-1-21-11-1"
        ),
        "<WORKSPACE>",
    ),
    (re.compile(r"(?i)^D:\\Trans\\migration-audit-work"), "<AUDIT_ROOT>"),
    (re.compile(r"(?i)^D:\\Trans\\migration-handoff-20260812"), "<HANDOFF_ROOT>"),
]


def normalize_destination(value: str) -> str:
    normalized = value.replace("\\", "/")
    marker = ".building-"
    if marker in normalized:
        tail = normalized.split(marker, 1)[1]
        if "/" in tail:
            normalized = tail.split("/", 1)[1]
    return normalized.lstrip("/")


payload = json.loads(MAP.read_text(encoding="utf-8"))
previous_generated_at = payload.get("generated_at")
before_normalization = json.dumps(
    {key: value for key, value in payload.items() if key != "generated_at"},
    ensure_ascii=False,
    sort_keys=True,
)
for row in payload.get("sources", []):
    source = str(row.get("source", ""))
    for pattern, replacement in PREFIX_RULES:
        match = pattern.match(source)
        if match:
            suffix = source[match.end():].lstrip("\\/")
            source = replacement + ("/" + suffix.replace("\\", "/") if suffix else "")
            break
    row["source"] = source
    row["destination"] = normalize_destination(str(row.get("destination", "")))
after_normalization = json.dumps(
    {key: value for key, value in payload.items() if key != "generated_at"},
    ensure_ascii=False,
    sort_keys=True,
)
if before_normalization == after_normalization and previous_generated_at:
    payload["generated_at"] = previous_generated_at
else:
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
MAP.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"SOURCE_MAP_NORMALIZED records={len(payload.get('sources', []))}")
