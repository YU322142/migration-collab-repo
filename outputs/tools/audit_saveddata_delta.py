#!/usr/bin/env python3
"""Read-only inventory and structural audit for Minecraft SavedData files."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import nbtlib


EXCLUDED = {
    "create_tracks.dat",
    "create_logistics.dat",
    "mineastr_sign_translations.dat",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def scalar_preview(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 160 else value[:157] + "..."
    if isinstance(value, (int, float)):
        return value
    return str(value)


def summarize(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        if isinstance(value, (dict, list, tuple)):
            return {"type": type(value).__name__, "length": len(value)}
        return scalar_preview(value)
    if isinstance(value, dict):
        return {
            "type": type(value).__name__,
            "length": len(value),
            "keys": {str(k): summarize(v, depth + 1) for k, v in value.items()},
        }
    if isinstance(value, (list, tuple)):
        item_types = Counter(type(item).__name__ for item in value)
        result: dict[str, Any] = {
            "type": type(value).__name__,
            "length": len(value),
            "item_types": dict(sorted(item_types.items())),
        }
        if value:
            result["first"] = summarize(value[0], depth + 1)
            if len(value) > 1:
                result["last"] = summarize(value[-1], depth + 1)
        return result
    return {"type": type(value).__name__, "value": scalar_preview(value)}


def collect_strings(value: Any, prefix: str = "", depth: int = 0) -> list[dict[str, str]]:
    if depth > 8:
        return []
    found: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found.extend(collect_strings(item, path, depth + 1))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value[:1000]):
            found.extend(collect_strings(item, f"{prefix}[{index}]", depth + 1))
    elif isinstance(value, str):
        found.append({"path": prefix, "value": scalar_preview(value)})
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    for path in sorted(args.source.glob("*.dat"), key=lambda p: p.name.lower()):
        if path.name in EXCLUDED:
            continue
        record: dict[str, Any] = {
            "name": path.name,
            "bytes": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
            "sha256": sha256(path),
        }
        try:
            root = nbtlib.load(path, gzipped=True)
            record["parse"] = "ok"
            record["schema"] = summarize(root)
            strings = collect_strings(root)
            record["strings"] = strings[:5000]
            record["string_count"] = len(strings)
        except Exception as exc:  # audit output must retain parse failures
            record["parse"] = "error"
            record["error"] = f"{type(exc).__name__}: {exc}"
        records.append(record)

    report = {
        "source": str(args.source.resolve()),
        "excluded": sorted(EXCLUDED),
        "file_count": len(records),
        "total_bytes": sum(item["bytes"] for item in records),
        "files": records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "report": str(args.report.resolve()),
        "file_count": report["file_count"],
        "total_bytes": report["total_bytes"],
        "parse_errors": [item["name"] for item in records if item["parse"] != "ok"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
