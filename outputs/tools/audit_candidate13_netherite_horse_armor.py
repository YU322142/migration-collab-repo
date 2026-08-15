#!/usr/bin/env python3
"""Locate every real netherite-horse-armor ItemStack in source and staging.

The scan is intentionally read-only and covers every MCA chunk plus every
standalone ``.dat``, ``.dat_old`` and ``.nbt`` payload below both roots.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from candidate13_nbt_audit_common import (
    bounded,
    collect_world_nbt_files,
    compound_context,
    iter_region,
    known_non_nbt_reason,
    load_nbt_file,
    path_text,
    plain,
    sha256,
)


TARGET_ITEM = "minecraft:netherite_horse_armor"


def _integer(value: Any) -> bool:
    unpacked = plain(value)
    return isinstance(unpacked, int) and not isinstance(unpacked, bool)


def _walk(
    value: Any,
    parts: list[str | int],
    ancestors: list[tuple[list[str | int], Any]],
    matches: list[dict[str, Any]],
) -> None:
    if isinstance(value, dict):
        identifier = plain(value.get("id"))
        count_key = "count" if "count" in value else "Count" if "Count" in value else None
        if identifier == TARGET_ITEM and count_key and _integer(value[count_key]):
            owner = None
            for owner_parts, candidate in reversed(ancestors):
                context = compound_context(candidate)
                owner_id = context.get("id")
                if owner_id and owner_id != TARGET_ITEM:
                    owner = {"path": path_text(owner_parts), **context}
                    break
            matches.append(
                {
                    "path": path_text(parts),
                    "count_key": count_key,
                    "count": int(plain(value[count_key])),
                    "slot": plain(value.get("Slot")) if "Slot" in value else None,
                    "components": bounded(value.get("components", {})),
                    "legacy_tag": bounded(value.get("tag", {})),
                    "stack": bounded(value),
                    "owner": owner,
                }
            )
        next_ancestors = ancestors + [(parts, value)]
        for key, child in value.items():
            _walk(child, parts + [str(key)], next_ancestors, matches)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _walk(child, parts + [index], ancestors, matches)


def scan_file(task: tuple[str, str, str]) -> dict[str, Any]:
    label, root_text, path_text_value = task
    root = Path(root_text)
    path = Path(path_text_value)
    relative = str(path.relative_to(root)).replace("\\", "/")
    result: dict[str, Any] = {
        "label": label,
        "path": relative,
        "bytes": path.stat().st_size,
        "containers": 0,
        "matches": [],
        "errors": [],
        "skipped_known_non_nbt": [],
    }
    try:
        non_nbt_reason = known_non_nbt_reason(path)
        if non_nbt_reason is not None:
            result["skipped_known_non_nbt"].append(
                {
                    "reason": non_nbt_reason,
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
            return result
        if path.suffix.lower() == ".mca":
            for slot, compression, root_tag in iter_region(path):
                result["containers"] += 1
                found: list[dict[str, Any]] = []
                _walk(root_tag, [], [], found)
                for record in found:
                    record.update({"mca_slot": slot, "compression": compression})
                    result["matches"].append(record)
        else:
            root_tag, gzipped = load_nbt_file(path)
            result["containers"] = 1
            found = []
            _walk(root_tag, [], [], found)
            for record in found:
                record["gzipped"] = gzipped
                result["matches"].append(record)
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# Candidate13 netherite horse armor full-world audit",
        "",
        f"- Status: `{report['status']}`",
        f"- Item: `{TARGET_ITEM}`",
        f"- Workers: `{report['workers']}`",
        f"- Files scanned: `{report['totals']['files']}`",
        f"- NBT containers/chunks scanned: `{report['totals']['containers']}`",
        f"- Real ItemStack occurrences: `{report['totals']['matches']}`",
        f"- Parse errors: `{report['totals']['errors']}`",
        f"- Explicit known non-NBT files skipped: `{report['totals']['known_non_nbt_files']}`",
        "",
        "## Per root",
        "",
    ]
    for label, summary in report["roots"].items():
        lines.extend(
            [
                f"- `{label}`: files `{summary['files']}`, containers `{summary['containers']}`, "
                f"matches `{summary['matches']}`, known non-NBT `{summary['known_non_nbt_files']}`, "
                f"errors `{summary['errors']}`.",
            ]
        )
    lines.extend(["", "## Exact occurrences", ""])
    if not report["matches"]:
        lines.append("- None.")
    else:
        for index, row in enumerate(report["matches"], 1):
            lines.append(
                f"{index}. `{row['root_label']}:{row['file']}#{row['path']}` — "
                f"count `{row['count']}`, slot `{row['slot']}`, owner `{row.get('owner')}`."
            )
    lines.extend(
        [
            "",
            "The JSON report contains the complete bounded stack, components, legacy tag, "
            "owner context, MCA slot and compression metadata for every occurrence.",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.workers <= 20:
        parser.error("--workers must be in [1,20]")

    roots = {"source": args.source.resolve(), "staging": args.staging.resolve()}
    for root in roots.values():
        if not root.is_dir():
            raise FileNotFoundError(root)
    tasks = [
        (label, str(root), str(path))
        for label, root in roots.items()
        for path in collect_world_nbt_files(root)
    ]
    per_root = {
        label: {"root": str(root), "files": 0, "bytes": 0, "containers": 0, "matches": 0, "known_non_nbt_files": 0, "errors": 0}
        for label, root in roots.items()
    }
    matches: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped_known_non_nbt: list[dict[str, Any]] = []
    completed = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(scan_file, task): task for task in tasks}
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            summary = per_root[result["label"]]
            summary["files"] += 1
            summary["bytes"] += result["bytes"]
            summary["containers"] += result["containers"]
            summary["matches"] += len(result["matches"])
            summary["known_non_nbt_files"] += len(result["skipped_known_non_nbt"])
            summary["errors"] += len(result["errors"])
            for record in result["matches"]:
                matches.append(
                    {"root_label": result["label"], "file": result["path"], **record}
                )
            for error in result["errors"]:
                errors.append({"root_label": result["label"], "file": result["path"], "error": error})
            for record in result["skipped_known_non_nbt"]:
                skipped_known_non_nbt.append(
                    {"root_label": result["label"], "file": result["path"], **record}
                )
            if completed % 100 == 0 or completed == len(tasks):
                print(json.dumps({"completed": completed, "total": len(tasks), "matches": len(matches), "errors": len(errors)}), flush=True)

    matches.sort(key=lambda row: (row["root_label"], row["file"], row.get("mca_slot", -1), row["path"]))
    report: dict[str, Any] = {
        "schema": 1,
        "status": "PASS" if not errors else "BLOCKED_PARSE_ERRORS",
        "category": "candidate13_full_world_itemstack_audit",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "read_only": True,
        "target_item": TARGET_ITEM,
        "workers": args.workers,
        "process_pid": os.getpid(),
        "roots": per_root,
        "totals": {
            "files": sum(value["files"] for value in per_root.values()),
            "bytes": sum(value["bytes"] for value in per_root.values()),
            "containers": sum(value["containers"] for value in per_root.values()),
            "matches": len(matches),
            "known_non_nbt_files": len(skipped_known_non_nbt),
            "errors": len(errors),
        },
        "matches": matches,
        "skipped_known_non_nbt": skipped_known_non_nbt,
        "errors": errors,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, args.output_md)
    print(json.dumps({"status": report["status"], "matches": len(matches), "errors": len(errors), "json_sha256": sha256(args.output_json), "md_sha256": sha256(args.output_md)}), flush=True)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
