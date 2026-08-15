#!/usr/bin/env python3
"""Compare SavedData NBT trees from a source world and a saved target world."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import nbtlib


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def primitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): primitive(item) for key, item in value.items()}
    if hasattr(value, "tolist"):
        listed = value.tolist()
        return primitive(listed)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [primitive(item) for item in value]
    if isinstance(value, str):
        return str(value)
    if isinstance(value, (int, float)):
        return value.item() if hasattr(value, "item") else value
    return str(value)


def differences(left: Any, right: Any, path: str = "", limit: int = 2000) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(a: Any, b: Any, current: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                child = f"{current}.{key}" if current else key
                if key not in a:
                    found.append({"path": child, "change": "added", "target": b[key]})
                elif key not in b:
                    found.append({"path": child, "change": "removed", "source": a[key]})
                else:
                    visit(a[key], b[key], child)
            return
        if isinstance(a, list) and isinstance(b, list):
            if a != b:
                found.append({
                    "path": current,
                    "change": "list_changed",
                    "source_length": len(a),
                    "target_length": len(b),
                    "source": a if len(a) <= 20 else None,
                    "target": b if len(b) <= 20 else None,
                })
            return
        if a != b:
            found.append({"path": current, "change": "value_changed", "source": a, "target": b})

    visit(left, right, path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    records = []
    names = sorted({p.name for p in args.source.glob("*.dat")} | {p.name for p in args.target.glob("*.dat")})
    for name in names:
        source = args.source / name
        target = args.target / name
        record: dict[str, Any] = {"name": name, "source_exists": source.exists(), "target_exists": target.exists()}
        if not source.exists() or not target.exists():
            records.append(record)
            continue
        record.update({
            "source_sha256": digest(source),
            "target_sha256": digest(target),
            "source_bytes": source.stat().st_size,
            "target_bytes": target.stat().st_size,
        })
        left = primitive(nbtlib.load(source, gzipped=True))
        right = primitive(nbtlib.load(target, gzipped=True))
        record["exact_equal"] = left == right
        left_without_version = dict(left)
        right_without_version = dict(right)
        left_without_version.pop("DataVersion", None)
        right_without_version.pop("DataVersion", None)
        record["semantic_equal_ignoring_data_version"] = left_without_version == right_without_version
        record["differences"] = differences(left, right)
        records.append(record)

    result = {
        "source": str(args.source.resolve()),
        "target": str(args.target.resolve()),
        "files": records,
        "hash_changed": [r["name"] for r in records if r.get("source_sha256") != r.get("target_sha256")],
        "semantic_changed": [r["name"] for r in records if not r.get("semantic_equal_ignoring_data_version", False)],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(args.report.resolve()), "hash_changed": result["hash_changed"], "semantic_changed": result["semantic_changed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
