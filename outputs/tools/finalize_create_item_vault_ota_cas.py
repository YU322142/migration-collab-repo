from __future__ import annotations

import argparse
import base64
import collections
import copy
import gzip
import hashlib
import io
import json
import math
import zlib
from pathlib import Path
from typing import Any

import nbtlib

from audit_create_item_vault_ota_readonly import (
    VAULT_ID,
    block_entities,
    compact_record,
    digest,
    plain,
    scan_world,
)


def decompress(payload: bytes, compression: int) -> bytes:
    compression &= 0x7F
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"unsupported region compression {compression}")


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def dimension_for_region(relative: str) -> str:
    path = Path(relative)
    if path.parts[:2] == ("DIM-1", "region"):
        return "minecraft:the_nether"
    if path.parts[:2] == ("DIM1", "region"):
        return "minecraft:the_end"
    return "minecraft:overworld"


def key_for_raw(raw: Any, dimension: str) -> str | None:
    if str(raw.get("id")) != VAULT_ID:
        return None
    try:
        x, y, z = (int(raw.get(axis)) for axis in ("x", "y", "z"))
    except (TypeError, ValueError):
        return None
    return f"{dimension}|{x},{y},{z}"


def typed_payload(inventory: Any) -> dict[str, Any]:
    if not isinstance(inventory, list):
        raise TypeError(f"staging Inventory is {type(inventory).__name__}, expected dense list")
    if len(inventory) > 20:
        raise ValueError(f"staging dense list has {len(inventory)} entries, target capacity is 20")
    items: list[nbtlib.Compound] = []
    for index, raw_stack in enumerate(inventory):
        if not isinstance(raw_stack, nbtlib.Compound):
            raise TypeError(f"staging Inventory[{index}] is {type(raw_stack).__name__}, expected Compound")
        stack = copy.deepcopy(raw_stack)
        stack["Slot"] = nbtlib.Int(index)
        items.append(stack)
    target = nbtlib.Compound({
        "Size": nbtlib.Int(20),
        "Items": nbtlib.List[nbtlib.Compound](items),
    })
    wrapper = nbtlib.File({"Content": target}, root_name="")
    buffer = io.BytesIO()
    wrapper.write(buffer, byteorder="big")
    payload = buffer.getvalue()
    parsed = nbtlib.File.parse(io.BytesIO(payload), byteorder="big")
    if parsed.root_name != "" or plain(parsed.get("Content")) != plain(target):
        raise ValueError("typed payload round-trip mismatch")
    return {
        "encoding": "uncompressed_binary_nbt",
        "byte_order": "big",
        "root_name": "",
        "root_key": "Content",
        "byte_length": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "base64": base64.b64encode(payload).decode("ascii"),
        "roundtrip_verified": True,
        "shape": "Content={Size:Int(20),Items:List<Compound>[converted staging stacks + Slot:Int(index)]}",
    }


def extract_typed_payloads(world: Path, regions: set[str], wanted: set[str]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    output: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for relative in sorted(regions):
        path = world / Path(relative)
        dimension = dimension_for_region(relative)
        if not path.exists():
            errors.append({"region_path": relative, "error": "missing staging region"})
            continue
        with path.open("rb") as handle:
            locations = handle.read(4096)
            for mca_slot in range(1024):
                entry = locations[mca_slot * 4 : (mca_slot + 1) * 4]
                offset = int.from_bytes(entry[:3], "big")
                if not offset:
                    continue
                try:
                    handle.seek(offset * 4096)
                    length = int.from_bytes(handle.read(4), "big")
                    compression = handle.read(1)[0]
                    if compression & 0x80:
                        raise ValueError("external chunk payload unsupported")
                    root = nbtlib.File.parse(
                        io.BytesIO(decompress(handle.read(length - 1), compression)),
                        byteorder="big",
                    )
                    for block_entity_index, raw in enumerate(block_entities(root)):
                        key = key_for_raw(raw, dimension)
                        if key is None or key not in wanted:
                            continue
                        payload = typed_payload(raw.get("Inventory"))
                        output[key] = {
                            **payload,
                            "staging_region_path": relative,
                            "mca_slot": mca_slot,
                            "block_entity_index": block_entity_index,
                        }
                except Exception as exc:
                    errors.append({
                        "region_path": relative,
                        "mca_slot": mca_slot,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
    for key in sorted(wanted - set(output)):
        errors.append({"key": key, "error": "typed staging payload not found"})
    return output, errors


def group_map(records: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records.values():
        result[record["group_key"]].append(record)
    for members in result.values():
        members.sort(key=lambda item: tuple(item["pos"]))
    return result


def member_keys(groups: dict[str, list[dict[str, Any]]], group_key: str) -> list[str]:
    return sorted(member["key"] for member in groups.get(group_key, []))


def compact_member(member: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": member["key"],
        "pos": member["pos"],
        "controller": member["controller"],
        "chunk": member["chunk"],
        "region_path": member["region_path"],
        "mca_slot": member["mca_slot"],
        "block_entity_index": member["block_entity_index"],
        "block_state": member["block_state"],
        "axis": member["block_state"].get("properties", {}).get(
            "axis", member["block_state"].get("properties", {}).get("horizontal_axis")
        ),
        "last_known_pos": member["last_known_pos"],
        "Size": member["radius"],
        "Length": member["length"],
        "storage_type": member["storage_type"],
        "inventory": {
            key: value
            for key, value in member["inventory"].items()
            if key not in {"slots", "item_id_totals"}
        },
    }


def member_relationship_signature(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for member in members:
        properties = member["block_state"].get("properties", {})
        output.append({
            "key": member["key"],
            "controller": member["controller"],
            "block_state": {
                "name": member["block_state"].get("name"),
                "properties": properties,
                "axis": properties.get("axis", properties.get("horizontal_axis")),
                "decode": member["block_state"].get("decode"),
            },
            "Size": member["radius"],
            "Length": member["length"],
        })
    return sorted(output, key=lambda item: item["key"])


def relationship_validation(
    source: dict[str, Any],
    staging: dict[str, Any] | None,
    live: dict[str, Any] | None,
    source_groups: dict[str, list[dict[str, Any]]],
    staging_groups: dict[str, list[dict[str, Any]]],
    live_groups: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    group_key = source["group_key"]
    source_members = member_keys(source_groups, group_key)
    staging_members = member_keys(staging_groups, group_key)
    live_members = member_keys(live_groups, group_key)
    source_relationship = member_relationship_signature(source_groups.get(group_key, []))
    staging_relationship = member_relationship_signature(staging_groups.get(group_key, []))
    live_relationship = member_relationship_signature(live_groups.get(group_key, []))
    source_state = source["block_state"]
    staging_state = staging["block_state"] if staging is not None else None
    live_state = live["block_state"] if live is not None else None
    source_axis = source_state.get("properties", {}).get(
        "axis", source_state.get("properties", {}).get("horizontal_axis")
    )
    staging_axis = staging_state.get("properties", {}).get(
        "axis", staging_state.get("properties", {}).get("horizontal_axis")
    ) if staging_state is not None else None
    live_axis = live_state.get("properties", {}).get(
        "axis", live_state.get("properties", {}).get("horizontal_axis")
    ) if live_state is not None else None
    checks = {
        "staging_present": staging is not None,
        "live_present": live is not None,
        "staging_id": staging is not None,
        "live_id": live is not None,
        "controller_source_staging_equal": staging is not None and source["controller"] == staging["controller"],
        "controller_source_live_equal": live is not None and source["controller"] == live["controller"],
        "group_key_source_staging_equal": staging is not None and group_key == staging["group_key"],
        "group_key_source_live_equal": live is not None and group_key == live["group_key"],
        "source_staging_member_set_equal": source_members == staging_members,
        "source_live_member_set_equal": source_members == live_members,
        "source_block_state_is_item_vault": source_state.get("name") == VAULT_ID and source_state.get("decode") == "ok",
        "staging_block_state_is_item_vault": staging_state is not None and staging_state.get("name") == VAULT_ID and staging_state.get("decode") == "ok",
        "live_block_state_is_item_vault": live_state is not None and live_state.get("name") == VAULT_ID and live_state.get("decode") == "ok",
        "source_staging_block_state_equal": staging_state is not None and source_state == staging_state,
        "source_live_block_state_equal": live_state is not None and source_state == live_state,
        "source_staging_axis_equal": staging_state is not None and source_axis == staging_axis,
        "source_live_axis_equal": live_state is not None and source_axis == live_axis,
        "source_staging_group_relationship_equal": source_relationship == staging_relationship,
        "source_live_group_relationship_equal": source_relationship == live_relationship,
        "source_staging_identity_counts_equal": staging is not None
        and source["inventory"]["identity_count_sha256"] == staging["inventory"]["identity_count_sha256"],
        "source_staging_nonempty": staging is not None and staging["inventory"]["is_nonempty"],
        "staging_dense_list": staging is not None and staging["inventory"]["format"] == "dense_list",
        "staging_capacity_valid": staging is not None and staging["inventory"]["nonempty_slots"] <= 20,
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "source_member_set_sha256": digest(source_members),
        "staging_member_set_sha256": digest(staging_members),
        "live_member_set_sha256": digest(live_members),
        "source_group_relationship_sha256": digest(source_relationship),
        "staging_group_relationship_sha256": digest(staging_relationship),
        "live_group_relationship_sha256": digest(live_relationship),
        "source_axis": source_axis,
        "staging_axis": staging_axis,
        "live_axis": live_axis,
        "member_count": len(source_members),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize object-level CAS ledger for Create item vaults")
    parser.add_argument("--raw-report", type=Path, required=True)
    parser.add_argument("--source-world", type=Path, required=True)
    parser.add_argument("--staging-world", type=Path, required=True)
    parser.add_argument("--live-world", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=7)
    args = parser.parse_args()

    raw_report = json.loads(args.raw_report.read_text(encoding="utf-8"))
    conversion_marker_path = args.staging_world.resolve().parent / "migration-reports" / "conversion-complete.json"
    conversion_marker = json.loads(conversion_marker_path.read_text(encoding="utf-8")) if conversion_marker_path.exists() else {}
    conversion_time_converter = conversion_marker.get("converter_fingerprints", {}).get("convert_world_nbt.py")
    current_converter_path = Path(__file__).with_name("convert_world_nbt.py")
    current_converter_text = current_converter_path.read_text(encoding="utf-8")
    converter_provenance = {
        "conversion_marker": str(conversion_marker_path),
        "conversion_time_converter": conversion_time_converter,
        "current_converter": {
            "path": str(current_converter_path.resolve()),
            "bytes": current_converter_path.stat().st_size,
            "sha256": file_sha256(current_converter_path),
            "contains_item_vault_converter": "def convert_create_item_vault_inventory" in current_converter_text,
            "contains_item_vault_call_site": "convert_create_item_vault_inventory(block, audit)" in current_converter_text,
        },
        "same_as_conversion_time": bool(
            conversion_time_converter
            and conversion_time_converter.get("sha256") == file_sha256(current_converter_path)
        ),
    }
    regions = {
        region
        for group in raw_report.get("affected_groups", [])
        for region in group.get("region_paths", [])
    }
    source_snapshot = scan_world(args.source_world.resolve(), args.workers, regions)
    staging_snapshot = scan_world(args.staging_world.resolve(), args.workers, regions)
    live_snapshot = scan_world(args.live_world.resolve(), args.workers, regions)
    source_records = source_snapshot.pop("records")
    staging_records = staging_snapshot.pop("records")
    live_records = live_snapshot.pop("records")
    source_groups = group_map(source_records)
    staging_groups = group_map(staging_records)
    live_groups = group_map(live_records)
    wanted = {key for key, record in source_records.items() if record["inventory"]["is_nonempty"]}
    typed_payloads, staging_payload_errors = extract_typed_payloads(args.staging_world.resolve(), regions, wanted)
    legacy_candidate_keys = {
        key
        for key in wanted
        if key in staging_records
        and key in live_records
        and live_records[key]["inventory"]["format"] == "dense_list"
        and live_records[key]["inventory"]["is_nonempty"]
        and live_records[key]["inventory"]["content_sha256"] == staging_records[key]["inventory"]["content_sha256"]
    }
    live_schema_payloads, live_payload_errors = extract_typed_payloads(
        args.live_world.resolve(), regions, legacy_candidate_keys
    )
    payload_errors = [
        {"payload_source": "staging", **item} for item in staging_payload_errors
    ] + [
        {"payload_source": "live", **item} for item in live_payload_errors
    ]

    safe_restore: list[dict[str, Any]] = []
    legacy_schema: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    all_entries: list[dict[str, Any]] = []
    group_actions: dict[str, dict[str, Any]] = {}

    for group_key, members in sorted(source_groups.items()):
        if not any(member["inventory"]["is_nonempty"] for member in members):
            continue
        chunks = sorted({tuple(member["chunk"]) for member in members})
        group_actions[group_key] = {
            "group_key": group_key,
            "dimension": members[0]["dimension"],
            "controller": members[0]["controller"],
            "members": [compact_member(member) for member in members],
            "member_count": len(members),
            "member_set_sha256": digest(sorted(member["key"] for member in members)),
            "member_relationship_sha256": digest(member_relationship_signature(members)),
            "chunks_for_locking_and_validation_only": [list(chunk) for chunk in chunks],
            "cross_chunk": len(chunks) > 1,
            "safe_restore_coords": [],
            "legacy_schema_coords": [],
            "conflict_coords": [],
            "blocker_coords": [],
        }

    for key in sorted(wanted):
        source = source_records[key]
        staging = staging_records.get(key)
        live = live_records.get(key)
        validation = relationship_validation(
            source, staging, live, source_groups, staging_groups, live_groups
        )
        payload = typed_payloads.get(key)
        base = {
            "key": key,
            "dimension": source["dimension"],
            "id": VAULT_ID,
            "pos": source["pos"],
            "controller": source["controller"],
            "group_key": source["group_key"],
            "block_state": source["block_state"],
            "axis": source["block_state"].get("properties", {}).get(
                "axis", source["block_state"].get("properties", {}).get("horizontal_axis")
            ),
            "Size": source["radius"],
            "Length": source["length"],
            "Height": source["length"],
            "source": compact_record(source, include_slots=True),
            "staging": compact_record(staging, include_slots=True),
            "live": compact_record(live, include_slots=True),
            "relationship_validation": validation,
            "target_inventory_payload": payload,
            "target_inventory_payload_source": "converted_staging",
            "postcondition": {
                "id": VAULT_ID,
                "controller": source["controller"],
                "group_member_set_sha256": validation["source_member_set_sha256"],
                "group_relationship_sha256": validation["source_group_relationship_sha256"],
                "block_state": source["block_state"],
                "inventory_content_sha256": staging["inventory"]["content_sha256"] if staging else None,
                "inventory_identity_count_sha256": staging["inventory"]["identity_count_sha256"] if staging else None,
            },
        }

        if not validation["pass"] or payload is None:
            entry = {
                **base,
                "classification": "relationship_or_payload_blocker",
                "cas_allowed": False,
                "reason": "BE/controller/group/member/source-staging identity validation failed or exact typed payload is missing",
            }
            blockers.append(entry)
            group_actions[source["group_key"]]["blocker_coords"].append(source["pos"])
        elif live is None:
            entry = {
                **base,
                "classification": "missing_live_blocker",
                "cas_allowed": False,
                "reason": "live block entity is missing",
            }
            blockers.append(entry)
            group_actions[source["group_key"]]["blocker_coords"].append(source["pos"])
        elif not live["inventory"]["is_nonempty"]:
            entry = {
                **base,
                "classification": "safe_restore_live_empty",
                "cas_allowed": True,
                "required_action": "object_level_restore_from_converted_staging",
                "expected_live": {
                    "id": VAULT_ID,
                    "pos": live["pos"],
                    "controller": live["controller"],
                    "group_member_set_sha256": validation["live_member_set_sha256"],
                    "group_relationship_sha256": validation["live_group_relationship_sha256"],
                    "block_state": live["block_state"],
                    "inventory_format": live["inventory"]["format"],
                    "inventory_content_sha256": live["inventory"]["content_sha256"],
                    "inventory_nonempty_slots": 0,
                    "inventory_total_item_count": 0,
                },
                "cas_rule": "write only if all expected_live and relationship_validation fields still match atomically; otherwise skip",
            }
            safe_restore.append(entry)
            group_actions[source["group_key"]]["safe_restore_coords"].append(source["pos"])
        elif live["inventory"]["format"] == "dense_list" and staging is not None and (
            live["inventory"]["content_sha256"] == staging["inventory"]["content_sha256"]
        ):
            entry = {
                **base,
                "target_inventory_payload": live_schema_payloads.get(key),
                "target_inventory_payload_source": "live_current_dense_list",
                "classification": "legacy_schema_pending_no_restore",
                "cas_allowed": False,
                "schema_cas_allowed": key in live_schema_payloads,
                "required_action": "mandatory_schema_only_reencode_from_live",
                "expected_live": {
                    "id": VAULT_ID,
                    "pos": live["pos"],
                    "controller": live["controller"],
                    "group_member_set_sha256": validation["live_member_set_sha256"],
                    "group_relationship_sha256": validation["live_group_relationship_sha256"],
                    "block_state": live["block_state"],
                    "inventory_format": "dense_list",
                    "inventory_content_sha256": live["inventory"]["content_sha256"],
                },
                "schema_cas_rule": "mandatory schema-only upgrade: derive payload from the exact live dense-list tags and write only if live id/xyz/block-state/axis/controller/full-group relationship/content hash still match atomically; never copy source contents",
                "reason": "live contents are nonempty and preserved, so source restore is forbidden; the legacy envelope must still be upgraded before Create deserializes this chunk.",
            }
            legacy_schema.append(entry)
            group_actions[source["group_key"]]["legacy_schema_coords"].append(source["pos"])
        else:
            entry = {
                **base,
                "classification": "live_nonempty_conflict",
                "cas_allowed": False,
                "required_action": "skip_and_report_conflict",
                "reason": "live inventory is nonempty or differs from staging; never overwrite automatically",
            }
            conflicts.append(entry)
            group_actions[source["group_key"]]["conflict_coords"].append(source["pos"])
        all_entries.append(entry)

    cross_chunk_groups = [value for value in group_actions.values() if value["cross_chunk"]]
    unstable = {
        name: snapshot["unstable_regions"]
        for name, snapshot in (
            ("source", source_snapshot),
            ("staging", staging_snapshot),
            ("live", live_snapshot),
        )
        if snapshot["unstable_regions"]
    }
    summary = {
        "affected_region_files": len(regions),
        "vault_records_in_affected_regions": len(source_records),
        "source_nonempty_members": len(wanted),
        "affected_groups": len(group_actions),
        "cross_chunk_groups": len(cross_chunk_groups),
        "safe_restore_live_empty": len(safe_restore),
        "legacy_schema_pending_no_restore": len(legacy_schema),
        "legacy_schema_mandatory_reencode": len(legacy_schema),
        "live_nonempty_conflicts": len(conflicts),
        "all_live_nonempty_skip": len(legacy_schema) + len(conflicts),
        "blockers": len(blockers),
        "typed_payloads": len(typed_payloads),
        "live_schema_payloads": len(live_schema_payloads),
        "typed_payload_errors": len(payload_errors),
        "unstable_region_snapshots": sum(len(value) for value in unstable.values()),
        "safe_restore_item_slots": sum(entry["staging"]["inventory"]["nonempty_slots"] for entry in safe_restore),
        "safe_restore_total_item_count": sum(entry["staging"]["inventory"]["total_item_count"] for entry in safe_restore),
    }
    report = {
        "schema": 3,
        "read_only": True,
        "mode": "object_level_compare_and_set",
        "world_replacement": False,
        "chunk_overwrite": False,
        "source_world": str(args.source_world.resolve()),
        "staging_world": str(args.staging_world.resolve()),
        "live_world": str(args.live_world.resolve()),
        "raw_forensic_report": str(args.raw_report.resolve()),
        "root_cause": {
            "source_schema": "Create Fly 1.21.11 ItemVaultHandler writes Inventory as a dense list of nonempty ItemStack values and reads them sequentially.",
            "target_schema": "Create 6.0.10 NeoForge calls ItemStackHandler.deserializeNBT(compound.getCompound(\"Inventory\")); it requires Inventory={Size:Int,Items:[...Slot:Int...]}.",
            "observed_failure": "The converted staging still contains dense-list item-vault inventories. On target first load, 1,207 source-nonempty members were persisted as empty NeoForge handlers.",
            "conversion_run_conclusion": "The converter build recorded in conversion-complete.json did not translate create:item_vault inventories in the produced staging.",
            "current_tool_note": "The current workspace converter is a different build and now contains an item-vault converter plus call site; the historical gap must not be inferred to remain in the current tool.",
        },
        "converter_provenance": converter_provenance,
        "summary": summary,
        "snapshot_summaries": {
            "source": source_snapshot,
            "staging": staging_snapshot,
            "live": live_snapshot,
        },
        "unstable_regions": unstable,
        "group_actions": list(group_actions.values()),
        "safe_restore_ledger": safe_restore,
        "legacy_schema_pending": legacy_schema,
        "live_nonempty_conflicts": conflicts,
        "live_nonempty_skip_ledger": [
            {"key": entry["key"], "classification": entry["classification"]}
            for entry in legacy_schema + conflicts
        ],
        "blockers": blockers,
        "typed_payload_errors": payload_errors,
        "all_source_nonempty_entries": [
            {
                "key": entry["key"],
                "classification": entry["classification"],
                "group_key": entry["group_key"],
            }
            for entry in all_entries
        ],
        "safety_contract": [
            "Never replace the world or any whole chunk.",
            "Restore only source/staging-nonempty coordinates whose live inventory is still empty.",
            "Revalidate id, xyz, Controller, full group member set, live empty content hash, and payload SHA-256 immediately before mutation.",
            "Treat every live-nonempty NeoForge-handler coordinate as skip/no-overwrite.",
            "For a live nonempty dense-list coordinate that exactly matches its own expected hash, perform a mandatory schema-only re-encode from the live tags; never restore its contents from source/staging.",
            "Include each member's block-state id, full properties, and axis in the full-group relationship hash.",
            "Lock or serialize all chunks touched by one multiblock group while checking and applying that group's eligible coordinates.",
            "If any CAS predicate changes, skip that coordinate/group and emit an audit record; never fall back to unconditional write.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Create Item Vault Object-level CAS OTA Ledger",
        "",
        "Read-only forensic output. It does not replace the world, overwrite chunks, or modify any block entity.",
        "",
        "## Exact scope",
        "",
        f"- Vault records in the `{summary['affected_region_files']}` affected region files: `{summary['vault_records_in_affected_regions']}`.",
        f"- Source-nonempty vault members: `{summary['source_nonempty_members']}` across `{summary['affected_groups']}` controller groups.",
        f"- Cross-chunk controller groups: `{summary['cross_chunk_groups']}`.",
        f"- Safe object-level restore (live empty): `{summary['safe_restore_live_empty']}` coordinates, `{summary['safe_restore_item_slots']}` occupied slots, `{summary['safe_restore_total_item_count']}` items.",
        f"- Live dense-list contents that forbid source restore but require mandatory live-derived schema re-encode: `{summary['legacy_schema_mandatory_reencode']}` coordinates.",
        f"- Live nonempty conflicts; mandatory skip: `{summary['live_nonempty_conflicts']}` coordinates.",
        f"- All live-nonempty coordinates skipped by the source-restore path: `{summary['all_live_nonempty_skip']}`; the 87 dense-list entries still use their separate live-derived schema CAS path.",
        f"- Validation/payload blockers: `{summary['blockers']}`; payload extraction errors: `{summary['typed_payload_errors']}`.",
        f"- Regions changed during read: `{summary['unstable_region_snapshots']}`.",
        "",
        "## CAS contract",
        "",
    ]
    for rule in report["safety_contract"]:
        lines.append(f"- {rule}")
    lines.extend([
        "",
        "## Typed payload",
        "",
        "Every safe entry contains an uncompressed, big-endian binary NBT payload (base64 + SHA-256), with an empty root name and `Content=Inventory`. Original converted-staging tag types are preserved; only `Slot:Int(index)` and `Size:Int(20)` are added.",
        "",
        "## Manifest",
        "",
        f"- `{args.output.resolve()}`",
    ])
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"status": "PASS" if not blockers and not payload_errors and not unstable else "BLOCKED", **summary, "output": str(args.output.resolve())}, ensure_ascii=False, indent=2))
    return 0 if not blockers and not payload_errors and not unstable else 2


if __name__ == "__main__":
    raise SystemExit(main())
