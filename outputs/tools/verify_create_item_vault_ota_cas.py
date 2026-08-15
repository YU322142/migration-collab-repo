from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import nbtlib


def plain(value: Any) -> Any:
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    return value


def digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def member_relationship_signature(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for member in members:
        block_state = member["block_state"]
        properties = block_state.get("properties", {})
        output.append({
            "key": member["key"],
            "controller": member["controller"],
            "block_state": {
                "name": block_state.get("name"),
                "properties": properties,
                "axis": properties.get("axis", properties.get("horizontal_axis")),
                "decode": block_state.get("decode"),
            },
            "Size": member["Size"],
            "Length": member["Length"],
        })
    return sorted(output, key=lambda item: item["key"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Create item-vault CAS ledger")
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    raw = args.ledger.read_bytes()
    report = json.loads(raw.decode("utf-8"))
    summary = report["summary"]
    safe = report["safe_restore_ledger"]
    legacy = report["legacy_schema_pending"]
    conflicts = report["live_nonempty_conflicts"]
    skip = report["live_nonempty_skip_ledger"]
    blockers = report["blockers"]
    all_entries = report["all_source_nonempty_entries"]
    failures: list[str] = []

    require(report.get("schema") == 3, "ledger schema is not 3", failures)
    require(report.get("read_only") is True, "ledger is not marked read-only", failures)
    require(report.get("mode") == "object_level_compare_and_set", "ledger mode is not object-level CAS", failures)
    require(report.get("world_replacement") is False, "world replacement is not disabled", failures)
    require(report.get("chunk_overwrite") is False, "chunk overwrite is not disabled", failures)
    require(not report.get("unstable_regions"), "one or more region files changed during read", failures)
    require(not blockers, "ledger contains blockers", failures)
    require(not report.get("typed_payload_errors"), "ledger contains typed payload extraction errors", failures)
    provenance = report.get("converter_provenance", {})
    require(bool(provenance.get("conversion_time_converter")), "conversion-time converter fingerprint is missing", failures)
    require(provenance.get("same_as_conversion_time") is False, "current converter unexpectedly equals conversion-time build", failures)
    require(provenance.get("current_converter", {}).get("contains_item_vault_converter") is True, "current converter lacks item-vault converter", failures)
    require(provenance.get("current_converter", {}).get("contains_item_vault_call_site") is True, "current converter lacks item-vault call site", failures)

    require(len(safe) == summary["safe_restore_live_empty"], "safe count mismatch", failures)
    require(len(legacy) == summary["legacy_schema_pending_no_restore"], "legacy count mismatch", failures)
    require(len(conflicts) == summary["live_nonempty_conflicts"], "conflict count mismatch", failures)
    require(len(skip) == summary["all_live_nonempty_skip"], "skip count mismatch", failures)
    require(len(all_entries) == summary["source_nonempty_members"], "source-nonempty count mismatch", failures)
    require(summary["legacy_schema_mandatory_reencode"] == len(legacy), "mandatory schema re-encode count mismatch", failures)
    require(summary["live_schema_payloads"] == len(legacy), "live-derived schema payload count mismatch", failures)
    require(len(safe) + len(legacy) + len(conflicts) + len(blockers) == len(all_entries), "classification partition mismatch", failures)

    categories = {"safe": safe, "legacy": legacy, "conflict": conflicts, "blocker": blockers}
    seen: dict[str, str] = {}
    for category, entries in categories.items():
        for entry in entries:
            key = entry["key"]
            if key in seen:
                failures.append(f"duplicate key {key} in {seen[key]} and {category}")
            seen[key] = category
    require(set(seen) == {entry["key"] for entry in all_entries}, "classification keys do not match all entries", failures)
    require({entry["key"] for entry in skip} == {entry["key"] for entry in legacy + conflicts}, "unified nonempty skip ledger mismatch", failures)

    payloads_verified = 0
    for entry in safe + legacy + conflicts:
        key = entry["key"]
        require(entry["relationship_validation"]["pass"] is True, f"{key}: relationship validation failed", failures)
        require(all(entry["relationship_validation"]["checks"].values()), f"{key}: one or more relationship checks failed", failures)
        block_state = entry["block_state"]
        axis = block_state.get("properties", {}).get("axis", block_state.get("properties", {}).get("horizontal_axis"))
        require(block_state.get("name") == "create:item_vault", f"{key}: block state is not create:item_vault", failures)
        require(block_state.get("decode") == "ok", f"{key}: block state decode is not ok", failures)
        require(axis in {"x", "z"}, f"{key}: invalid/missing vault axis", failures)
        require(axis == entry.get("axis"), f"{key}: top-level axis mismatch", failures)
        payload = entry["target_inventory_payload"]
        expected_payload_source = "live_current_dense_list" if entry["classification"] == "legacy_schema_pending_no_restore" else "converted_staging"
        require(entry.get("target_inventory_payload_source") == expected_payload_source, f"{key}: payload source mismatch", failures)
        decoded = base64.b64decode(payload["base64"], validate=True)
        require(len(decoded) == payload["byte_length"], f"{key}: payload byte length mismatch", failures)
        require(hashlib.sha256(decoded).hexdigest() == payload["sha256"], f"{key}: payload SHA-256 mismatch", failures)
        typed = nbtlib.File.parse(io.BytesIO(decoded), byteorder="big")
        require(typed.root_name == "", f"{key}: payload root name is not empty", failures)
        inventory = typed.get("Content")
        require(isinstance(inventory, nbtlib.Compound), f"{key}: Content is not Compound", failures)
        if not isinstance(inventory, nbtlib.Compound):
            continue
        require(isinstance(inventory.get("Size"), nbtlib.Int), f"{key}: Size is not IntTag", failures)
        require(int(inventory.get("Size", 0)) == 20, f"{key}: Size is not 20", failures)
        items = inventory.get("Items")
        require(isinstance(items, list), f"{key}: Items is not a list", failures)
        if not isinstance(items, list):
            continue
        expected_slots = entry["live"]["inventory"]["slots"] if entry["classification"] == "legacy_schema_pending_no_restore" else entry["staging"]["inventory"]["slots"]
        require(len(items) == len(expected_slots), f"{key}: payload/source item length mismatch", failures)
        for index, (item, expected) in enumerate(zip(items, expected_slots)):
            require(isinstance(item, nbtlib.Compound), f"{key}: item {index} is not Compound", failures)
            require(isinstance(item.get("Slot"), nbtlib.Int), f"{key}: item {index} Slot is not IntTag", failures)
            require(int(item.get("Slot", -1)) == expected["slot"], f"{key}: item {index} Slot mismatch", failures)
            actual_stack = plain(item)
            actual_stack.pop("Slot", None)
            require(actual_stack == expected["stack"], f"{key}: item {index} stack differs from staging", failures)
        payloads_verified += 1

    for entry in safe:
        key = entry["key"]
        require(entry.get("cas_allowed") is True, f"{key}: safe entry CAS is not allowed", failures)
        require(entry.get("required_action") == "object_level_restore_from_converted_staging", f"{key}: safe required action mismatch", failures)
        require(entry["relationship_validation"]["pass"] is True, f"{key}: relationship validation failed", failures)
        require(entry["staging"]["inventory"]["is_nonempty"] is True, f"{key}: staging is empty", failures)
        require(entry["live"]["inventory"]["is_nonempty"] is False, f"{key}: live is nonempty", failures)
        require(entry["expected_live"]["inventory_nonempty_slots"] == 0, f"{key}: expected live slots not zero", failures)
        require(entry["expected_live"]["inventory_total_item_count"] == 0, f"{key}: expected live item count not zero", failures)
        require(entry["expected_live"]["block_state"] == entry["live"]["block_state"], f"{key}: expected live block state mismatch", failures)
        require(entry["expected_live"]["group_relationship_sha256"] == entry["relationship_validation"]["live_group_relationship_sha256"], f"{key}: expected live group relationship hash mismatch", failures)

    for entry in legacy:
        key = entry["key"]
        require(entry.get("cas_allowed") is False, f"{key}: legacy entry unexpectedly allows restore", failures)
        require(entry.get("schema_cas_allowed") is True, f"{key}: legacy schema CAS is not allowed", failures)
        require(entry.get("required_action") == "mandatory_schema_only_reencode_from_live", f"{key}: legacy required action mismatch", failures)
        require(entry["live"]["inventory"]["is_nonempty"] is True, f"{key}: legacy live inventory is empty", failures)
        require(entry["live"]["inventory"]["format"] == "dense_list", f"{key}: legacy inventory is not dense list", failures)
        require(entry["live"]["inventory"]["content_sha256"] == entry["staging"]["inventory"]["content_sha256"], f"{key}: legacy/staging contents differ", failures)
        require(entry["expected_live"]["block_state"] == entry["live"]["block_state"], f"{key}: legacy expected block state mismatch", failures)
        require(entry["expected_live"]["group_relationship_sha256"] == entry["relationship_validation"]["live_group_relationship_sha256"], f"{key}: legacy group relationship hash mismatch", failures)

    for entry in conflicts:
        key = entry["key"]
        require(entry.get("cas_allowed") is False, f"{key}: conflict unexpectedly allows restore", failures)
        require(entry.get("required_action") == "skip_and_report_conflict", f"{key}: conflict required action mismatch", failures)
        require(entry["live"]["inventory"]["is_nonempty"] is True, f"{key}: conflict live inventory is empty", failures)

    groups = report["group_actions"]
    require(len(groups) == summary["affected_groups"], "affected group count mismatch", failures)
    require(sum(bool(group["cross_chunk"]) for group in groups) == summary["cross_chunk_groups"], "cross-chunk group count mismatch", failures)
    group_action_keys: set[str] = set()
    for group in groups:
        member_keys = sorted(member["key"] for member in group["members"])
        require(len(member_keys) == group["member_count"], f"{group['group_key']}: member count mismatch", failures)
        require(digest(member_keys) == group["member_set_sha256"], f"{group['group_key']}: member-set hash mismatch", failures)
        relationship = member_relationship_signature(group["members"])
        require(digest(relationship) == group["member_relationship_sha256"], f"{group['group_key']}: member relationship hash mismatch", failures)
        for member in group["members"]:
            state = member["block_state"]
            axis = state.get("properties", {}).get("axis", state.get("properties", {}).get("horizontal_axis"))
            require(state.get("name") == "create:item_vault", f"{member['key']}: group member block state mismatch", failures)
            require(state.get("decode") == "ok", f"{member['key']}: group member state decode failed", failures)
            require(axis == member.get("axis") and axis in {"x", "z"}, f"{member['key']}: group member axis mismatch", failures)
        action_count = sum(len(group[name]) for name in ("safe_restore_coords", "legacy_schema_coords", "conflict_coords", "blocker_coords"))
        source_nonempty_in_group = sum(
            1 for entry in all_entries if entry["group_key"] == group["group_key"]
        )
        require(action_count == source_nonempty_in_group, f"{group['group_key']}: action count does not cover nonempty members", failures)
        group_action_keys.update(entry["key"] for entry in all_entries if entry["group_key"] == group["group_key"])
    require(group_action_keys == {entry["key"] for entry in all_entries}, "group actions do not cover all entries", failures)

    calculated_safe_slots = sum(entry["staging"]["inventory"]["nonempty_slots"] for entry in safe)
    calculated_safe_items = sum(entry["staging"]["inventory"]["total_item_count"] for entry in safe)
    require(calculated_safe_slots == summary["safe_restore_item_slots"], "safe slot total mismatch", failures)
    require(calculated_safe_items == summary["safe_restore_total_item_count"], "safe item total mismatch", failures)

    result = {
        "schema": 1,
        "status": "PASS" if not failures else "FAIL",
        "ledger": str(args.ledger.resolve()),
        "ledger_bytes": len(raw),
        "ledger_sha256": hashlib.sha256(raw).hexdigest(),
        "payloads_verified": payloads_verified,
        "safe_restore_entries": len(safe),
        "legacy_schema_entries": len(legacy),
        "live_nonempty_conflicts": len(conflicts),
        "affected_groups": len(groups),
        "cross_chunk_groups": summary["cross_chunk_groups"],
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Create Item Vault CAS Ledger Verification",
        "",
        f"- Status: `{result['status']}`",
        f"- Ledger SHA-256: `{result['ledger_sha256']}`",
        f"- Typed payloads independently decoded and checked: `{payloads_verified}`",
        f"- Safe restore / legacy skip / live conflict: `{len(safe)}` / `{len(legacy)}` / `{len(conflicts)}`",
        f"- Controller groups / cross-chunk groups: `{len(groups)}` / `{summary['cross_chunk_groups']}`",
        f"- Failures: `{len(failures)}`",
    ]
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
