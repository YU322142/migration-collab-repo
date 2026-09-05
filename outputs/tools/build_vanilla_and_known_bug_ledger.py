#!/usr/bin/env python3
"""Build the 1.21.11 vanilla/gameplay and known-bug evidence ledger.

This builder is deliberately evidence-only.  It reads existing reports, hashes
them, and writes a compact ledger.  It never opens Anvil regions, starts Java,
or mutates source, staging, or release directories.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
OUTPUT_JSON = WORKSPACE / "outputs/vanilla-and-known-bug-ledger-20260813.json"
OUTPUT_MD = WORKSPACE / "outputs/vanilla-and-known-bug-ledger-20260813.md"

CLASS_FIXED = "fixed"
CLASS_DATA_SAFE = "data_safe_gameplay_runtime_pending"
CLASS_UNFINISHED = "unfinished"
CLASSIFICATIONS = {CLASS_FIXED, CLASS_DATA_SAFE, CLASS_UNFINISHED}


EVIDENCE_LOCKS: dict[str, tuple[str, int]] = {
    r"<AUDIT_ROOT>\feature-id-audit.json": (
        "F7101938CF6C14972D4217E93E55D898C3C65820290961EB5F49F89AE26866DA",
        12460,
    ),
    "outputs/incoming-20260811-world-dryrun-candidate13-20260812.json": (
        "CD34C9AE8B8EB4E0EF74836CFF594615EE0F20D8E043533643F85C7CC3ABD244",
        105873429,
    ),
    r"<AUDIT_ROOT>\incoming-20260811-villagers-source-baseline-20260812.json": (
        "07DA5802FD834049D76B5EF860CA3192303BD00692AF08D70E50B146C1DB51F8",
        2033500,
    ),
    "outputs/nautilus-body-lifecycle-smoke-20260809.md": (
        "FBC85CBC142FAA79F0A15B769253F775C73D19DE96D24749D7BF7323C2990670",
        3741,
    ),
    "outputs/happyghast-stat-audit-20260811.json": (
        "3D19A428DBB972BBCD925B70C748650DF093F1DA9549C46CE048A375FE543E39",
        545030,
    ),
    "outputs/waypoint-fire-engineering-closure-20260809.md": (
        "7F8D9145470D790137A24CAF4E16DBD7DDF0F138466D5EBC97259A5DD62ED21C",
        12438,
    ),
    "outputs/waypoint-op-join-gate-20260811.json": (
        "B6227801A6B2E456087B7078905B91B65B812828B071075368157018CB77BA93",
        3323,
    ),
    "outputs/candidate14-netherite-horse-armor-ledger-baseline-20260812.json": (
        "671C3EABE08F5536DCECF2127AFE0D8A65BB47EF76CEA874266B682BA615695F",
        3020,
    ),
    "outputs/candidate14-deferred-item-ledger-current-20260812.json": (
        "EC3BC83BEAF885ADBC23C4763F4D4B25D3AC99CBE319F9F313F615E790CB219C",
        2518,
    ),
    "outputs/candidate13-scarecrow-compat-build-audit-20260812.json": (
        "95EBDA34D33D1E21E6A3ECA8169E656335E2774D438DD5708E98DEAF818E307B",
        6580,
    ),
    "outputs/create-carriage-orientation-guard-p02-audit-20260813.md": (
        "564B0AF0E84C100B8876B872260F7D1AAB8C98E810350E274340011435A62B91",
        3827,
    ),
    "outputs/candidate11-chute-guard-stress-20260811.json": (
        "C06B099824E6CA6A176DD60CF96D9D5093CADF66A0323AE9E685CB5AE356B38B",
        29008,
    ),
    "outputs/candidate14-server-recipe-book-stale-allowlist-20260812.json": (
        "D4EB4F372F79E4B1C546C6979EBAC181DFA3EFFA03B718228818E6E759E4FF70",
        4785,
    ),
    "outputs/candidate14-server-recipe-book-stale-compat-20260812.md": (
        "8B1C5ACD968BF68F430F71753BD829DB73CD20A1A81154068C09FEF676836ADA",
        2078,
    ),
    "outputs/known-minor-errors-candidate11-candidate8n-20260812.md": (
        "E92C53F8261D66DB5071187F5E0E8064699D7152299CC03434251C4E803EDEC3",
        8051,
    ),
    "outputs/candidate13-resource-closure-20260812/build-report.json": (
        "D1147E82D3B9438C609299B557BF5FB64ADB5BD7330296D9D8C1F169B4C3876E",
        3686,
    ),
    "outputs/immersive-paintings-render-closure-20260810.md": (
        "EDDA098852CE99F05DBF88B2DFD8628813CE4D936E80465DB8228E785DDE6D6D",
        3211,
    ),
    "outputs/candidate14-ota-repairability-contract-20260812.json": (
        "99CF24314AA87EEA54C544EB54B7D49192BFD4A7CCAF4C3AED7C2958367A2750",
        29322,
    ),
    "outputs/candidate14-ota-repairability-validation-20260812.json": (
        "4F86BFC2C8E99CBC4D5C7663BA3F0C04BD410A431440E143792CB21E47240B13",
        651,
    ),
    "outputs/incoming-20260811-create-fluid-source-audit-v3.json": (
        "554601BFD4E1FFE64CC504C6912C42016AD2CA49FED5D95CCE6B98A513D39A71",
        541159,
    ),
    "outputs/migration-current-status-and-todo-20260813.md": (
        "514016C7DC13A6155ABF4B818F02F0C3BCC9F0A7EBFBE7027075EF080ED3FA2F",
        5375,
    ),
    "outputs/player-item-components-audit-20260809.md": (
        "5A477D85D3FF21F25FC1B6B2F6DC28750683E95A753E2641C077DB98F099E2EC",
        14701,
    ),
    "outputs/tools/convert_world_nbt.py": (
        "9ED51DF76AFE74D811F973169C2A26A4AEFEC2ECE22ABE33F2FAC00ADA078307",
        234274,
    ),
    "outputs/tools/convert_create_saveddata.py": (
        "E0A5D46760DA52AC5F33A9B4DEAA13D639C5DA91E71C6261D82CBE555621174A",
        91100,
    ),
}


NEW_VANILLA_IDS: list[tuple[str, int]] = [
    ("minecraft:leaf_litter", 123162),
    ("minecraft:wildflowers", 51610),
    ("minecraft:firefly_bush", 7087),
    ("minecraft:tall_dry_grass", 6510),
    ("minecraft:short_dry_grass", 6505),
    ("minecraft:pale_garden", 1728),
    ("minecraft:pale_oak_leaves", 1720),
    ("minecraft:pale_oak_log", 1570),
    ("minecraft:dried_ghast", 507),
    ("minecraft:cactus_flower", 455),
    ("minecraft:creaking_heart", 131),
    ("minecraft:pale_oak_planks", 116),
    ("minecraft:nautilus_shell", 57),
    ("minecraft:golden_spear", 51),
    ("minecraft:copper_leggings", 40),
    ("minecraft:copper_helmet", 39),
    ("minecraft:copper_chestplate", 36),
    ("minecraft:pale_oak_fence", 31),
    ("minecraft:copper_boots", 28),
    ("minecraft:nautilus", 23),
    ("minecraft:pale_oak_trapdoor", 21),
    ("minecraft:zombie_nautilus", 18),
    ("minecraft:pale_oak_wall_sign", 14),
    ("minecraft:pale_oak_slab", 12),
    ("minecraft:iron_spear", 12),
    ("minecraft:pale_oak_fence_gate", 12),
    ("minecraft:pale_oak_sapling", 11),
    ("minecraft:pale_oak_button", 8),
    ("minecraft:pale_oak_door", 6),
    ("minecraft:pale_oak_sign", 6),
    ("minecraft:copper_nautilus_armor", 5),
    ("minecraft:stripped_pale_oak_log", 5),
    ("minecraft:happy_ghast", 4),
    ("minecraft:shelf", 4),
    ("minecraft:pale_oak_shelf", 4),
    ("minecraft:stone_spear", 4),
    ("minecraft:pale_oak_boat", 4),
    ("minecraft:pink_harness", 3),
    ("minecraft:copper_axe", 3),
    ("minecraft:pale_oak_stairs", 2),
    ("minecraft:diamond_spear", 2),
    ("minecraft:iron_nautilus_armor", 2),
    ("minecraft:resin_clump", 2),
    ("minecraft:blue_harness", 1),
    ("minecraft:netherite_horse_armor", 1),
    ("minecraft:pale_oak_pressure_plate", 1),
    ("minecraft:pale_oak_hanging_sign", 1),
    ("minecraft:copper_shovel", 1),
    ("minecraft:diamond_nautilus_armor", 1),
    ("minecraft:netherite_spear", 1),
]

NAUTILUS_IDS = {
    "minecraft:nautilus_shell",
    "minecraft:nautilus",
    "minecraft:zombie_nautilus",
    "minecraft:copper_nautilus_armor",
    "minecraft:iron_nautilus_armor",
    "minecraft:diamond_nautilus_armor",
}
HAPPY_GHAST_IDS = {
    "minecraft:dried_ghast",
    "minecraft:happy_ghast",
    "minecraft:pink_harness",
    "minecraft:blue_harness",
}


def evidence_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else WORKSPACE / candidate


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")


def verify_evidence_locks() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for logical_path, (expected_sha, expected_bytes) in EVIDENCE_LOCKS.items():
        path = evidence_path(logical_path)
        if not path.is_file():
            failures.append(f"missing evidence: {logical_path}")
            continue
        actual_bytes = path.stat().st_size
        actual_sha = sha256(path)
        if actual_bytes != expected_bytes:
            failures.append(f"size drift: {logical_path}: {actual_bytes} != {expected_bytes}")
        if actual_sha != expected_sha:
            failures.append(f"hash drift: {logical_path}: {actual_sha} != {expected_sha}")
        rows.append({"path": logical_path, "bytes": actual_bytes, "sha256": actual_sha})
    if failures:
        raise RuntimeError("evidence lock failure:\n" + "\n".join(failures))
    return rows


def new_identifier_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for identifier, chunk_presence in NEW_VANILLA_IDS:
        if identifier == "minecraft:netherite_horse_armor":
            classification = CLASS_DATA_SAFE
            coverage = "protected_carrier_only"
            cluster = "netherite_horse_armor"
            note = "载体与操作防呆已存在；完整模型、配方和装备玩法尚未实现。"
        elif identifier in NAUTILUS_IDS:
            classification = CLASS_DATA_SAFE
            coverage = "functional_backport_present"
            cluster = "nautilus"
            note = "注册/存档与 BODY 生命周期有证据；完整交互、生成、音画和多人矩阵待实测。"
        elif identifier in HAPPY_GHAST_IDS:
            classification = CLASS_DATA_SAFE
            coverage = "functional_backport_present"
            cluster = "happy_ghast"
            note = "兼容实现与统计 ID 已进入候选；真实骑乘、相机、声音、渲染和多人矩阵待实测。"
        else:
            classification = CLASS_FIXED
            coverage = "functional_backport_present"
            cluster = "content_backport"
            note = "存在功能性 backport；仍必须在最终合包中重做注册表、资源与保存重启门禁。"
        rows.append(
            {
                "id": identifier,
                "source_chunk_presence": chunk_presence,
                "coverage": coverage,
                "classification": classification,
                "cluster": cluster,
                "note": note,
            }
        )
    return rows


def issue(
    issue_id: str,
    title: str,
    classification: str,
    evidence: list[str],
    accomplished: list[str],
    remaining: list[str],
    ota_class: str,
    delivery: str,
    world_mutation: bool,
    release_gate: list[str],
    artifact_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "title": title,
        "classification": classification,
        "evidence": evidence,
        "accomplished": accomplished,
        "remaining": remaining,
        "artifact_sha256": artifact_sha256,
        "ota": {
            "class": ota_class,
            "delivery": delivery,
            "world_mutation_allowed": world_mutation,
            "requires_new_release_lock": True,
            "requires_rollback_path": True,
        },
        "release_gate": release_gate,
    }


def build_issues() -> list[dict[str, Any]]:
    return [
        issue(
            "vanilla.new_registry_ids",
            "50 个 1.21.1 后新增原版 ID",
            CLASS_DATA_SAFE,
            [r"<AUDIT_ROOT>\feature-id-audit.json", "outputs/migration-current-status-and-todo-20260813.md"],
            ["识别到 50/50 个实际出现 ID", "49/50 有功能性 backport", "1/50 由安全载体保活"],
            ["最终合包注册表 dump", "双轮保存重启", "四个玩法簇的人工矩阵"],
            "both_side_mod_update",
            "成对更新 backport/兼容 JAR；客户端由 MCModSync 退出后更新，服务端短停同步替换",
            False,
            ["50 个 ID 全部可解析", "没有 Invalid item/entity/block", "安全载体与完整实现不得共存"],
        ),
        issue(
            "vanilla.nautilus",
            "Nautilus / Zombie Nautilus",
            CLASS_DATA_SAFE,
            ["outputs/nautilus-body-lifecycle-smoke-20260809.md", "outputs/incoming-20260811-world-dryrun-candidate13-20260812.json"],
            ["canonical ID 与资源存在", "BODY 装备即时替换/清空/保存重启与属性生命周期通过", "最新 dry-run 的实体/装备未知项为 0"],
            ["41 个源实体逐个对账", "GUI/交互/骑乘冲刺/繁殖/自然生成/僵尸骑手/掉落/发射器/剪切", "声音/渲染/多人同步"],
            "both_side_mod_update",
            "发布新的 Nautilus 成对 JAR；若需要改旧 NBT，另附幂等 server datafix 与 sidecar",
            True,
            ["41/41 fixture 通过", "两名真实客户端通过", "保存重启后 BODY/乘客/Owner/Brain 不漂移"],
            "01EBD831AC5D12D60965168EE10887FB9DE81CE660341F420D0C51E9A1E33415",
        ),
        issue(
            "vanilla.happy_ghast",
            "Happy Ghast",
            CLASS_DATA_SAFE,
            ["outputs/happyghast-stat-audit-20260811.json", "outputs/migration-current-status-and-todo-20260813.md"],
            ["兼容 JAR 已进入基线", "happy_ghast_one_cm 统计 ID 已识别", "存档 ID 不因缺注册表被静默丢弃"],
            ["真实多人骑乘", "相机/家锚/声音/模型/动画", "运行时注册表 dump 与保存重启"],
            "both_side_mod_update",
            "成对替换 Happy Ghast 兼容 JAR，客户端通过 MCModSync，服务端短停同步",
            False,
            ["注册表 dump 含实体与统计 ID", "两客户端骑乘/重连/维度切换", "无 passenger/owner/stat 丢失"],
            "36C1CE14EE18B81C04654F1A6956F2257B7DEAC07746E960475AAF5C6F25A579",
        ),
        issue(
            "vanilla.locator_bar",
            "Locator Bar / Waypoint 显示语义",
            CLASS_DATA_SAFE,
            ["outputs/waypoint-fire-engineering-closure-20260809.md", "outputs/waypoint-op-join-gate-20260811.json"],
            ["服务端规则、属性跟踪、颜色/位置语义和保存重启已有 smoke", "高权限命令树修复并真实入服 PASS"],
            ["官方数据驱动 waypoint_style_asset 与 sprites", "双真实客户端、GUI scale、shader/resource pack", "Geyser/Bedrock 路径与像素对比"],
            "both_side_mod_update",
            "成对更新 Waypoint 兼容 JAR；纯 sprite 修复可走客户端资源 overlay",
            False,
            ["双客户端 add/update/remove/reconnect/dimension matrix", "不同缩放与 spectator/invisibility/team matrix", "无非官方协议漂移"],
            "86A85C0447315AC17D373E3708425CEB8450D9D0CB1FD9C7ABDC82CE8D8E5B92",
        ),
        issue(
            "vanilla.netherite_horse_armor",
            "Netherite Horse Armor",
            CLASS_DATA_SAFE,
            ["outputs/candidate14-netherite-horse-armor-ledger-baseline-20260812.json", "outputs/candidate14-deferred-item-ledger-current-20260812.json"],
            ["源与 staging 的同一匹马/同一物品已锁定", "保护载体阻止危险操作与静默吞物", "稳定 owner UUID、栈哈希和路径别名已记录"],
            ["完整物品模型/配方/属性/装备交互", "两轮运行后栈与 owner 精确对账", "用完整实现替换载体"],
            "both_side_mod_update",
            "先成对发布完整实现，再短停服务端；同一次 release 原子移除保护载体，禁止二者共存",
            False,
            ["round1/round2 owner UUID 与 stack hash 不变", "完整装备/卸下/死亡掉落/漏斗等防呆矩阵", "carrier_and_full_implementation_never_coexist"],
            "1C7C4B2A76978C563C18EE05ABA9292099E6B15BA920CF2699904068F0B1104B",
        ),
        issue(
            "converter.player_attributes",
            "玩家专属属性 namespace 与全量属性迁移",
            CLASS_FIXED,
            ["outputs/known-minor-errors-candidate11-candidate8n-20260812.md", "outputs/incoming-20260811-world-dryrun-candidate13-20260812.json", "outputs/tools/convert_world_nbt.py"],
            ["7 个 player.* namespace 修正", "211,551 条属性别名转换", "unsupported_attributes=0"],
            ["最终合包 fresh conversion 后注册表/保存重启复验"],
            "server_only_data_migration",
            "停服副本上执行当前幂等转换器；客户端无单独修复动作",
            True,
            ["unsupported_attributes=0", "七个错误 generic.* 计数为 0", "二次转换无变化"],
        ),
        issue(
            "converter.trial_spawner",
            "Trial Spawner Not-a-map 崩溃链",
            CLASS_FIXED,
            ["outputs/incoming-20260811-world-dryrun-candidate13-20260812.json", "outputs/candidate11-chute-guard-stress-20260811.json"],
            ["8,705 个配置已结构转换", "最新 dry-run malformed/unsupported region 为 0", "旧 stress 报告中的 Not a map 根因已纳入转换"],
            ["最终新合包 round1/round2 加载实际试炼区块"],
            "server_only_data_migration",
            "停服副本执行幂等 NBT 转换；需要客户端内容变更时再成对发版",
            True,
            ["日志无 TrialSpawner Not a map", "强制加载代表性区块", "保存重启后配置结构不漂移"],
        ),
        issue(
            "server.recipe_book",
            "玩家 Recipe Book 陈旧 ID",
            CLASS_DATA_SAFE,
            ["outputs/candidate14-server-recipe-book-stale-allowlist-20260812.json", "outputs/candidate14-server-recipe-book-stale-compat-20260812.md"],
            ["精确锁定 62 行/41 ID", "确认是 ServerRecipeBook 原生 removed-now 自清理，不是物品/实体拒载"],
            ["fresh runtime 第一轮精确命中", "优雅保存停服", "第二轮必须为 0"],
            "server_only_data_migration",
            "无需客户端 OTA；服务器短停运行原生 load/save，自清理必须受 exact allowlist 约束",
            True,
            ["round1 multiset SHA 精确", "round2 zero", "任何新 ID/格式/普通 Server thread ERROR 阻断"],
        ),
        issue(
            "server.map_banner",
            "地图旗帜字段 Not a list: null",
            CLASS_UNFINISHED,
            ["outputs/known-minor-errors-candidate11-candidate8n-20260812.md", "outputs/candidate14-ota-repairability-contract-20260812.json"],
            ["已定位为 4 条持久化地图旗帜字段", "修复边界限定为字段级，禁止删除整个地图记录"],
            ["实现 fail-closed 字段规范化", "保留 map ID、装饰和未知 payload", "幂等夹具、回滚与运行时验证"],
            "server_only_data_migration",
            "服务端短停执行字段级 datafix，写 ledger/sidecar；MCModSync 不能单独修复",
            True,
            ["4/4 规范化", "地图 ID/装饰/payload hash 不变", "二次运行 no-op", "实机查看地图"],
        ),
        issue(
            "create.fluids",
            "Create 流体单位与 potion 小误差",
            CLASS_FIXED,
            ["outputs/incoming-20260811-create-fluid-source-audit-v3.json", "outputs/incoming-20260811-world-dryrun-candidate13-20260812.json"],
            ["744 个流体栈已审计", "Create milk 规范为 minecraft:milk", "两条 810 源单位按用户接受策略各转 8 mB，单条误差 +0.5 mB", "unsupported_create_fluids=0"],
            ["最终 fresh conversion 二次幂等", "代表性管道/容器/药水流体运行验证"],
            "server_only_data_migration",
            "停服副本执行当前 Create saved-data/NBT 转换器；如 codec 改变则成对发兼容 JAR",
            True,
            ["unsupported_create_fluids=0", "仅允许已审计的两条 nearest conversion", "二次转换 no-op"],
        ),
        issue(
            "kaleidoscope.scarecrow",
            "Cookery Scarecrow 旧库存 codec 崩溃",
            CLASS_FIXED,
            ["outputs/candidate13-scarecrow-compat-build-audit-20260812.json"],
            ["旧 HandItems/ArmorItems list 转 ItemStackHandler", "slot-3 dragon head 与 UUID/坐标证据锁定", "幂等、错误类型 fail-closed", "隔离构建与单元测试通过"],
            ["最终合包加入精确 JAR", "真实区块加载、保存重启与交互验收"],
            "both_side_mod_update",
            "成对发布 Scarecrow compat JAR；不离线重写整个实体",
            False,
            ["实体不再拒载", "slot 0..3 物品逐项不变", "保存重启后 handler 结构稳定"],
            "E06FCFEA1FF76FB22EAD50964C18F22657971E42B6E82F0A2FE844C2F048B463",
        ),
        issue(
            "waypoint.command_tree",
            "Waypoint 高权限命令树缺参数导致无法入服",
            CLASS_FIXED,
            ["outputs/waypoint-op-join-gate-20260811.json", "outputs/waypoint-fire-engineering-closure-20260809.md"],
            ["命令参数注册完成", "permission level 4 真实入服及颜色命令 PASS", "服务端规则保存重启 smoke"],
            ["在 Mechanomania 最终合包重复高权限入服"],
            "both_side_mod_update",
            "成对发布锁定 Waypoint JAR",
            False,
            ["OP4 join", "命令执行成功", "无命令树同步异常"],
            "86A85C0447315AC17D373E3708425CEB8450D9D0CB1FD9C7ABDC82CE8D8E5B92",
        ),
        issue(
            "create.chute_unload",
            "Create Chute 客户端区块卸载竞态",
            CLASS_FIXED,
            ["outputs/candidate11-chute-guard-stress-20260811.json", "outputs/migration-current-status-and-todo-20260813.md"],
            ["BOTH-side unload guard 已构建并进入后续基线", "旧 stress round1 已进服；该报告 NO_GO 原因是独立 TrialSpawner 错误，不是 chute guard 失效"],
            ["最终合包双轮飞行/传送/卸载回归"],
            "both_side_mod_update",
            "成对发布 Create chute guard",
            False,
            ["无 chute unload NPE/crash", "快速区块卸载/重载", "两轮客户端日志无 Render/System fatal"],
            "AC51AEFDDA8437D777B5C8B3E285E9036676D854F7958C6B882807C15BE0910A",
        ),
        issue(
            "create.carriage_orientation",
            "Create carriage 小写方向导致 DOWN/崩溃",
            CLASS_FIXED,
            ["outputs/create-carriage-orientation-guard-p02-audit-20260813.md", "outputs/tools/convert_create_saveddata.py"],
            ["根因锁定为 case-sensitive enum fallback", "转换器规范化 InitialOrientation", "p0.2 BOTH-side 只读保护，双构建哈希一致", "4 个 carriage 与 16 个 controls 静态对账"],
            ["从权威源 fresh conversion", "最终 create_tracks.dat 方向全为合法水平大写", "崩溃列车坐标实机加载/驾驶/保存重启"],
            "both_side_mod_update",
            "服务端先用当前转换器生成新副本，并成对发布 p0.2 guard",
            True,
            ["4/4 InitialOrientation 大写且水平", "(-98.5,63,-97.7625) 附近列车通过", "round2 无 DOWN/getCounterClockWise 崩溃"],
            "805D6841BD30B514A059B21BEE4B6C70E183CB379CA286032975DCB961D6D74E",
        ),
        issue(
            "immersive_paintings.orientation",
            "Immersive Paintings Rotation/VRotation 冲突",
            CLASS_FIXED,
            ["outputs/immersive-paintings-render-closure-20260810.md"],
            ["标量旋转迁移到 VRotation", "127/127 bounded attached entities retained", "两轮 reload/save/stop 通过"],
            ["最终大合包在真实原画附近重复观察与保存重启"],
            "both_side_mod_update",
            "成对发布 patched Immersive Paintings JAR",
            False,
            ["画框方向/旋转不漂移", "实体不消失", "客户端截图与日志通过"],
            "AF4D838434302FF65F676D3A4BE8682666E0CCF95392FCFFFBE33E00D79D8D86",
        ),
        issue(
            "immersive_paintings.cache",
            "Immersive Paintings 图片缓存迁移",
            CLASS_DATA_SAFE,
            ["outputs/migration-current-status-and-todo-20260813.md", "outputs/immersive-paintings-render-closure-20260810.md"],
            ["缓存已纳入迁移白名单", "权威集合记录为 87 原图 + 87 缩略图", "组装脚本已有复制/完整性门禁"],
            ["最终 release 实际携带 87+87", "服务器提供图片且客户端真实显示", "炸服/重启后缓存与实体引用保持"],
            "server_only_data_migration",
            "服务端短停复制权威缓存并做清单校验；客户端渲染 JAR 可成对 OTA",
            True,
            ["87 original + 87 thumbnails", "零缺图/HTTP/cache error", "重启前后文件清单与画面一致"],
        ),
        issue(
            "client.resource_assets",
            "Yuushya / creaking / dragon-tea / blowgun 资源缺失",
            CLASS_FIXED,
            ["outputs/candidate13-resource-closure-20260812/build-report.json", "outputs/known-minor-errors-candidate11-candidate8n-20260812.md", "outputs/immersive-paintings-render-closure-20260810.md"],
            ["432 条 form=2 警告有 bounded alias", "5 个坏模型与 23 类贴图引用已定点处理", "creaking_heart 非法 active 状态从派生包移除", "dragon-tea 144 状态与 3 个 blowgun 模型闭环"],
            ["最终 Mechanomania 合包重新做资源加载", "真实客户端截图", "不把整合包标题/托管 UI 带回"],
            "client_only_ota",
            "客户端退出后由 MCModSync 更新资源 overlay JAR；不覆盖用户原资源包 ZIP",
            False,
            ["零 missing model/texture in audited set", "零 Render-thread ERROR/FATAL", "截图检查沉浸画框与代表方块"],
            "BCCB7D7CF8019D8895A081D563E578712D7CDF93DA0AD9EAFB31067439C62862",
        ),
        issue(
            "server.advancement_unlocks",
            "陈旧 Advancement 解锁 ID",
            CLASS_UNFINISHED,
            ["outputs/known-minor-errors-candidate11-candidate8n-20260812.md", "outputs/candidate14-ota-repairability-contract-20260812.json"],
            ["已识别为玩家解锁等价问题，不与物品/区块丢失混淆", "禁止删除整个 advancement/player 文件"],
            ["建立 exact source-to-target ID map", "无等价项形成有界 waiver", "两轮保存重启与 UI 对账"],
            "server_only_data_migration",
            "服务端短停运行幂等 advancement datafix；MCModSync 不能单独修复",
            True,
            ["每个旧 ID 都映射或显式 waiver", "玩家进度文件其余字段不变", "第二轮 no-op"],
        ),
        issue(
            "create.schematic_dependencies",
            "Create schematic 外部文件依赖",
            CLASS_UNFINISHED,
            ["outputs/incoming-20260811-world-dryrun-candidate13-20260812.json", "outputs/player-item-components-audit-20260809.md"],
            ["5 个源中存在的 schematic 已被 dry-run 定位为目标依赖缺失", "另有 3 个源端本就缺失的引用被区分为 inherited state"],
            ["最终组装必须复制源中存在的 5 个外部 NBT", "保留 3 个 inherited missing 引用，不伪造内容", "Schematicannon/物品实机打开"],
            "server_only_data_migration",
            "服务器短停复制外部 schematic 目录并锁定哈希；不通过客户端 OTA 猜测文件",
            True,
            ["5 个 available dependencies 全部存在", "3 个 inherited missing 仍有 ledger", "无新 missing schematic blocker"],
        ),
        issue(
            "cctweaked.lifecycle_guard",
            "CC:Tweaked 冷启动/停服超时",
            CLASS_FIXED,
            ["outputs/migration-current-status-and-todo-20260813.md"],
            ["受限 startup/shutdown guard 已进入基线", "未放宽普通 Lua 运行超时"],
            ["最终合包两轮启动/保存/停服与电脑外设检查"],
            "both_side_mod_update",
            "成对发布受限 guard",
            False,
            ["冷启动和优雅停服无超时", "普通 Lua timeout 策略未被放宽", "电脑数据跨重启保留"],
            "6744626E2B43643E9F28C9159FABD7A6A53CDCDEB83AE8252C266F7E987F84F7",
        ),
    ]


def build_gates() -> list[dict[str, Any]]:
    return [
        {
            "id": "gate.fresh_authority_conversion",
            "status": "pending",
            "blocking": True,
            "requirements": [
                "从权威 stopped source 用当前 convert_world_nbt.py 与 convert_create_saveddata.py 重建唯一副本",
                "转换 marker 绑定当前脚本哈希，不接受旧 marker",
                "不从运行过的测试世界反向取数",
            ],
        },
        {
            "id": "gate.static_ledger_and_bundle",
            "status": "pending",
            "blocking": True,
            "requirements": [
                "新 release lock/manifests 包含所有 required guard/backport/resource artifacts",
                "server/client side policy 与哈希完全匹配",
                "保护载体与完整 Netherite Horse Armor 实现不得共存",
            ],
        },
        {
            "id": "gate.two_round_runtime",
            "status": "pending",
            "blocking": True,
            "requirements": [
                "round1 启动、OP4 真入服、关键坐标/实体/方块实体加载、save-all flush、优雅停服",
                "round2 重启重复入服与加载",
                "unknown registry、Invalid item、TrialSpawner Not a map、scarecrow codec、Create carriage/chute crash 为 0",
                "recipe-book round1 精确 62/41，round2 为 0",
            ],
        },
        {
            "id": "gate.real_client_gameplay_matrix",
            "status": "pending",
            "blocking": True,
            "requirements": [
                "Nautilus、Happy Ghast、Locator Bar、Netherite Horse Armor 分项人工测试",
                "两名真实客户端、重连、维度切换、不同 GUI scale",
                "渲染/声音/交互/多人同步均留日志与截图证据",
            ],
        },
        {
            "id": "gate.paintings_and_resources",
            "status": "pending",
            "blocking": True,
            "requirements": [
                "Immersive Paintings cache 87 原图 + 87 缩略图",
                "真实图片显示、方向与重启保持",
                "审计范围内缺模型/贴图和 Render-thread ERROR/FATAL 为 0",
            ],
        },
        {
            "id": "gate_unfinished_data_repairs",
            "status": "pending",
            "blocking": True,
            "requirements": [
                "4 条 map banner 字段级修复完成且幂等",
                "advancement 旧 ID 映射/waiver 完整",
                "5 个现存 Create schematic 外部文件复制，3 个继承缺失仅记录不伪造",
            ],
        },
        {
            "id": "gate.ota_repairability",
            "status": "pending",
            "blocking": True,
            "requirements": [
                "每个已知问题具有稳定 ID、OTA class、回滚路径和新 release lock",
                "客户端 JAR/overlay 可由 MCModSync 在退出后更新",
                "服务端 JAR 和世界/player NBT 不冒充 MCModSync 热更新",
                "任何未分类 P0/P1 错误均 NO_GO",
            ],
        },
    ]


def make_ledger(evidence_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    identifiers = new_identifier_rows()
    issues = build_issues()
    id_class_counts = Counter(row["classification"] for row in identifiers)
    issue_class_counts = Counter(row["classification"] for row in issues)
    coverage_counts = Counter(row["coverage"] for row in identifiers)
    return {
        "schema": 1,
        "ledger_id": "vanilla-and-known-bug-ledger-20260813",
        "generated_date": "2026-08-13",
        "status": "NO_GO_FINAL_RUNTIME_GATES_PENDING",
        "scope": {
            "source_version": "Minecraft 1.21.11 Fabric",
            "target_version": "Minecraft 1.21.1 NeoForge 21.1.241",
            "mode": "existing-evidence-only",
            "world_rescan_performed": False,
            "java_started": False,
            "source_modified": False,
            "staging_modified": False,
            "release_modified": False,
        },
        "classification_definitions": {
            CLASS_FIXED: "修复实现与定向证据已闭环；合入最终大包后仍必须做回归，不能把历史 PASS 当作新包 PASS。",
            CLASS_DATA_SAFE: "注册/载体/转换/保护层已防止静默丢数据，但完整玩法或真实多人/音画实测尚未闭环。",
            CLASS_UNFINISHED: "尚缺可发布的有界实现、映射或幂等修复；发布门禁保持阻断。",
        },
        "summary": {
            "new_vanilla_identifiers": {
                "seen": len(identifiers),
                "functional_backport_present": coverage_counts["functional_backport_present"],
                "protected_carrier_only": coverage_counts["protected_carrier_only"],
                "classification_counts": dict(id_class_counts),
            },
            "latest_dryrun": {
                "players": 112,
                "entities": 73117,
                "region_files": 5727,
                "player_item_stacks_scanned": 2444,
                "entity_item_stacks_scanned": 33231,
                "block_entity_item_stacks_scanned": 2282,
                "trial_spawner_conversions": 8705,
                "attribute_aliases": 211551,
                "item_component_aliases": 2278,
                "unsupported_player_items": 0,
                "unsupported_entity_items": 0,
                "unsupported_entities": 0,
                "unsupported_equipment": 0,
                "unsupported_attributes": 0,
                "unsupported_game_rules": 0,
                "unsupported_create_fluids": 0,
                "malformed_players": 0,
                "malformed_regions": 0,
                "qualification": "5 个 source-present Create schematic 在该 dry-run 目标中缺外部依赖，另有 3 个 source-inherited missing；已单列 unfinished，不能写成全局零 blocker。",
            },
            "villagers": {"source_villagers": 1216, "trades": 927, "duplicate_uuids": 0, "final_deep_compare_pending_newest": 23},
            "known_issue_rows": len(issues),
            "known_issue_classification_counts": dict(issue_class_counts),
            "blocking_release_gates": len(build_gates()),
        },
        "evidence_locks": evidence_rows
        if evidence_rows is not None
        else [{"path": p, "sha256": sha, "bytes": size} for p, (sha, size) in EVIDENCE_LOCKS.items()],
        "new_vanilla_identifiers": identifiers,
        "items": issues,
        "release_gates": build_gates(),
        "ota_policy": {
            "client_only_ota": "客户端退出后更新 client-only JAR/resource overlay；不覆盖用户资源包 ZIP 与 servers.dat。",
            "both_side_mod_update": "客户端由 MCModSync 更新，服务端必须短停并同步替换；发布新的 paired release lock。",
            "server_only_data_migration": "服务器短停，在世界副本执行幂等 datafix，写 ledger/sidecar 并保留回滚；MCModSync 不能改世界/player NBT。",
            "unknown_error_rule": "任何不在总账或批准 allowlist 中的 P0/P1 错误都阻断发布。",
        },
        "invariants": {
            "production_ports_unchanged": {"server": 25566, "rcon": 25575, "query": 25565},
            "production_server_properties_unchanged": True,
            "source_and_existing_terrain_never_overwritten": True,
            "unknown_payloads_preserved_or_sidecarred": True,
            "no_silent_item_entity_map_or_chunk_deletion": True,
            "one_authoritative_conversion_and_one_release_lock": True,
            "no_test_world_as_conversion_baseline": True,
        },
    }


def validate_model(ledger: dict[str, Any]) -> None:
    identifiers = ledger["new_vanilla_identifiers"]
    if len(identifiers) != 50 or len({row["id"] for row in identifiers}) != 50:
        raise ValueError("new_vanilla_identifiers must contain exactly 50 unique IDs")
    if any(row["classification"] not in CLASSIFICATIONS for row in identifiers):
        raise ValueError("invalid identifier classification")
    functional = sum(row["coverage"] == "functional_backport_present" for row in identifiers)
    carriers = [row["id"] for row in identifiers if row["coverage"] == "protected_carrier_only"]
    if functional != 49 or carriers != ["minecraft:netherite_horse_armor"]:
        raise ValueError("coverage must remain 49 functional + netherite horse armor carrier")
    issues = ledger["items"]
    if len(issues) != len({row["id"] for row in issues}):
        raise ValueError("duplicate issue IDs")
    required = {
        "vanilla.nautilus",
        "vanilla.happy_ghast",
        "vanilla.locator_bar",
        "vanilla.netherite_horse_armor",
        "converter.player_attributes",
        "converter.trial_spawner",
        "server.recipe_book",
        "server.map_banner",
        "create.fluids",
        "kaleidoscope.scarecrow",
        "waypoint.command_tree",
        "create.chute_unload",
        "create.carriage_orientation",
        "immersive_paintings.orientation",
        "immersive_paintings.cache",
        "client.resource_assets",
    }
    missing = required - {row["id"] for row in issues}
    if missing:
        raise ValueError(f"missing required issue rows: {sorted(missing)}")
    for row in issues:
        if row["classification"] not in CLASSIFICATIONS:
            raise ValueError(f"invalid issue classification: {row['id']}")
        if not row["evidence"] or not row["release_gate"] or not row["ota"]["delivery"]:
            raise ValueError(f"incomplete issue row: {row['id']}")
    if not any(row["classification"] == CLASS_UNFINISHED for row in issues):
        raise ValueError("ledger must expose unfinished work")
    if any(not row["blocking"] for row in ledger["release_gates"]):
        raise ValueError("all current release gates must remain blocking")


def render_markdown(ledger: dict[str, Any]) -> str:
    summary = ledger["summary"]
    lines = [
        "# 1.21.11 原版玩法迁移与已知 Bug 总账",
        "",
        "更新时间：2026-08-13",
        "",
        "## 结论",
        "",
        "当前不是‘全部玩法 100% 完成’，也不是‘还有未知数量的反复淘汰’。现有证据已把问题收敛成三类：修复实现已闭环、数据安全已闭环但玩法实测未闭环、以及仍缺有界实现的未完成项。最终状态仍为 **NO-GO：等待唯一新合包的运行门禁**。",
        "",
        "本次只汇总并锁定已有报告：没有重新扫描世界、没有启动 Java，也没有修改 source、staging 或 release。",
        "",
        "## 数字摘要",
        "",
        f"- 1.21.1 之后的新原版 ID：{summary['new_vanilla_identifiers']['seen']} 个；49 个有功能性 backport，1 个（`minecraft:netherite_horse_armor`）当前仅安全载体。",
        f"- 最新 dry-run：112 玩家、73,117 实体、5,727 region 文件；8,705 个 Trial Spawner、211,551 条属性别名、2,278 条物品组件别名。",
        "- dry-run 的 unsupported player/entity item、entity、equipment、attribute、gamerule、Create fluid、malformed player/region 均为 0。",
        "- 不能把上一句写成‘全局零 blocker’：5 个源中存在的 Create schematic 外部文件尚未进入该 dry-run 目标，另有 3 个源端本来就缺失的引用必须原样记录。",
        "- 村民基线：1,216 个村民、927 条交易、重复 UUID 0；最新多出的 23 个村民仍需最终 deep compare。",
        "",
        "## 三类状态",
        "",
        "| 分类 | 含义 | 数量（总账项目） |",
        "|---|---|---:|",
    ]
    counts = summary["known_issue_classification_counts"]
    for key, label in ((CLASS_FIXED, "已修"), (CLASS_DATA_SAFE, "数据安全已闭环，玩法/运行实测待闭环"), (CLASS_UNFINISHED, "未完成")):
        lines.append(f"| `{key}`（{label}） | {ledger['classification_definitions'][key]} | {counts.get(key, 0)} |")
    lines.extend(["", "## 原版玩法主项", "", "| 主项 | 分类 | 已做到 | 还缺什么 |", "|---|---|---|---|"])
    main_ids = {
        "vanilla.new_registry_ids",
        "vanilla.nautilus",
        "vanilla.happy_ghast",
        "vanilla.locator_bar",
        "vanilla.netherite_horse_armor",
    }
    for row in ledger["items"]:
        if row["id"] in main_ids:
            lines.append(
                f"| `{row['id']}` {row['title']} | `{row['classification']}` | {'；'.join(row['accomplished'])} | {'；'.join(row['remaining'])} |"
            )
    lines.extend(["", "## 已知 Bug / 数据缺口", "", "| ID | 分类 | 当前结论 | OTA/后续修复路径 |", "|---|---|---|---|"])
    for row in ledger["items"]:
        if row["id"] not in main_ids:
            lines.append(
                f"| `{row['id']}` | `{row['classification']}` | {'；'.join(row['accomplished'])} | {row['ota']['delivery']} |"
            )
    lines.extend(["", "## 发布前硬门禁", ""])
    for index, gate in enumerate(ledger["release_gates"], 1):
        lines.append(f"{index}. **`{gate['id']}`**：{'；'.join(gate['requirements'])}。")
    lines.extend(
        [
            "",
            "## OTA 边界",
            "",
            "- 客户端模型、贴图、渲染兼容 JAR：游戏退出后可由 MCModSync 更新。",
            "- BOTH-side 模组：客户端可由 MCModSync 更新，但服务端必须短停并同步换 JAR；必须发布新的 paired release lock。",
            "- 世界、玩家、recipe-book、advancement、map banner、外部 schematic：必须在服务器副本执行幂等 datafix/复制并留 sidecar 与回滚；MCModSync 不能假装热修这些数据。",
            "- 未分类 P0/P1 错误一律 NO-GO；不能靠扩大 allowlist 或删除玩家数据消音。",
            "",
            "## 不变量",
            "",
            "- 生产端口保持 `25566 / 25575 / 25565`，`server.properties` 不改。",
            "- 原服务器已有地形、区块、实体、地图、物品和未知 payload 不覆盖、不重滚、不静默删除。",
            "- 只从 stopped authority 做一次 fresh conversion；测试世界永不作为转换基线。",
            "",
            "机器可读详情、50 个 ID 逐项状态、证据哈希、每项 OTA class 和验收条件见同名 JSON。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-evidence-hash-check", action="store_true")
    parser.add_argument("--json", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--markdown", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    evidence_rows = None if args.skip_evidence_hash_check else verify_evidence_locks()
    ledger = make_ledger(evidence_rows)
    validate_model(ledger)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_bytes(stable_json(ledger))
    args.markdown.write_text(render_markdown(ledger), encoding="utf-8", newline="\n")
    print(f"PASS {args.json}")
    print(f"PASS {args.markdown}")
    print(f"items={len(ledger['items'])} identifiers={len(ledger['new_vanilla_identifiers'])} gates={len(ledger['release_gates'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
