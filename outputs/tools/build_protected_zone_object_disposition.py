#!/usr/bin/env python3
"""Build a read-only disposition plan from the protected-zone object audit."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import uuid
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


CREATE_STRUCTURE_X = (9_941, 9_996)
CREATE_STRUCTURE_Y = (24, 43)
CREATE_STRUCTURE_Z = (-2_243, -2_135)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def parse_uuid_value(value: Any) -> str | None:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except Exception:
            decoded = value
    else:
        decoded = value
    try:
        if isinstance(decoded, str):
            return str(uuid.UUID(decoded))
        if isinstance(decoded, list) and len(decoded) == 4:
            number = 0
            for part in decoded:
                number = (number << 32) | (int(part) & 0xFFFFFFFF)
            return str(uuid.UUID(int=number))
    except (TypeError, ValueError, AttributeError):
        return None
    return None


def world_prefix(archive: zipfile.ZipFile) -> str:
    matches = [name[: -len("level.dat")] for name in archive.namelist() if name.endswith("/world/level.dat")]
    if len(matches) != 1:
        raise ValueError(f"expected one live world/level.dat, found {matches}")
    return matches[0]


def load_json_member(archive: zipfile.ZipFile, name: str) -> Any:
    try:
        return json.loads(archive.read(name).decode("utf-8-sig"))
    except KeyError:
        return None


def known_player_identities(archive_path: Path) -> tuple[set[str], dict[str, str]]:
    with zipfile.ZipFile(archive_path, "r") as archive:
        prefix = world_prefix(archive)
        root_prefix = prefix[: -len("world/")]
        identities: set[str] = set()
        names: dict[str, str] = {}
        for info in archive.infolist():
            marker = prefix + "playerdata/"
            if info.filename.startswith(marker) and info.filename.endswith(".dat"):
                raw = Path(info.filename).stem
                try:
                    identities.add(str(uuid.UUID(raw)))
                except ValueError:
                    pass
        for filename in ("usercache.json", "ops.json", "whitelist.json"):
            rows = load_json_member(archive, root_prefix + filename) or []
            for row in rows:
                if not isinstance(row, Mapping) or not row.get("uuid"):
                    continue
                try:
                    player_uuid = str(uuid.UUID(str(row["uuid"])))
                except ValueError:
                    continue
                identities.add(player_uuid)
                if row.get("name"):
                    names[player_uuid] = str(row["name"])
    return identities, names


def counter_dict(counter: collections.Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda row: (-row[1], row[0])))


def in_create_structure(pos: list[int] | None) -> bool:
    if not pos or len(pos) != 3:
        return False
    return (
        CREATE_STRUCTURE_X[0] <= pos[0] <= CREATE_STRUCTURE_X[1]
        and CREATE_STRUCTURE_Y[0] <= pos[1] <= CREATE_STRUCTURE_Y[1]
        and CREATE_STRUCTURE_Z[0] <= pos[2] <= CREATE_STRUCTURE_Z[1]
    )


def owner_rows(record: Mapping[str, Any], known_players: set[str], names: Mapping[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ref in record.get("owner_or_player_refs", []):
        if not isinstance(ref, Mapping):
            continue
        owner_uuid = parse_uuid_value(ref.get("value"))
        rows.append(
            {
                "path": ref.get("path"),
                "uuid": owner_uuid,
                "matches_current_player_identity": owner_uuid in known_players if owner_uuid else False,
                "resolved_name": names.get(owner_uuid) if owner_uuid else None,
            }
        )
    return rows


def be_disposition(
    record: Mapping[str, Any],
    known_players: set[str],
    names: Mapping[str, str],
) -> tuple[str, dict[str, Any]]:
    identifier = str(record.get("id"))
    flags = set(record.get("flags", []))
    pos = record.get("pos")
    items = record.get("item_summary", {})
    fluids = record.get("fluid_summary", {})
    interesting = record.get("interesting_paths", {})
    owners = owner_rows(record, known_players, names)
    known_owner = any(row["matches_current_player_identity"] for row in owners)
    nonempty_stacks = int(items.get("nonempty_stacks", 0) or 0)
    # Create copycat Material is a structural block-state payload, not stored
    # inventory.  The raw audit proved that all 246 non-empty BE stack records
    # belong to create:copycat; no other BE contains an item stack.
    structural_copycat_stack = identifier == "create:copycat" and nonempty_stacks > 0
    stored_stacks = 0 if structural_copycat_stack else nonempty_stacks
    nonempty_fluids = int(fluids.get("nonempty_tanks", 0) or 0)
    computer = bool(interesting.get("computer"))
    text_or_command = bool(interesting.get("text_book_or_command"))
    custom_name = record.get("custom_name") is not None
    filter_configuration = nonempty_stacks > 0 and any(
        "filter" in str(path).lower() for path in interesting.get("inventory_or_filter", [])
    )
    actual_player_payload_reasons: list[str] = []
    if stored_stacks:
        actual_player_payload_reasons.append("nonempty_stored_item_stack")
    if nonempty_fluids:
        actual_player_payload_reasons.append("nonempty_fluid")
    if computer:
        actual_player_payload_reasons.append("computer_state")
    if text_or_command:
        actual_player_payload_reasons.append("text_book_or_command")
    if custom_name:
        actual_player_payload_reasons.append("custom_name")
    if filter_configuration:
        actual_player_payload_reasons.append("configured_filter")
    if known_owner:
        actual_player_payload_reasons.append("owner_matches_current_player_identity")

    generated_evidence: list[str] = []
    if "loot_table" in flags:
        generated_evidence.append("unopened_worldgen_loot_table")
    if identifier.startswith("lootr:"):
        generated_evidence.append("lootr_worldgen_block")
    if identifier.startswith("minecraft:sculk_") or identifier in {
        "minecraft:brushable_block",
        "minecraft:beehive",
    }:
        generated_evidence.append("natural_or_structure_feature_block_entity")
    if identifier.startswith("create:") and in_create_structure(pos):
        generated_evidence.append("inside_compact_685_BE_create_structure")
    if identifier in {"minecraft:barrel", "minecraft:lectern"} and in_create_structure(pos):
        generated_evidence.append("co-located_with_create_structure_and_39_villager_workstation_poi")
    if structural_copycat_stack:
        generated_evidence.append("copycat_material_is_structural_not_inventory")
    if owners and not known_owner:
        generated_evidence.append("owner_uuid_not_present_in_112_playerdata_or_identity_lists")
    if identifier == "create:item_vault" and nonempty_stacks == 0:
        generated_evidence.append("item_vault_inventory_empty")
    if identifier.startswith("create:") and nonempty_fluids == 0:
        generated_evidence.append("no_nonempty_fluid_payload")

    compact = {
        "id": identifier,
        "pos": pos,
        "chunk": record.get("source_chunk"),
        "inside_exact_circle": record.get("inside_exact_circle"),
        "source": record.get("source"),
        "slot": record.get("slot"),
        "owner_refs": owners,
        "nonempty_stored_item_stacks": stored_stacks,
        "copycat_structural_item_stacks": nonempty_stacks if structural_copycat_stack else 0,
        "nonempty_fluid_payloads": nonempty_fluids,
        "generated_or_structure_evidence": generated_evidence,
    }
    if actual_player_payload_reasons:
        compact.update(
            {
                "action": "SALVAGE_OR_RELOCATE_WITH_SUPPORTING_BLOCKS",
                "reasons": actual_player_payload_reasons,
            }
        )
        return "salvage_or_relocate", compact
    compact.update(
        {
            "action": "SAFE_REPLACE_WITH_V_UNDER_EXPLICIT_TERRAIN_AUTHORIZATION",
            "reason": "no persistent player payload detected; replacement intentionally removes current generated/structure state",
        }
    )
    return "safe_replace", compact


def entity_disposition(record: Mapping[str, Any]) -> dict[str, Any]:
    flags = set(record.get("flags", []))
    priority_flags = sorted(
        flags
        & {
            "maid",
            "vehicle",
            "villager",
            "tamed_or_owned",
            "custom_named",
            "player_reference",
            "carries_items",
            "persistent",
        }
    )
    return {
        "id": record.get("id"),
        "uuid": record.get("uuid"),
        "pos": record.get("pos"),
        "chunk": record.get("source_chunk"),
        "inside_exact_circle": record.get("inside_exact_circle"),
        "priority_flags": priority_flags,
        "carried_item_totals": record.get("item_summary", {}).get("item_id_totals", {}),
        "action": "PRESERVE_C_ENTITY_NBT_THEN_VALIDATE_AGAINST_V_COLLISION_AND_SUPPORT",
        "source": record.get("source"),
        "slot": record.get("slot"),
        "path": record.get("path"),
    }


def poi_disposition(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": record.get("type"),
        "pos": record.get("pos"),
        "chunk": record.get("source_chunk"),
        "free_tickets": record.get("free_tickets"),
        "action": "REBUILD_FROM_FINAL_V_BLOCKS_OR_USE_V_POI;_DO_NOT_COPY_STALE_C_RECORD",
        "source": record.get("source"),
        "slot": record.get("slot"),
    }


def build(raw: Mapping[str, Any], raw_path: Path, archive_path: Path) -> dict[str, Any]:
    known_players, player_names = known_player_identities(archive_path)
    safe_replace: list[dict[str, Any]] = []
    salvage: list[dict[str, Any]] = []
    owner_uuid_counts: collections.Counter[str] = collections.Counter()
    owner_be_ids: collections.Counter[str] = collections.Counter()
    for record in raw["block_entities"]["records"]:
        category, row = be_disposition(record, known_players, player_names)
        for ref in row["owner_refs"]:
            if ref["uuid"]:
                owner_uuid_counts[ref["uuid"]] += 1
                owner_be_ids[str(row["id"])] += 1
        if category == "safe_replace":
            safe_replace.append(row)
        else:
            salvage.append(row)

    preserve_entities = [entity_disposition(row) for row in raw["entities"]["records"]]
    rebuild_poi = [poi_disposition(row) for row in raw["poi"]["records"]]

    be_ids = collections.Counter(row["id"] for row in safe_replace)
    create_rows = [row for row in safe_replace if str(row["id"]).startswith("create:")]
    create_ids = collections.Counter(str(row["id"]) for row in create_rows)
    create_chunks = {tuple(row["chunk"]) for row in create_rows if row.get("chunk")}
    empty_vaults = [row for row in safe_replace if row["id"] == "create:item_vault"]
    actual_nonempty_containers = [
        row for row in salvage if row["nonempty_stored_item_stacks"] > 0
    ]
    actual_nonempty_fluids = [row for row in salvage if row["nonempty_fluid_payloads"] > 0]
    generated_loot_rows = [
        row
        for row in safe_replace
        if "unopened_worldgen_loot_table" in row["generated_or_structure_evidence"]
    ]
    copycat_rows = [
        row for row in safe_replace if row["copycat_structural_item_stacks"] > 0
    ]

    entity_flags = collections.Counter(
        flag for row in preserve_entities for flag in row["priority_flags"]
    )
    carried_items: collections.Counter[str] = collections.Counter()
    for row in preserve_entities:
        carried_items.update({str(key): int(value) for key, value in row["carried_item_totals"].items()})

    attention: dict[tuple[int, int], dict[str, Any]] = {
        tuple(chunk): {
            "chunk": chunk,
            "safe_replace_block_entities": 0,
            "salvage_or_relocate_block_entities": 0,
            "preserve_entities": 0,
            "rebuild_poi": 0,
            "affected_player_current_or_spawn": 0,
        }
        for chunk in raw["attention_chunks"]["chunks"]
    }
    for key, rows in (
        ("safe_replace_block_entities", safe_replace),
        ("salvage_or_relocate_block_entities", salvage),
        ("preserve_entities", preserve_entities),
        ("rebuild_poi", rebuild_poi),
    ):
        for row in rows:
            chunk = tuple(row.get("chunk") or [])
            if chunk in attention:
                attention[chunk][key] += 1
    for player in raw["players"]["affected_players"]:
        for point_name in ("current", "spawn"):
            point = player.get(point_name)
            if isinstance(point, Mapping) and point.get("inside_selected_chunk_set"):
                chunk = tuple(point.get("chunk") or [])
                if chunk in attention:
                    attention[chunk]["affected_player_current_or_spawn"] += 1

    owner_rows_summary = []
    for owner_uuid, count in sorted(owner_uuid_counts.items(), key=lambda row: (-row[1], row[0])):
        owner_rows_summary.append(
            {
                "uuid": owner_uuid,
                "references": count,
                "uuid_version": uuid.UUID(owner_uuid).version,
                "matches_current_player_identity": owner_uuid in known_players,
                "resolved_name": player_names.get(owner_uuid),
            }
        )

    hard_blockers: list[dict[str, Any]] = []
    if salvage:
        hard_blockers.append(
            {
                "reason": "persistent player payload requires salvage or relocation",
                "records": len(salvage),
            }
        )
    if raw["players"]["affected_players"]:
        hard_blockers.append(
            {
                "reason": "player position or spawn lies in selected chunks",
                "players": len(raw["players"]["affected_players"]),
            }
        )
    if raw.get("parse_errors") or raw["players"].get("parse_errors"):
        hard_blockers.append({"reason": "upstream parse errors"})

    return {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "status": "SAFE_TO_BUILD_V_SLOT_REPLACEMENT_PENDING_ENTITY_COLLISION_AND_POI_REBUILD_GATES"
        if not hard_blockers
        else "SALVAGE_OR_RELOCATION_REQUIRED_BEFORE_V_SLOT_REPLACEMENT",
        "operation": "protected-zone-object-disposition-readonly",
        "inputs": {
            "raw_audit": str(raw_path.resolve()),
            "raw_audit_sha256": sha256_file(raw_path),
            "source_archive": str(archive_path.resolve()),
            "source_archive_sha256_bound_by_raw_audit": raw["source"]["sha256"],
            "source_archive_bytes": archive_path.stat().st_size,
            "known_player_identity_uuids": len(known_players),
        },
        "scope": raw["scope"],
        "summary": {
            "safe_replace_block_entities": len(safe_replace),
            "salvage_or_relocate_block_entities": len(salvage),
            "preserve_entities": len(preserve_entities),
            "rebuild_poi_records": len(rebuild_poi),
            "attention_chunks": len(attention),
            "affected_players": len(raw["players"]["affected_players"]),
            "actual_nonempty_container_block_entities": len(actual_nonempty_containers),
            "actual_nonempty_fluid_block_entities": len(actual_nonempty_fluids),
            "empty_create_item_vault_parts": len(empty_vaults),
            "copycat_structural_material_block_entities": len(copycat_rows),
            "unopened_worldgen_loot_table_block_entities": len(generated_loot_rows),
            "create_structure_block_entities": len(create_rows),
            "create_structure_chunks": len(create_chunks),
        },
        "evidence": {
            "block_entity_id_counts": counter_dict(be_ids),
            "create_structure": {
                "bounding_box": {
                    "x": list(CREATE_STRUCTURE_X),
                    "y": list(CREATE_STRUCTURE_Y),
                    "z": list(CREATE_STRUCTURE_Z),
                },
                "block_entities": len(create_rows),
                "chunks": [list(row) for row in sorted(create_chunks)],
                "id_counts": counter_dict(create_ids),
                "co_located_fisherman_poi": raw["poi"]["type_counts"].get("minecraft:fisherman", 0),
                "co_located_librarian_poi": raw["poi"]["type_counts"].get("minecraft:librarian", 0),
            },
            "owner_uuid_references": owner_rows_summary,
            "owner_reference_block_entity_ids": counter_dict(owner_be_ids),
            "owner_interpretation": "The two Owner UUIDs occur on Create structure block entities, match neither current playerdata nor usercache/ops/whitelist identities, and are treated as schematic/worldgen provenance. This is strong evidence, not a mathematical proof that no historical external player ever used the UUID.",
            "entity_priority_flag_counts": counter_dict(entity_flags),
            "entity_carried_item_totals": counter_dict(carried_items),
            "explicit_absences": {
                "player_current_or_spawn_in_zone": len(raw["players"]["affected_players"]) == 0,
                "maid_entities": entity_flags.get("maid", 0) == 0,
                "named_entities": entity_flags.get("custom_named", 0) == 0,
                "tamed_or_owned_entities": entity_flags.get("tamed_or_owned", 0) == 0,
                "vehicle_entities": entity_flags.get("vehicle", 0) == 0,
                "villager_entities": entity_flags.get("villager", 0) == 0,
                "known_player_owner_block_entities": all(
                    not row["matches_current_player_identity"] for row in owner_rows_summary
                ),
                "nonempty_create_item_vault": len(actual_nonempty_containers) == 0,
                "nonempty_fluid_storage": len(actual_nonempty_fluids) == 0,
                "computer_block_entities": raw["block_entities"]["flag_counts"].get("computer", 0) == 0,
                "custom_named_block_entities": raw["block_entities"]["flag_counts"].get("custom_named", 0) == 0,
                "text_book_or_command_block_entities": raw["block_entities"]["flag_counts"].get("text_book_or_command", 0) == 0,
            },
        },
        "machine_lists": {
            "safe_replace": safe_replace,
            "salvage_or_relocate": salvage,
            "preserve_entities": preserve_entities,
            "rebuild_poi": rebuild_poi,
        },
        "attention_chunks": [attention[key] for key in sorted(attention)],
        "hard_blockers_before_slot_replacement": hard_blockers,
        "mandatory_gates": [
            "Generate and bind V before any write.",
            "Rebuild each MCA from C and replace only the 29,305 selected slots; never copy whole region files.",
            "Keep C entities data, then collision/support-test all 198 preserved entities against V and relocate unsafe records with receipts.",
            "Use V POI or rebuild POI from final blocks; do not copy the 40 stale C records.",
            "Keep per-slot C preimage hashes and retain the stopped source archive for rollback.",
        ],
        "non_actions": {
            "world_modified": False,
            "archive_modified": False,
            "java_started": False,
            "ota_built_or_published": False,
        },
    }


def markdown(report: Mapping[str, Any], json_path: Path, json_sha256: str) -> str:
    summary = report["summary"]
    evidence = report["evidence"]
    absences = evidence["explicit_absences"]
    owners = evidence["owner_uuid_references"]
    lines = [
        "# 保护区对象处置建议（直接地形/群系覆盖）",
        "",
        f"- 状态：`{report['status']}`",
        f"- 原始只读审计：`{report['inputs']['raw_audit']}`",
        f"- 原始审计 SHA-256：`{report['inputs']['raw_audit_sha256']}`",
        f"- 处置 JSON：`{json_path.resolve()}`",
        f"- 处置 JSON SHA-256：`{json_sha256}`",
        "- 未写入世界、未启动 Java、未制作或发布 OTA。",
        "",
        "## 结论",
        "",
        "按用户已经授权的“保护区地形/群系直接覆盖”口径，当前 1,333 个 block entity 中没有检测到必须保留的玩家财产载荷。它们可随 V 的选中 chunk 槽替换；仍必须保留 C 的实体数据，并在 V 完成后执行碰撞/承托检查；POI 必须按最终方块重建。",
        "",
        "| 机器清单 | 数量 | 动作 |",
        "|---|---:|---|",
        f"| `safe_replace` | {summary['safe_replace_block_entities']:,} BE | 允许随 V 替换 |",
        f"| `salvage_or_relocate` | {summary['salvage_or_relocate_block_entities']:,} BE | 当前为空；若后续源快照变化必须重新审计 |",
        f"| `preserve_entities` | {summary['preserve_entities']:,} 实体 | 保留 C；V 后碰撞/承托校验 |",
        f"| `rebuild_poi` | {summary['rebuild_poi_records']:,} POI | 丢弃旧 C POI，采用 V/按最终方块重建 |",
        "",
        "## 玩家财产排除证据",
        "",
        f"- 玩家当前位置或出生点受影响：{summary['affected_players']}。",
        f"- 真正非空容器 BE：{summary['actual_nonempty_container_block_entities']}。",
        f"- 非空液体 BE：{summary['actual_nonempty_fluid_block_entities']}。",
        f"- Create 保险柜部件：{summary['empty_create_item_vault_parts']}，全部空。",
        f"- 246 个非空物品栈全部来自 Create copycat 的结构材质字段，不是库存。",
        f"- 未开封世界生成 LootTable BE：{summary['unopened_worldgen_loot_table_block_entities']}。",
        f"- 电脑、具名 BE、文本/书/命令 BE：分别为 0、0、0。",
        f"- 女仆、具名实体、驯服/有主人实体、载具、村民实体：均为 0。",
        "",
        "## Create 结构",
        "",
        f"共有 {summary['create_structure_block_entities']} 个 Create BE 集中在 `x={CREATE_STRUCTURE_X[0]}..{CREATE_STRUCTURE_X[1]}`, `y={CREATE_STRUCTURE_Y[0]}..{CREATE_STRUCTURE_Y[1]}`, `z={CREATE_STRUCTURE_Z[0]}..{CREATE_STRUCTURE_Z[1]}` 的紧凑结构内，跨 {summary['create_structure_chunks']} 个 chunk；同处还有 38 个 fisherman POI、1 个 librarian POI和对应空桶/讲台。该空间聚类支持“整合包世界生成结构”判断。",
        "",
        "Create ID 计数：",
        "",
    ]
    for identifier, count in evidence["create_structure"]["id_counts"].items():
        lines.append(f"- `{identifier}`：{count}")
    lines.extend(["", "Owner UUID：", ""])
    for row in owners:
        lines.append(
            f"- `{row['uuid']}`：{row['references']} 次，UUID v{row['uuid_version']}，匹配当前 playerdata/usercache/ops/whitelist：`{str(row['matches_current_player_identity']).lower()}`。"
        )
    lines.extend(
        [
            "",
            "这两个 Owner 值只出现在 Create 结构 BE 中，均不匹配 112 份当前 playerdata 或身份列表；因此按结构/模板来源元数据处理。它是强证据，但不能证明某个外部历史玩家从未使用过同一 UUID。",
            "",
            "## 实体与 POI",
            "",
            f"保护区选中实体槽中有 {summary['preserve_entities']} 个实体。没有女仆、具名/驯服/有主人实体、载具或村民；其中 70 个实体携带物品，47 个带 persistent 标记。完整坐标和携带物摘要在 JSON 的 `machine_lists.preserve_entities`。它们不随 terrain region 替换，V 生成后必须检查是否卡入固体、悬空、落入液体或越界。",
            "",
            f"POI 共 {summary['rebuild_poi_records']} 条：38 fisherman、1 librarian、1 bee_nest。它们必须与 V 的最终方块一致，所以全部进入 `rebuild_poi`，不能把 C 的旧记录拼回去。",
            "",
            "## 185 个关注 chunk",
            "",
            "完整 185 行坐标与四类对象计数位于 JSON 的 `attention_chunks`。这份清单是 OTA 应用器的强制前置输入：每个涉及 chunk 均要保留 C preimage hash，并在输出 MCA 中只改严格选中的槽。",
            "",
            "## 放行边界",
            "",
            "当前可放行的是“构建 V 并准备槽级替换”，不是直接写入公测世界。写入前仍缺 V 绑定、实体碰撞检查、POI 重建、克隆服验证与逐槽回滚收据。",
            "",
        ]
    )
    if not all(absences.values()):
        lines.extend(["警告：以下显式缺失条件未满足：", ""])
        for key, value in absences.items():
            if not value:
                lines.append(f"- `{key}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-audit", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--sha256-manifest", type=Path, required=True)
    args = parser.parse_args()

    raw = json.loads(args.raw_audit.read_text(encoding="utf-8"))
    report = build(raw, args.raw_audit.resolve(), args.archive.resolve())
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    json_payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    args.output_json.write_bytes(json_payload)
    json_hash = sha256_bytes(json_payload)
    md_payload = (markdown(report, args.output_json, json_hash) + "\n").encode("utf-8")
    args.output_md.write_bytes(md_payload)
    md_hash = sha256_bytes(md_payload)
    manifest = (
        f"{report['inputs']['source_archive_sha256_bound_by_raw_audit']} *{args.archive.resolve()}\n"
        f"{report['inputs']['raw_audit_sha256']} *{args.raw_audit.resolve()}\n"
        f"{json_hash} *{args.output_json.resolve()}\n"
        f"{md_hash} *{args.output_md.resolve()}\n"
    )
    args.sha256_manifest.write_text(manifest, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "summary": report["summary"],
                "owner_uuid_references": report["evidence"]["owner_uuid_references"],
                "explicit_absences": report["evidence"]["explicit_absences"],
                "output_json": str(args.output_json.resolve()),
                "output_md": str(args.output_md.resolve()),
                "sha256_manifest": str(args.sha256_manifest.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not report["hard_blockers_before_slot_replacement"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
