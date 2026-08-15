#!/usr/bin/env python3
"""Prove skipped conflict block entities remain byte-semantically unchanged."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import create_storage_object_ota as ota


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--apply-report", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    package = ota.load_package(args.package)
    report = json.loads(args.apply_report.read_text(encoding="utf-8"))
    conflict_ids = {row["group_id"] for row in report.get("conflicts", [])}
    backup_root = Path(str(report.get("backup_root", ""))) / "regions"
    world = args.world.resolve()
    current_chunks: dict[tuple[Path, int], ota.ChunkImage] = {}
    backup_chunks: dict[tuple[Path, int], ota.ChunkImage] = {}
    failures: list[dict[str, object]] = []
    checked = 0

    with ota.world_lock_probe(world):
        for group in package.groups:
            if group.group_id not in conflict_ids:
                continue
            for spec in group.members:
                checked += 1
                relative = spec.region_path
                current_region = ota.local_path(world, relative)
                backup_region = ota.local_path(backup_root, relative)
                current_key = (current_region, spec.slot)
                backup_key = (backup_region, spec.slot)
                if current_key not in current_chunks:
                    image = ota.read_chunk_image(current_region, spec.slot)
                    if image is not None:
                        current_chunks[current_key] = image
                if backup_key not in backup_chunks:
                    image = ota.read_chunk_image(backup_region, spec.slot)
                    if image is not None:
                        backup_chunks[backup_key] = image
                current = current_chunks.get(current_key)
                before = backup_chunks.get(backup_key)
                if current is None or before is None:
                    failures.append({"group_id": group.group_id, "pos": list(spec.pos), "error": "chunk missing"})
                    continue
                current_be = ota.find_block_entity(current.chunk, spec.pos)
                before_be = ota.find_block_entity(before.chunk, spec.pos)
                if current_be is None or before_be is None:
                    failures.append({"group_id": group.group_id, "pos": list(spec.pos), "error": "block entity missing"})
                    continue
                current_content = ota.dotted_get(current_be, spec.content_path)
                before_content = ota.dotted_get(before_be, spec.content_path)
                current_hash = None if current_content is ota.MISSING else ota.content_hash(current_content)
                before_hash = None if before_content is ota.MISSING else ota.content_hash(before_content)
                if current_hash != before_hash:
                    failures.append({
                        "group_id": group.group_id,
                        "pos": list(spec.pos),
                        "content_path": spec.content_path,
                        "error": "conflicting content changed",
                    })
                    continue
                if ota.validate_stable_fields(spec, current_be):
                    failures.append({"group_id": group.group_id, "pos": list(spec.pos), "error": "stable identity changed"})
                    continue
                if ota.block_state_at(current.chunk, spec.pos) != ota.block_state_at(before.chunk, spec.pos):
                    failures.append({"group_id": group.group_id, "pos": list(spec.pos), "error": "block state changed"})

    result = {
        "status": "PASS_CONFLICTS_PRESERVED" if not failures else "BLOCKED",
        "package": str(args.package.resolve()),
        "apply_report": str(args.apply_report.resolve()),
        "conflict_groups": len(conflict_ids),
        "checked_members": checked,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if not failures else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ota.OtaError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
