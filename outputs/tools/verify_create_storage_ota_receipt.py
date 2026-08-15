#!/usr/bin/env python3
"""Read-only post-apply verification for create-storage-object-ota receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import create_storage_object_ota as ota


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--allow-region-hash-drift",
        action="store_true",
        help="allow later OTA receipts to have changed the same region; member hashes remain mandatory",
    )
    args = parser.parse_args()

    receipt = ota.load_receipt(args.receipt)
    world = args.world.resolve()
    failures: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    checked_members = 0
    checked_regions = 0
    chunks: dict[tuple[Path, int], ota.ChunkImage] = {}

    with ota.world_lock_probe(world):
        try:
            ota.validate_world_identity(world, receipt.get("world_identity"))
        except ota.OtaError as exc:
            failures.append({"scope": "world_identity", "error": str(exc)})
        for region_row in receipt.get("regions", []):
            relative = region_row.get("region_path")
            if not isinstance(relative, str):
                failures.append({"scope": "region", "error": "invalid region_path"})
                continue
            region = ota.local_path(world, ota.safe_relative(relative, suffix=".mca"))
            backup = Path(str(region_row.get("backup_path", "")))
            if not backup.is_file() or ota.sha256_file(backup) != region_row.get("backup_sha256"):
                failures.append({"scope": "region_backup", "region": relative, "error": "backup missing/hash mismatch"})
            if not region.is_file() or ota.sha256_file(region) != region_row.get("post_apply_region_sha256"):
                row = {"scope": "region_post", "region": relative, "error": "post-apply hash mismatch"}
                if args.allow_region_hash_drift:
                    warnings.append(row)
                else:
                    failures.append(row)
            checked_regions += 1

        for row in receipt.get("members", []):
            checked_members += 1
            try:
                spec = ota.receipt_member_spec(row)
                region = ota.local_path(world, spec.region_path)
                key = (region, spec.slot)
                if key not in chunks:
                    image = ota.read_chunk_image(region, spec.slot)
                    if image is None:
                        raise ota.OtaError("chunk is missing")
                    chunks[key] = image
                block_entity = ota.find_block_entity(chunks[key].chunk, spec.pos)
                if block_entity is None:
                    raise ota.OtaError("block entity is missing")
                if ota.plain(block_entity.get("id")) != spec.block_entity_id:
                    raise ota.OtaError("block entity id changed")
                stable = ota.validate_stable_fields(spec, block_entity)
                if stable:
                    raise ota.OtaError("; ".join(stable))
                state = ota.block_state_at(chunks[key].chunk, spec.pos)
                state_problems = ota.validate_expected_block_state(spec.expected_block_state, state)
                if state_problems:
                    raise ota.OtaError("; ".join(state_problems))
                content = ota.dotted_get(block_entity, spec.content_path)
                if content is ota.MISSING or ota.content_hash(content) != row.get("post_content_sha256"):
                    raise ota.OtaError("post content hash mismatch")
                remove_paths = row.get("post_removed_paths", row.get("remove_paths", []))
                if not isinstance(remove_paths, list):
                    raise ota.OtaError("receipt remove paths are invalid")
                lingering = [path for path in remove_paths if ota.dotted_get(block_entity, path) is not ota.MISSING]
                if lingering:
                    raise ota.OtaError("legacy fields still present: " + ", ".join(lingering))
                snapshot = Path(str(row.get("snapshot_path", "")))
                if not snapshot.is_file() or ota.sha256_file(snapshot) != row.get("snapshot_sha256"):
                    raise ota.OtaError("block-entity snapshot missing/hash mismatch")
            except (KeyError, TypeError, ValueError, ota.OtaError) as exc:
                failures.append({
                    "scope": "member",
                    "dimension": row.get("dimension") if isinstance(row, dict) else None,
                    "pos": row.get("pos") if isinstance(row, dict) else None,
                    "error": str(exc),
                })

    result = {
        "status": "PASS_POST_APPLY" if not failures else "BLOCKED",
        "receipt": str(args.receipt.resolve()),
        "world": str(world),
        "ledger_sha256": receipt.get("ledger_sha256"),
        "checked_regions": checked_regions,
        "checked_members": checked_members,
        "warnings": warnings,
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(args.report)
    return 0 if not failures else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ota.OtaError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
