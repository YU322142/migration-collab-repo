#!/usr/bin/env python3
"""Build a concise SavedData downgrade audit report from read-only world data."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import nbtlib


TARGET_DATA_VERSION = 3955
EXCLUDED = {"create_tracks.dat", "create_logistics.dat", "mineastr_sign_translations.dat"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load(path: Path) -> Any:
    return nbtlib.load(path, gzipped=True)


def integer(value: Any) -> int:
    return int(value)


def chunk_long(x: int, z: int) -> int:
    value = (x & 0xFFFFFFFF) | ((z & 0xFFFFFFFF) << 32)
    return value - (1 << 64) if value >= (1 << 63) else value


def write_markdown(report: dict[str, Any], output: Path) -> None:
    maps = report["metrics"]["maps"]
    chunks = report["metrics"]["chunks"]
    lines = [
        "# 1.21.11 -> NeoForge 1.21.1 SavedData 增量切换审计",
        "",
        f"- 源：`{report['source']}`（只读）",
        f"- 范围：`world/data` 中 {report['file_count']} 个 `.dat`；排除已单独闭环的 3 个 Create/MineAstr 文件后审计 {report['audited_file_count']} 个。",
        f"- 实证：与已完成保存/重启的 NeoForge 1.21.1 样本对照，源文件没有缺失；仅 {len(report['runtime_comparison']['hash_changed'])} 个被运行时重写。",
        "",
        "## 结论",
        "",
        "不能把整个 `world/data` 原样覆盖后直接开服。当前快照存在 3 个确定的数据损失点：`chunks.dat` 会丢 7 个强加载区块，`WorldUUID.dat` 会丢 JourneyMap 世界 UUID，`world_border.dat` 的 warning_time=6000 会回到 1.21.1 默认值 15。另有 `raids.dat`、`scoreboard.dat` 需要规范化或条件门禁。其余文件可直接保留。",
        "",
        "| 分类 | 文件 | 当前数据 | 结论/动作 |",
        "|---|---|---:|---|",
        f"| 必须转换 | `chunks.dat` | {chunks['forced_count']} 个 forced + {chunks['portal_count']} 个 portal ticket | forced 转为 1.21.1 `Forced` LongArray；portal ticket 无原生持久格式，切服前等待其自然到期并再次保存，否则阻断 |",
        f"| 必须转换 | `WorldUUID.dat` | `{report['metrics']['journeymap_world_uuid']}` | `data.world_uuid` 包装为 `data.WorldUUID.world_uuid`；否则 JourneyMap 6.0.3 会保存空值 |",
        f"| 条件转换 | `raids.dat` | 活动袭击 {report['metrics']['raids']['active_count']}；next_id={report['metrics']['raids']['next_id']} | 当前可映射计数器并写空 `Raids`；切服时若 `data.raids` 非空必须阻断，未实现完整活动袭击反向 codec 前不可开服 |",
        f"| 规范化 | `scoreboard.dat` | {report['metrics']['scoreboard']['objectives']} objective / {report['metrics']['scoreboard']['scores']} scores | 补 `CriteriaName=dummy`、`RenderType=integer`、JSON DisplayName、`Teams=[]`，值与名称保持不变 |",
        f"| 必须跨文件转换 | `world_border.dat` | warning_time={report['metrics']['world_border']['warning_time']}，其余边界几何/伤害值为默认 | 1.21.1 不消费该 SavedData；将 9 个字段映射回 `level.dat/Data/Border*`，尤其保持 `BorderWarningTime=6000` |",
        f"| 可直保留 | `map_0.dat`...`map_45.dat` + `idcounts.dat` | {maps['count']} 张连续地图，map 计数={maps['idcount']} | 1.21.11/1.21.1 字段兼容；样本重启 46/46 哈希不变 |",
        f"| 可直保留 | `random_sequences.dat` | {report['metrics']['random_sequences']['count']} 个序列 | 所有键和状态可加载；运行时仅正常推进 1 个已使用序列并补两个默认布尔字段 |",
        f"| 可直保留 | `immersive_paintings.dat` | {report['metrics']['immersive_paintings']} 条画作元数据 | 0.7.9 -> 0.7.8 NeoForge 样本保存/重启哈希不变 |",
        f"| 可直保留 | `JMPlayerSettings.dat` | {report['metrics']['journeymap_players']} 个玩家设置 | JourneyMap 样本保存/重启哈希不变 |",
        f"| 可直保留 | `toms_storage_rc.dat` | {report['metrics']['toms_connections']} 个远程连接 | Tom's Storage 目标样本保存/重启哈希不变 |",
        "| 可直保留 | 8 个 `*_index.dat` | 全部为空 | 结构索引 schema 相同；保留即可 |",
        "| 可直保留/休眠 | `chunk_loader.dat`, `stopwatches.dat`, `mtr.dat` | 前两者为空；MTR 仅 world id、禁用播报列表为空 | 当前模组集合不消费或无活动内容；保留原文件，不删除，便于未来恢复模组 |",
        "| 不存在 | `command_storage_*.dat` | 0 个 | 当前无命令存储数据；切服增量阶段必须重新 glob，若出现则 `contents` schema 可直保留 |",
        "",
        "## 地图与关键数据",
        "",
        f"- 地图 ID：{maps['min_id']}..{maps['max_id']}，连续={str(maps['contiguous']).lower()}；颜色数组异常={maps['invalid_color_arrays']}；banner 总数={maps['banner_count']}；frame 总数={maps['frame_count']}。",
        f"- 地图维度分布：{json.dumps(maps['dimensions'], ensure_ascii=False, sort_keys=True)}。",
        f"- 强加载区块：{json.dumps(chunks['forced'], ensure_ascii=False)}。",
        f"- 短暂 portal ticket：{json.dumps(chunks['portal'], ensure_ascii=False)}。这是运行时瞬态，1.21.1 `chunks.dat` 无法表示。",
        "- Scoreboard 6 条 Potted Farms 耐久统计均在目标样本中保留；列表顺序变化不影响键值语义。",
        "- `random_sequences.dat` 的 1030 个键完整保留；目标样本只有 `minecraft:blocks/short_grass` 因正常运行被推进一次。",
        "",
        "## 快速停服增量门禁",
        "",
        "1. 停止新登录与自动保存触发源，执行 `save-all flush`；等待至少 20 秒让 portal ticket 到期，再次 `save-all flush`，然后正常停服。",
        "2. 重新复制整个 `world/data` 的新增/修改文件，不只复制预设文件名；源清单与 staging 清单按 SHA-256 对账。",
        "3. 离线原子转换 `chunks.dat`、`WorldUUID.dat`、`raids.dat`、`scoreboard.dat`，并把 `world_border.dat` 映射进 `level.dat`；旧正式 1.21.1 格式必须识别并保持幂等。",
        "4. 硬门禁：active raids 必须为 0；portal tickets 必须为 0；forced 个数与坐标转换前后相等；JourneyMap UUID 字节串相同；46 张地图及 idcounts 语义不变。",
        "5. 第一次 NeoForge 保存后再次做语义比较。允许的变化仅为 DataVersion、字段规范化、随机序列实际被使用后的状态推进及 NeoForge 自建文件；其他变化一律 NO-GO。",
        "",
        "## 证据",
        "",
        f"- 原始结构报告：`{report['evidence']['raw_report']}`",
        f"- 运行时差异报告：`{report['evidence']['runtime_comparison']}`",
        f"- 1.21.11 官方映射：`{report['evidence']['source_mappings']}`",
        f"- 1.21.1 NeoForge 源码：`{report['evidence']['target_sources']}`",
        "",
        "结论状态：**NO-GO（直到上述 SavedData 转换与增量门禁接入切服编排）**。",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("raw_report", type=Path)
    parser.add_argument("comparison", type=Path)
    parser.add_argument("json_output", type=Path)
    parser.add_argument("markdown_output", type=Path)
    args = parser.parse_args()

    files = sorted(args.source.glob("*.dat"), key=lambda path: path.name.lower())
    maps = sorted((p for p in files if p.stem.startswith("map_") and p.stem[4:].isdigit()), key=lambda p: int(p.stem[4:]))
    map_ids = [int(p.stem[4:]) for p in maps]
    dimensions: Counter[str] = Counter()
    banner_count = frame_count = invalid_colors = 0
    for path in maps:
        data = load(path)["data"]
        dimensions[str(data.get("dimension", "<missing>"))] += 1
        banner_count += len(data.get("banners", []))
        frame_count += len(data.get("frames", []))
        if len(data.get("colors", [])) != 16384:
            invalid_colors += 1

    chunks = load(args.source / "chunks.dat")["data"]
    tickets = chunks.get("tickets", [])
    forced = []
    portal = []
    for ticket in tickets:
        x, z = map(integer, ticket["chunk_pos"])
        item = {"x": x, "z": z, "level": integer(ticket["level"])}
        if str(ticket["type"]) == "minecraft:forced":
            item["target_long"] = chunk_long(x, z)
            forced.append(item)
        elif str(ticket["type"]) == "minecraft:portal":
            item["ticks_left"] = integer(ticket.get("ticks_left", 0))
            portal.append(item)

    raids = load(args.source / "raids.dat")["data"]
    scoreboard = load(args.source / "scoreboard.dat")["data"]
    random_sequences = load(args.source / "random_sequences.dat")["data"]["sequences"]
    comparisons = json.loads(args.comparison.read_text(encoding="utf-8"))
    report = {
        "source": str(args.source.resolve()),
        "runtime_sample": str(args.runtime.resolve()),
        "target_data_version": TARGET_DATA_VERSION,
        "file_count": len(files),
        "audited_file_count": len([p for p in files if p.name not in EXCLUDED]),
        "excluded": sorted(EXCLUDED),
        "source_manifest_sha256": {p.name: sha256(p) for p in files},
        "runtime_comparison": {
            "hash_changed": comparisons["hash_changed"],
            "semantic_changed": comparisons["semantic_changed"],
        },
        "metrics": {
            "maps": {
                "count": len(maps),
                "min_id": min(map_ids),
                "max_id": max(map_ids),
                "contiguous": map_ids == list(range(min(map_ids), max(map_ids) + 1)),
                "idcount": integer(load(args.source / "idcounts.dat")["data"]["map"]),
                "dimensions": dict(sorted(dimensions.items())),
                "banner_count": banner_count,
                "frame_count": frame_count,
                "invalid_color_arrays": invalid_colors,
            },
            "chunks": {
                "ticket_count": len(tickets),
                "forced_count": len(forced),
                "portal_count": len(portal),
                "forced": forced,
                "portal": portal,
            },
            "raids": {
                "active_count": len(raids.get("raids", [])),
                "next_id": integer(raids.get("next_id", 1)),
                "tick": integer(raids.get("tick", 0)),
            },
            "scoreboard": {
                "objectives": len(scoreboard.get("Objectives", [])),
                "scores": len(scoreboard.get("PlayerScores", [])),
                "teams": len(scoreboard.get("Teams", [])),
            },
            "random_sequences": {
                "count": len(random_sequences),
                "namespaces": dict(sorted(Counter(str(key).split(":", 1)[0] for key in random_sequences).items())),
            },
            "immersive_paintings": len(load(args.source / "immersive_paintings.dat")["data"]["paintings"]),
            "journeymap_players": len(load(args.source / "JMPlayerSettings.dat")["data"]["players"]),
            "journeymap_world_uuid": str(load(args.source / "WorldUUID.dat")["data"]["world_uuid"]),
            "toms_connections": len(load(args.source / "toms_storage_rc.dat")["data"]["connections"]),
            "world_border": {
                key: integer(value) if isinstance(value, (int, float)) or type(value).__name__ in {"Byte", "Short", "Int", "Long", "Float", "Double"} else str(value)
                for key, value in load(args.source / "world_border.dat")["data"].items()
            },
            "command_storage_files": [p.name for p in files if p.name.startswith("command_storage_")],
        },
        "classification": {
            "must_convert": ["chunks.dat", "WorldUUID.dat", "world_border.dat -> level.dat"],
            "conditional_or_normalize": ["raids.dat", "scoreboard.dat"],
            "direct_preserve": [
                "map_0.dat..map_45.dat", "idcounts.dat", "random_sequences.dat", "immersive_paintings.dat",
                "JMPlayerSettings.dat", "toms_storage_rc.dat", "*_index.dat",
            ],
            "preserve_dormant": ["chunk_loader.dat", "stopwatches.dat", "mtr.dat"],
        },
        "evidence": {
            "raw_report": str(args.raw_report.resolve()),
            "runtime_comparison": str(args.comparison.resolve()),
            "source_mappings": r"D:\Trans\migration-audit-work\server-1.21.11-mappings.txt",
            "target_sources": r"D:\Trans\migration-audit-work\create-saveddata-probe\build\moddev\artifacts\neoforge-21.1.241-sources.jar",
        },
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, args.markdown_output)
    print(json.dumps({"json": str(args.json_output.resolve()), "markdown": str(args.markdown_output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
