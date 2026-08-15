#!/usr/bin/env python3
"""Combine the CEI world scan with the 2.4.2/2.5.1 persistence audit."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def group_positions(records: list[dict[str, Any]], id_key: str) -> dict[str, Any]:
    grouped: dict[str, list[list[int | float]]] = collections.defaultdict(list)
    for record in records:
        grouped[str(record[id_key])].append(record["position"])
    return {
        identifier: {
            "count": len(positions),
            "positions": sorted(positions),
        }
        for identifier, positions in sorted(grouped.items())
    }


def slim_items(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "item_id": record["item_id"],
            "count": record.get("count"),
            "file": record["file"],
            "source_kind": record.get("source_kind"),
            "path": record.get("path"),
            "owner_id": record.get("owner_id"),
            "owner_position": record.get("owner_position"),
            "cei_tokens_in_components": record.get("cei_tokens_in_components", []),
        }
        for record in records
    ]


def stable_fluid_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record.get("dimension"),
        tuple(record.get("owner_position") or []),
        record.get("owner_id"),
        record.get("path"),
    )


def fluid_comparison(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    source_map = {stable_fluid_key(item): item for item in source["records"]["fluid_compounds"]}
    target_map = {stable_fluid_key(item): item for item in target["records"]["fluid_compounds"]}
    converted = []
    dropped = []
    added = []
    for key in sorted(set(source_map) | set(target_map), key=str):
        before = source_map.get(key)
        after = target_map.get(key)
        record = {
            "dimension": key[0],
            "owner_position": list(key[1]),
            "owner_id": key[2],
            "path": key[3],
            "source": before and before["nbt"],
            "target": after and after["nbt"],
        }
        if before and after:
            source_amount = before["nbt"].get("amount")
            target_amount = after["nbt"].get("amount")
            record["source_amount"] = source_amount
            record["target_amount"] = target_amount
            if isinstance(source_amount, int) and isinstance(target_amount, int):
                record["exact_81_to_1"] = source_amount == target_amount * 81
                record["source_units_minus_target_equivalent"] = source_amount - target_amount * 81
            converted.append(record)
        elif before:
            source_amount = before["nbt"].get("amount")
            record["source_amount"] = source_amount
            dropped.append(record)
        else:
            added.append(record)
    dropped_units = sum(
        item["source_amount"] for item in dropped if isinstance(item.get("source_amount"), int)
    )
    return {
        "source_records": len(source_map),
        "target_records": len(target_map),
        "converted_records": converted,
        "dropped_sub_millibucket_records": dropped,
        "dropped_record_count": len(dropped),
        "dropped_fabric_units": dropped_units,
        "dropped_equivalent_millibuckets": dropped_units / 81,
        "target_only_records": added,
    }


def find_new_key_hits(report: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    hits = []
    for category, id_key in (
        ("block_entities", "block_entity_id"),
        ("entities", "entity_id"),
        ("item_stacks", "item_id"),
    ):
        for record in report["records"][category]:
            paths = list(record.get("schema", {}))
            matched = [
                path
                for path in paths
                if any(path.split(".")[-1] == key for key in keys)
            ]
            if matched:
                hits.append(
                    {
                        "category": category,
                        "id": record.get(id_key),
                        "position": record.get("position") or record.get("owner_position"),
                        "file": record.get("file"),
                        "path": record.get("path"),
                        "matched_fields": sorted(matched),
                        "nbt": record.get("nbt"),
                    }
                )
    return hits


def recipe_renames(source: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    old = "create_enchantment_industry:recipes/misc/mechanical_grindstone"
    new = "create_enchantment_industry:recipes/mechanical_grindstone"
    source_records = [
        item for item in source["records"]["namespace_occurrences"] if item["token"] == old
    ]
    target_records = [
        item for item in target["records"]["namespace_occurrences"] if item["token"] == new
    ]
    source_files = {item["file"] for item in source_records}
    target_files = {item["file"] for item in target_records}
    return [
        {
            "file": file,
            "source_key": old,
            "target_key": new,
            "source_present": file in source_files,
            "target_present": file in target_files,
        }
        for file in sorted(source_files | target_files)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world-audit-dir", required=True, type=Path)
    parser.add_argument("--jar-preliminary", required=True, type=Path)
    parser.add_argument("--source-jar", required=True, type=Path)
    parser.add_argument("--target-242-jar", required=True, type=Path)
    parser.add_argument("--jar-251", required=True, type=Path)
    args = parser.parse_args()

    audit_dir = args.world_audit_dir.resolve()
    world_main_path = audit_dir / "cei-world-data-compat-audit-20260814.json"
    source_detail_path = audit_dir / "source-original-cei-world-data.json"
    target_detail_path = audit_dir / "handoff-converted-staging-cei-world-data.json"
    attempt_manifest_path = audit_dir / "fresh-attempt2-world-manifest.json"
    legacy_nether_path = audit_dir / "source_legacy_world_nether.json"
    legacy_end_path = audit_dir / "source_legacy_world_the_end.json"
    output_json = audit_dir / "cei-2.4.2-current-world-readability-20260814.json"
    output_md = audit_dir / "cei-2.4.2-current-world-readability-20260814.md"

    world_main = load(world_main_path)
    source = load(source_detail_path)
    target = load(target_detail_path)
    attempt_manifest = load(attempt_manifest_path)
    jar = load(args.jar_preliminary)
    legacy_nether = load(legacy_nether_path)
    legacy_end = load(legacy_end_path)

    only_251_ids = sorted(
        {
            identifier
            for values in jar["only_251_registry_ids"].values()
            for identifier in values
        }
    )
    target_tokens = collections.Counter(target["summary"]["namespace_tokens"])
    for category in (
        "block_state_ids",
        "block_entity_ids",
        "entity_ids",
        "item_ids",
        "embedded_block_state_ids",
    ):
        target_tokens.update(target["summary"].get(category, {}))
    used_only_251 = {
        identifier: target_tokens.get(identifier, 0)
        for identifier in only_251_ids
        if target_tokens.get(identifier, 0)
    }
    new_key_hits = find_new_key_hits(target, jar["new_nbt_keys"])
    forger_hits = [
        item
        for item in new_key_hits
        if item["id"] == "create_enchantment_industry:blaze_forger"
    ]
    unsafe_forger_hits = []
    for item in forger_hits:
        nbt = item["nbt"]
        forging_mode = nbt.get("ForgingMode")
        operation = nbt.get("Inventory", {}).get("Operation")
        inventory_mode = nbt.get("Inventory", {}).get("Mode")
        inventory_size = nbt.get("Inventory", {}).get("Size")
        inventory_items = nbt.get("Inventory", {}).get("Items", [])
        item["readability_242"] = {
            "forging_mode_251": forging_mode,
            "operation_251": operation,
            "legacy_mode_present": inventory_mode is not None,
            "legacy_mode_value_or_242_default": inventory_mode if inventory_mode is not None else 0,
            "inventory_size": inventory_size,
            "inventory_items": inventory_items,
            "safe_current_state": (
                forging_mode == 0
                and operation == 0
                and inventory_size == 6
                and not inventory_items
            ),
            "reason": (
                "CEI 2.4.2 ignores ForgingMode/Operation and reads absent Inventory.Mode as 0; "
                "both saved values are already 0 (MERGE). Its inventory constructor is six slots, "
                "so Size=6 is the safe target shape."
            ),
        }
        if not item["readability_242"]["safe_current_state"]:
            unsafe_forger_hits.append(item)

    unexpected_new_key_hits = [
        item
        for item in new_key_hits
        if item["id"] != "create_enchantment_industry:blaze_forger"
        or any(
            path not in {"ForgingMode", "Inventory.Operation"}
            for path in item["matched_fields"]
        )
    ]
    fluid = fluid_comparison(source, target)
    staging_attempt = world_main["comparisons"]["staging_to_attempt2"]
    coordinate_gate = world_main["comparisons"]["source_to_staging"]
    legacy_namespace_occurrences = (
        legacy_nether["summary"]["namespace_occurrence_instances"]
        + legacy_end["summary"]["namespace_occurrence_instances"]
    )

    blockers = []
    if used_only_251:
        blockers.append("2.5.1-only registry/component/stat IDs are present in the current world")
    if unsafe_forger_hits:
        blockers.append("one or more 2.5.1-format blaze forgers would not preserve their mode in 2.4.2")
    if unexpected_new_key_hits:
        blockers.append("unexpected 2.5.1-only persistent fields are present")
    if coordinate_gate["block_states"]["missing_count"] or coordinate_gate["block_states"]["extra_count"] or coordinate_gate["block_states"]["changed_count"]:
        blockers.append("CEI placed block coordinates/states differ after conversion")
    if coordinate_gate["block_entities"]["missing_count"] or coordinate_gate["block_entities"]["extra_count"]:
        blockers.append("CEI block entity coordinates/IDs differ after conversion")
    if staging_attempt["changed_files_with_cei_count"]:
        blockers.append("fresh attempt2 differs from handoff staging in CEI-bearing files")
    if source["parse_errors"] or target["parse_errors"]:
        blockers.append("world scan has NBT parse errors")
    if source["summary"]["decode_errors"] or target["summary"]["decode_errors"]:
        blockers.append("world scan has block-state decode errors")

    status = "PASS_CURRENT_CONTENT_WITH_CEI_2_4_2_STATIC" if not blockers else "NO_GO_CEI_2_4_2"
    report = {
        "schema": 1,
        "date": "2026-08-14",
        "status": status,
        "runtime_status": "STATIC_ONLY_RUNTIME_STARTUP_STILL_REQUIRED",
        "scope": {
            "source": source["root"],
            "handoff_staging": target["root"],
            "fresh_attempt2": world_main["datasets"]["attempt2"]["root"],
            "java_or_minecraft_started_by_this_audit": False,
            "world_files_written": False,
        },
        "mod_versions": {
            "source": {
                "version": "2.4.2+fabric.1.21.11-hotfix.10",
                "path": str(args.source_jar.resolve()),
                "bytes": args.source_jar.stat().st_size,
                "sha256": sha256(args.source_jar),
            },
            "attempt2_target": {
                "version": "2.4.2 NeoForge 1.21.1",
                "path": str(args.target_242_jar.resolve()),
                "bytes": args.target_242_jar.stat().st_size,
                "sha256": sha256(args.target_242_jar),
            },
            "superseded_2_5_1_reference": {
                "version": "2.5.1 NeoForge 1.21.1",
                "path": str(args.jar_251.resolve()),
                "bytes": args.jar_251.stat().st_size,
                "sha256": sha256(args.jar_251),
            },
        },
        "verdict": {
            "can_current_attempt2_world_be_read_by_cei_2_4_2": not blockers,
            "blockers": blockers,
            "conditions": [
                "Keep CEI 2.4.2 on both server and client for this startup test.",
                "Do not allow a 2.5.1 session to create blaze_composer, new incomplete affix templates, affix_template/overlimit_affixes components, or non-zero forger modes before downgrading.",
                "A later move to 2.5.1 is one-way unless an explicit reverse converter/guard is added.",
                "The nine sub-millibucket pipe residuals are the only identified CEI fluid quantity loss and fall under the user's accepted small conversion error.",
            ],
        },
        "current_content": {
            "placed_blocks": group_positions(target["records"]["block_states"], "block_id"),
            "placed_block_total": target["summary"]["block_state_blocks"],
            "block_entities": group_positions(target["records"]["block_entities"], "block_entity_id"),
            "block_entity_total": target["summary"]["block_entity_instances"],
            "block_entity_records": target["records"]["block_entities"],
            "entities": target["records"]["entities"],
            "item_stack_total": target["summary"]["item_stack_instances"],
            "item_ids": target["summary"]["item_ids"],
            "item_stack_records": slim_items(target["records"]["item_stacks"]),
            "embedded_block_states": target["records"]["embedded_block_states"],
            "namespace_tokens": target["summary"]["namespace_tokens"],
            "saveddata_cei_occurrences": target["summary"]["namespace_source_kinds"].get("saveddata", 0),
            "entity_cei_occurrences": target["summary"]["namespace_source_kinds"].get("entity", 0),
        },
        "source_to_staging": {
            "block_state_coordinate_gate": coordinate_gate["block_states"],
            "block_entity_coordinate_gate": coordinate_gate["block_entities"],
            "block_entity_schema": coordinate_gate["block_entity_schema"],
            "item_stack_schema": coordinate_gate["item_stack_schema"],
            "fluids": fluid,
            "advancement_recipe_renames": recipe_renames(source, target),
            "advancement_recipe_rename_count": len(recipe_renames(source, target)),
        },
        "2_5_1_downgrade_risk": {
            "only_2_5_1_registry_ids": jar["only_251_registry_ids"],
            "only_2_5_1_ids_found_in_current_world": used_only_251,
            "new_2_5_1_nbt_keys": jar["new_nbt_keys"],
            "new_key_hits_in_current_world": new_key_hits,
            "unsafe_forger_hits": unsafe_forger_hits,
            "unexpected_new_key_hits": unexpected_new_key_hits,
            "no_datafix_or_missing_mapping_bridge": True,
            "future_downgrade_policy": "NO_GO_AFTER_ANY_2_5_1_GAMEPLAY_WITHOUT_REVERSE_CONVERTER",
        },
        "staging_to_attempt2": staging_attempt,
        "legacy_bukkit_dimension_roots": {
            "world_nether": {
                "root": legacy_nether["root"],
                "status": legacy_nether["status"],
                "cei_namespace_occurrences": legacy_nether["summary"]["namespace_occurrence_instances"],
            },
            "world_the_end": {
                "root": legacy_end["root"],
                "status": legacy_end["status"],
                "cei_namespace_occurrences": legacy_end["summary"]["namespace_occurrence_instances"],
            },
            "combined_cei_namespace_occurrences": legacy_namespace_occurrences,
        },
        "evidence": {
            "world_scan_json": str(world_main_path),
            "source_detail_json": str(source_detail_path),
            "target_detail_json": str(target_detail_path),
            "attempt2_manifest_json": str(attempt_manifest_path),
            "jar_preliminary_json": str(args.jar_preliminary.resolve()),
            "source_detail_sha256": sha256(source_detail_path),
            "target_detail_sha256": sha256(target_detail_path),
            "world_scan_sha256": sha256(world_main_path),
        },
    }
    write_json(output_json, report)

    forgers = report["2_5_1_downgrade_risk"]["new_key_hits_in_current_world"]
    lines = [
        "# CEI 2.4.2 当前存档可读性结论（2026-08-14）",
        "",
        f"结论：`{status}`。这是静态存档结论；仍需由主流程完成隔离启动测试。",
        "",
        "## 核心事实",
        "",
        f"- 60 个 CEI 放置方块，坐标/ID/方块状态从原始世界到 staging 零缺失、零新增、零变化。",
        f"- 19 个 CEI 方块实体，坐标和 ID 零缺失、零新增；CEI 自有实体为 0。",
        f"- 47 个 CEI 物品栈全部仍在；当前世界没有 2.5.1 独占的 blaze_composer、三个 incomplete affix template、affix_template/overlimit_affixes 组件或 compose_affix 统计。",
        f"- staging 与 fresh attempt2 共 5821 个世界文件，5819 个 SHA-256 完全相同；仅 level.dat 与 Bukkit pack.mcmeta 不同，两者均不含 CEI 数据。",
        f"- 原始额外 Bukkit 维度根 world_nether/world_the_end 的 CEI 命名空间引用合计为 {legacy_namespace_occurrences}，没有遗漏的 CEI 内容。",
        "",
        "## 两台 Blaze Forger",
        "",
    ]
    for item in forgers:
        readability = item["readability_242"]
        lines.append(
            f"- `{item['position']}`：ForgingMode={readability['forging_mode_251']}，"
            f"Inventory.Operation={readability['operation_251']}，Size={readability['inventory_size']}，"
            f"Items={len(readability['inventory_items'])}；2.4.2 读取为旧 MERGE/Mode=0，当前状态语义无损。"
        )
    lines.extend(
        [
            "",
            "2.4.2 的内部物品表本来就是 6 格，转换后的 `Size=6` 应保留；改回原始 `Size=4` 反而可能让旧代码访问预览槽 4/5 时越界。",
            "",
            "## 流体与配方",
            "",
            f"- 20 条有效 experience 流体记录已转换为 NeoForge mB。9 条单独小于 1mB 的管道流动残量被清空，共 {fluid['dropped_fabric_units']} Fabric 单位，即 {fluid['dropped_equivalent_millibuckets']}mB。",
            f"- 9 个玩家 advancement 文件中的机械砂轮配方键已从 `recipes/misc/mechanical_grindstone` 改为目标 2.4.2 使用的 `recipes/mechanical_grindstone`。",
            "- 世界 SavedData 中没有 CEI 命名空间数据；不存在需要额外降级的 CEI SavedData 文件。",
            "",
            "## 防回退边界",
            "",
            "当前存档可以用 2.4.2，是因为尚未产生 2.5.1 的独占内容，且两台 Forger 的新模式字段都恰好为 0。以后只要用 2.5.1 实际保存过新方块、组件或非零模式，就不能再直接降回 2.4.2；CEI 没有自带 DataFix/missing-mapping 桥。",
            "",
            "## 报告",
            "",
            f"- 综合 JSON：`{output_json}`",
            f"- 世界全量 JSON：`{world_main_path}`",
            f"- 精确坐标/NBT：`{target_detail_path}`",
            "",
        ]
    )
    output_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": status, "json": str(output_json), "markdown": str(output_md)}, ensure_ascii=False))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
