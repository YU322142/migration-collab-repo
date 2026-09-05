#!/usr/bin/env python3
"""Build the fail-closed terrain preservation decision and frontier datapack.

This tool is intentionally static.  It never starts Java and never writes to
the authoritative world.  The generated datapack can either be merged last
into the final KubeJS data tree or installed as a highest-priority world
datapack after an isolated registry-load test.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
PACK_FORMAT = 48  # Minecraft 1.21 / 1.21.1 data pack format.
FRONTIER_NAMESPACE = "mechanomania_frontier"
FRONTIER_DIMENSION = f"{FRONTIER_NAMESPACE}:frontier"
FRONTIER_NOISE_SETTINGS = f"{FRONTIER_NAMESPACE}:tectonic"
FRONTIER_DIMENSION_TYPE = f"{FRONTIER_NAMESPACE}:frontier"

DEFAULT_FRONTIER_AUDIT = Path("outputs/existing-terrain-frontier-audit-20260813.json")
DEFAULT_BLEND_AUDIT = Path("outputs/existing-terrain-frontier-blending-audit-20260813.json")
DEFAULT_VANILLA_PLAN = Path("outputs/vanilla-terrain-protection-plan-20260813.json")
DEFAULT_PACK_DATA = Path(
    r"<AUDIT_ROOT>\integration-pack-audit-20260813\overrides\kubejs\data"
)
DEFAULT_VANILLA_JAR = Path(
    r"<INSTANCE_ROOT>\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3\libraries\com\mojang\minecraft\1.21.1\minecraft-1.21.1-client.jar"
)
DEFAULT_PACK_OUTPUT = Path("outputs/terrain-preservation-frontier-datapack-20260813")
DEFAULT_JSON_OUTPUT = Path("outputs/terrain-preservation-final-20260813.json")
DEFAULT_MD_OUTPUT = Path("outputs/terrain-preservation-final-20260813.md")

RESOURCE_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
ZIP_REGISTRY_RE = re.compile(
    r"^data/([^/]+)/worldgen/(density_function|noise)/(.+)\.json$"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def rewrite_strings(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, dict):
        return {key: rewrite_strings(child, mapping) for key, child in value.items()}
    if isinstance(value, list):
        return [rewrite_strings(child, mapping) for child in value]
    return value


@dataclass(frozen=True)
class RegistryResource:
    registry: str
    key: str
    source_path: str
    payload: bytes

    @property
    def json_value(self) -> Any:
        return json.loads(self.payload.decode("utf-8"))


def filesystem_registry(data_root: Path) -> list[RegistryResource]:
    resources: list[RegistryResource] = []
    for namespace_dir in sorted(path for path in data_root.iterdir() if path.is_dir()):
        namespace = namespace_dir.name
        for registry in ("worldgen/density_function", "worldgen/noise"):
            registry_root = namespace_dir / registry
            if not registry_root.is_dir():
                continue
            for path in sorted(registry_root.rglob("*.json")):
                logical = path.relative_to(registry_root).with_suffix("").as_posix()
                resources.append(
                    RegistryResource(
                        registry=registry,
                        key=f"{namespace}:{logical}",
                        source_path=str(path),
                        payload=path.read_bytes(),
                    )
                )
    return resources


def zip_registry(archive: zipfile.ZipFile) -> list[RegistryResource]:
    resources: list[RegistryResource] = []
    for name in sorted(archive.namelist()):
        match = ZIP_REGISTRY_RE.fullmatch(name)
        if not match:
            continue
        namespace, kind, logical = match.groups()
        resources.append(
            RegistryResource(
                registry=f"worldgen/{kind}",
                key=f"{namespace}:{logical}",
                source_path=name,
                payload=archive.read(name),
            )
        )
    return resources


def dependency_closure(
    roots: Iterable[Any], resources: Iterable[RegistryResource]
) -> list[RegistryResource]:
    """Return every noise/density resource reachable by resource identifiers.

    A key may legally exist in both the noise and density-function registries.
    Both are retained; rewriting the identifier remains correct because the
    consuming JSON field supplies the registry type.
    """

    by_key: dict[str, list[RegistryResource]] = defaultdict(list)
    for resource in resources:
        by_key[resource.key].append(resource)

    queue: deque[Any] = deque(copy.deepcopy(list(roots)))
    selected: dict[tuple[str, str], RegistryResource] = {}
    while queue:
        value = queue.popleft()
        for text in iter_strings(value):
            if not RESOURCE_RE.fullmatch(text):
                continue
            for resource in by_key.get(text, []):
                identity = (resource.registry, resource.key)
                if identity in selected:
                    continue
                selected[identity] = resource
                queue.append(resource.json_value)
    return [selected[key] for key in sorted(selected)]


def frontier_resource_id(source_key: str) -> str:
    namespace, logical = source_key.split(":", 1)
    return f"{FRONTIER_NAMESPACE}:{namespace}/{logical}"


def tree_manifest(root: Path, exclude: set[str] | None = None) -> tuple[list[dict[str, Any]], str]:
    exclude = exclude or set()
    rows: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in exclude:
            continue
        row = {
            "path": relative,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        rows.append(row)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\n")
    return rows, digest.hexdigest().upper()


def unique_biomes(dimension: dict[str, Any]) -> tuple[int, int]:
    entries = dimension["generator"]["biome_source"].get("biomes", [])
    names = {
        row.get("biome")
        for row in entries
        if isinstance(row, dict) and isinstance(row.get("biome"), str)
    }
    return len(entries), len(names)


def build_datapack(
    destination: Path, pack_data: Path, vanilla_jar: Path
) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")

    target_dimension_path = pack_data / "minecraft/dimension/overworld.json"
    target_type_path = pack_data / "minecraft/dimension_type/overworld.json"
    target_noise_path = pack_data / "minecraft/worldgen/noise_settings/overworld.json"
    target_dimension = load_json(target_dimension_path)
    target_type = load_json(target_type_path)
    target_noise = load_json(target_noise_path)

    with zipfile.ZipFile(vanilla_jar) as archive:
        vanilla_type = json.loads(
            archive.read("data/minecraft/dimension_type/overworld.json").decode("utf-8")
        )
        vanilla_noise = json.loads(
            archive.read("data/minecraft/worldgen/noise_settings/overworld.json").decode("utf-8")
        )
        vanilla_resources = zip_registry(archive)

    target_resources = filesystem_registry(pack_data)
    target_closure = dependency_closure([target_noise], target_resources)
    vanilla_closure = dependency_closure([vanilla_noise], vanilla_resources)
    target_keys = {resource.key for resource in target_closure}
    mapping = {key: frontier_resource_id(key) for key in sorted(target_keys)}

    frontier_noise = rewrite_strings(target_noise, mapping)
    frontier_dimension = rewrite_strings(target_dimension, mapping)
    frontier_dimension["type"] = FRONTIER_DIMENSION_TYPE
    frontier_dimension["generator"]["settings"] = FRONTIER_NOISE_SETTINGS

    safe_overworld_dimension = {
        "type": "minecraft:overworld",
        "generator": {
            "type": "minecraft:noise",
            "biome_source": {
                "type": "minecraft:multi_noise",
                "preset": "minecraft:overworld",
            },
            "settings": "minecraft:overworld",
        },
    }

    with tempfile.TemporaryDirectory(prefix="terrain-frontier-build-") as raw_temp:
        temp_root = Path(raw_temp) / destination.name
        temp_root.mkdir(parents=True)

        write_json(
            temp_root / "pack.mcmeta",
            {
                "pack": {
                    "pack_format": PACK_FORMAT,
                    "description": "Mechanomania frontier terrain isolation; generated 2026-08-13",
                }
            },
        )
        write_json(
            temp_root / "data/minecraft/dimension/overworld.json",
            safe_overworld_dimension,
        )
        write_json(
            temp_root / "data/minecraft/dimension_type/overworld.json", vanilla_type
        )
        write_json(
            temp_root / "data/minecraft/worldgen/noise_settings/overworld.json",
            vanilla_noise,
        )

        for resource in vanilla_closure:
            namespace, logical = resource.key.split(":", 1)
            output = temp_root / "data" / namespace / resource.registry / f"{logical}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(resource.payload)

        write_json(
            temp_root / f"data/{FRONTIER_NAMESPACE}/dimension/frontier.json",
            frontier_dimension,
        )
        write_json(
            temp_root / f"data/{FRONTIER_NAMESPACE}/dimension_type/frontier.json",
            target_type,
        )
        write_json(
            temp_root
            / f"data/{FRONTIER_NAMESPACE}/worldgen/noise_settings/tectonic.json",
            frontier_noise,
        )

        for resource in target_closure:
            source_namespace, logical = resource.key.split(":", 1)
            output = (
                temp_root
                / "data"
                / FRONTIER_NAMESPACE
                / resource.registry
                / source_namespace
                / f"{logical}.json"
            )
            write_json(output, rewrite_strings(resource.json_value, mapping))

        readme = f"""# Mechanomania frontier terrain isolation datapack

This directory is generated, not runtime-validated.

- `minecraft:overworld` is pinned to the Minecraft 1.21.1 384-block
  dimension type, noise settings, and reachable vanilla noise/density closure.
- `{FRONTIER_DIMENSION}` uses the Mechanomania/Tectonic 544-block generator.
- Existing world chunks are not included and must never be copied into this
  directory.
- Preferred integration: merge `data/**` last into the final KubeJS data tree.
- Alternative integration: install as the highest-priority world datapack and
  prove priority plus resolved registry values in an isolated server.
- Bootstrap test access: `/execute in {FRONTIER_DIMENSION} run tp @s 0 160 0`.

Do not publish until the runtime gates in
`outputs/terrain-preservation-final-20260813.md` pass.
"""
        (temp_root / "README.md").write_text(readme, encoding="utf-8", newline="\n")

        rows, tree_sha = tree_manifest(temp_root)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": utc_now(),
            "status": "STATIC_BLUEPRINT_ONLY",
            "frontier_dimension": FRONTIER_DIMENSION,
            "vanilla_closure_resource_count": len(vanilla_closure),
            "tectonic_closure_resource_count": len(target_closure),
            "tectonic_closure_source_key_count": len(target_keys),
            "tree_sha256": tree_sha,
            "files": rows,
        }
        write_json(temp_root / "FRONTIER-MANIFEST.json", manifest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(temp_root, destination)

    biome_entries, biome_count = unique_biomes(target_dimension)
    return {
        "path": str(destination),
        "manifest": str(destination / "FRONTIER-MANIFEST.json"),
        "tree_sha256": tree_sha,
        "file_count_excluding_manifest": len(rows),
        "vanilla_closure_resource_count": len(vanilla_closure),
        "tectonic_closure_resource_count": len(target_closure),
        "tectonic_closure_source_key_count": len(target_keys),
        "frontier_biome_parameter_entries": biome_entries,
        "frontier_unique_biomes": biome_count,
    }


def validate_evidence(
    frontier: dict[str, Any], blend: dict[str, Any], plan: dict[str, Any]
) -> None:
    expected = {
        "terrain chunks": (frontier["terrain"]["occupied_chunk_count"], 927_157),
        "frontier edges": (frontier["frontier"]["edge_count"], 21_018),
        "boundary chunks": (
            frontier["frontier"]["existing_boundary_chunk_count"],
            18_120,
        ),
        "blend checked chunks": (blend["checked_chunk_count"], 18_120),
        "freeze chunks": (plan["geometry"]["freeze"]["chunk_count"], 28_950),
        "generated freeze chunks": (
            frontier["requested_protected_zone"]["already_generated_chunk_count"],
            0,
        ),
    }
    failures = [f"{name}: {actual} != {wanted}" for name, (actual, wanted) in expected.items() if actual != wanted]
    if frontier.get("status") != "PASS":
        failures.append("frontier audit is not PASS")
    if blend.get("status") != "BLOCKED":
        failures.append("blend audit must remain BLOCKED")
    if not blend.get("variants") or any(row.get("has_blending_data") for row in blend["variants"]):
        failures.append("expected every audited frontier variant to lack blending_data")
    if failures:
        raise ValueError("; ".join(failures))


def render_markdown(report: dict[str, Any]) -> str:
    evidence = report["evidence"]
    datapack = report["frontier_datapack"]
    gates = report["release_gates"]
    return f"""# 旧主世界地形零覆盖裁决与 Mechanomania Frontier 方案

生成日期：2026-08-13  
状态：`{report['status']}`  
生产发布：`{report['production_release_status']}`

## 裁决

不在旧 Overworld 的任何边界直接启用 Tectonic。旧主世界继续解析为
Minecraft 1.21.1 原版兼容的 `384` 高度噪声几何；Mechanomania 的
Tectonic `544` 高度世界生成完整放入独立维度
`{FRONTIER_DIMENSION}`。这不是删减玩法，而是隔离两个不兼容的地形
坐标系，避免让旧服务器地形成为试验品。

当前只能判定为“静态方案已就绪，等待隔离运行验证”，不能写成生产
PASS；本轮没有启动 Java，也没有修改世界、`level.dat`、
`server.properties`、端口、RCON 或 query 配置。

## 权威证据

| 项目 | 结果 |
|---|---:|
| 旧 Overworld terrain 区块 | {evidence['existing_terrain_chunks']:,} |
| 旧地形到未生成区块的完整基数边界 | {evidence['frontier_edges']:,} |
| 旧边界区块 | {evidence['existing_boundary_chunks']:,} |
| 相邻未生成区块 | {evidence['adjacent_ungenerated_chunks']:,} |
| 检查 blending marker 的边界区块 | {evidence['blending_checked_chunks']:,} |
| 缺少 `blending_data` | {evidence['blending_missing_chunks']:,} |
| 原版 Overworld 高度 | {evidence['vanilla_height']} |
| Mechanomania/Tectonic 高度 | {evidence['tectonic_height']} |
| 高度差 | {evidence['height_delta']} |
| x=10192,z=-1574 的 1536 格冻结计划 | {evidence['protected_freeze_chunks']:,} 区块 |
| 该冻结区现有地形 | {evidence['protected_existing_chunks']} 区块 |

`blending_data` 在 {evidence['blending_checked_chunks']:,} 个边界区块中
全部缺失。因此，把悬崖风险简单外推到 1000/1536 格之外不能解决问题；
旧世界实际存在 {evidence['frontier_edges']:,} 条不规则边界，任一处都可能
被玩家加载。

## 零覆盖实现

生成的静态数据包蓝图：`{datapack['path']}`

它执行三件事：

1. 恢复 `minecraft:overworld` 的原版 1.21.1 dimension type、noise
   settings，以及从原版 noise settings 可达的噪声/密度函数闭包；新主
   世界区块保持 384 高度几何，旧的 {evidence['existing_terrain_chunks']:,}
   个区块完全不写入。
2. 把 Mechanomania/Tectonic noise settings 及其可达依赖闭包重命名到
   `mechanomania_frontier:*`，消除与主世界使用同名
   `minecraft:overworld` 资源的冲突。
3. 新增 `{FRONTIER_DIMENSION}`，沿用整合包的 {datapack['frontier_biome_parameter_entries']:,}
   条 multi-noise biome 参数（{datapack['frontier_unique_biomes']} 个唯一
   biome）以及整合包全局加载的结构、biome feature、任务与 KubeJS 玩法。

闭包统计：原版主世界 {datapack['vanilla_closure_resource_count']} 个资源；
Tectonic frontier {datapack['tectonic_closure_resource_count']} 个资源，来自
{datapack['tectonic_closure_source_key_count']} 个唯一资源 ID。蓝图树哈希：
`{datapack['tree_sha256']}`。

首选集成方式是由最终打包器把蓝图中的 `data/**` **最后合并**到最终
KubeJS data tree；这样不依赖数据包优先级。若作为世界 datapack 安装，
必须在隔离服务器证明它排在 Mechanomania KubeJS 数据之上。

注意：主世界的“原版兼容”在这里严格指地形高度、噪声与密度几何。
Mechanomania 的全局 biome feature/structure 注入仍可装饰以后生成的主
世界区块；已有区块不变。如果要求新主世界连装饰也逐字节原版，则还要
隔离所有 biome/structure 注册表修改，这会与“完整保留整合包玩法”冲突，
本方案不作虚假承诺。

## 生产门禁（全部通过才开服）

1. 在 D 盘隔离副本加载最终服务端；确认 registry/datapack 无错误，
   `{FRONTIER_DIMENSION}` 存在。
2. 读取解析后的注册表：`minecraft:overworld` 的 dimension type 与 noise
   height 必须都是 384；frontier 两项必须都是 544。
3. 用同一 seed 分别生成少量主世界和 frontier 测试区块；主世界高度范围
   不得超过原版边界，frontier 必须实际使用 Tectonic 依赖。
4. 用命令临时进入：
   `/execute in {FRONTIER_DIMENSION} run tp @s 0 160 0`。验证返回点、死亡、
   重登、两名客户端、结构/任务/配方/方块实体。公开版再提供受保护的传送
   门或命令，而不是依赖管理员命令。
5. 启动前后重新运行旧世界不可变清单；`region/entities/poi` 任一已有文件
   哈希漂移即拒绝发布。保护区预生成只能向审计证明为空的槽位写入。
6. 生产 `server.properties`、25566/25575/25565、RCON、query 与原
   `level.dat` 均不得被打包脚本替换。

当前阻塞项：

{chr(10).join(f'- {item}' for item in [
    '尚未用隔离 NeoForge 服务端证明 datapack/KubeJS 优先级与 codec 注册解析。',
    '尚未在运行时生成测试区块，证明主世界解析为 384 高度而 frontier 解析为 544 高度。',
    '尚未实现并测试 frontier 的公开受保护入口、返回点和失败恢复。',
    '尚未通过双客户端、死亡、重登、结构、任务、配方、方块实体和回滚冒烟测试。',
    'x=10192,z=-1574 的原版冻结区尚未预生成；其独立空槽与导入门禁仍然有效。',
])}

## 可重复验证

```powershell
python -B outputs/tools/validate_terrain_preservation_final.py `
  --report outputs/terrain-preservation-final-20260813.json `
  --datapack outputs/terrain-preservation-frontier-datapack-20260813 `
  --output outputs/terrain-preservation-final-validation-20260813.json
```

静态门禁状态：`{gates['static']['status']}`；隔离运行门禁：
`{gates['isolated_runtime']['status']}`；生产门禁：
`{gates['production']['status']}`。
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    frontier = load_json(args.frontier_audit)
    blend = load_json(args.blend_audit)
    plan = load_json(args.vanilla_plan)
    validate_evidence(frontier, blend, plan)

    with zipfile.ZipFile(args.vanilla_jar) as archive:
        vanilla_type = json.loads(
            archive.read("data/minecraft/dimension_type/overworld.json").decode("utf-8")
        )
        vanilla_noise = json.loads(
            archive.read("data/minecraft/worldgen/noise_settings/overworld.json").decode("utf-8")
        )
    target_type_path = args.pack_data / "minecraft/dimension_type/overworld.json"
    target_noise_path = args.pack_data / "minecraft/worldgen/noise_settings/overworld.json"
    target_dimension_path = args.pack_data / "minecraft/dimension/overworld.json"
    target_type = load_json(target_type_path)
    target_noise = load_json(target_noise_path)

    vanilla_height = vanilla_noise["noise"]["height"]
    target_height = target_noise["noise"]["height"]
    if vanilla_height != 384 or vanilla_type["height"] != 384:
        raise ValueError("unexpected Minecraft 1.21.1 Overworld height")
    if target_height != 544 or target_type["height"] != 544:
        raise ValueError("unexpected Mechanomania/Tectonic height")

    datapack = build_datapack(args.datapack, args.pack_data, args.vanilla_jar)
    variants = blend["variants"]
    missing_blending = sum(row["count"] for row in variants if not row["has_blending_data"])
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "READY_FOR_ISOLATED_RUNTIME_VALIDATION",
        "production_release_status": "BLOCKED_FAIL_CLOSED",
        "operation": "terrain-preservation-final-decision",
        "decision": {
            "selected_strategy": "SPLIT_DIMENSION_ZERO_OVERWRITE",
            "overworld": "Keep Minecraft 1.21.1 vanilla-compatible 384-height terrain geometry.",
            "frontier": f"Keep Mechanomania/Tectonic 544-height world generation in {FRONTIER_DIMENSION}.",
            "same_dimension_tectonic_switch": "REJECTED",
            "reason": "The complete old-world frontier lacks blending_data and the generator heights differ by 160 blocks.",
        },
        "authoritative_world": frontier["world"],
        "evidence": {
            "existing_terrain_chunks": frontier["terrain"]["occupied_chunk_count"],
            "terrain_region_files": frontier["terrain"]["region_file_count"],
            "frontier_edges": frontier["frontier"]["edge_count"],
            "existing_boundary_chunks": frontier["frontier"]["existing_boundary_chunk_count"],
            "adjacent_ungenerated_chunks": frontier["frontier"]["adjacent_ungenerated_chunk_count"],
            "blending_checked_chunks": blend["checked_chunk_count"],
            "blending_missing_chunks": missing_blending,
            "blending_required_marker": blend["required_marker"],
            "vanilla_height": vanilla_height,
            "tectonic_height": target_height,
            "height_delta": target_height - vanilla_height,
            "protected_center": plan["geometry"]["center"],
            "protected_core_radius": plan["geometry"]["core"]["radius"],
            "protected_freeze_radius": plan["geometry"]["freeze"]["radius"],
            "protected_freeze_chunks": plan["geometry"]["freeze"]["chunk_count"],
            "protected_existing_chunks": frontier["requested_protected_zone"]["already_generated_chunk_count"],
        },
        "immutable_policy": {
            "existing_region_entities_poi": "No existing file or occupied chunk may be overwritten, regenerated, or deleted.",
            "level_dat": "Do not replace or rebuild the authoritative level.dat.",
            "production_configuration": "Do not modify server.properties, ports, RCON, or query settings.",
            "protected_zone": "Only import vanilla-compatible pre-generated chunks into slots proven empty immediately before import.",
        },
        "overworld_policy": {
            "dimension": "minecraft:overworld",
            "dimension_type_height": vanilla_type["height"],
            "noise_height": vanilla_noise["noise"]["height"],
            "geometry": "Minecraft 1.21.1 vanilla-compatible noise and density closure",
            "existing_chunks": "immutable",
            "new_chunks": "384-height vanilla-compatible geometry",
            "decoration_caveat": "Mechanomania global biome feature and structure injections remain enabled; new chunks are not promised byte-identical vanilla decoration.",
        },
        "frontier_policy": {
            "dimension": FRONTIER_DIMENSION,
            "dimension_type": FRONTIER_DIMENSION_TYPE,
            "noise_settings": FRONTIER_NOISE_SETTINGS,
            "dimension_type_height": target_type["height"],
            "noise_height": target_noise["noise"]["height"],
            "temporary_access_command": f"/execute in {FRONTIER_DIMENSION} run tp @s 0 160 0",
            "public_access_requirement": "Add a guarded portal or command with return-point and failure recovery before public release.",
        },
        "frontier_datapack": datapack,
        "source_locks": {
            "frontier_audit": {"path": str(args.frontier_audit), "sha256": sha256_file(args.frontier_audit)},
            "blending_audit": {"path": str(args.blend_audit), "sha256": sha256_file(args.blend_audit)},
            "vanilla_plan": {"path": str(args.vanilla_plan), "sha256": sha256_file(args.vanilla_plan)},
            "vanilla_client_jar": {"path": str(args.vanilla_jar), "sha256": sha256_file(args.vanilla_jar)},
            "mechanomania_dimension": {"path": str(target_dimension_path), "sha256": sha256_file(target_dimension_path)},
            "mechanomania_dimension_type": {"path": str(target_type_path), "sha256": sha256_file(target_type_path)},
            "mechanomania_noise_settings": {"path": str(target_noise_path), "sha256": sha256_file(target_noise_path)},
        },
        "release_gates": {
            "static": {"status": "PASS", "checks": [
                "authoritative terrain/frontier counts locked",
                "all frontier blending markers audited and absent",
                "vanilla and Tectonic heights independently verified",
                "namespace-isolated frontier datapack built",
            ]},
            "isolated_runtime": {"status": "PENDING", "java_started_this_operation": False},
            "production": {"status": "BLOCKED", "rule": "Runtime registry, generation, client, immutable-world and configuration gates must all pass."},
        },
        "blockers": [
            "No isolated NeoForge registry load has yet proven datapack/KubeJS priority and codec resolution.",
            "No test chunks have yet proven Overworld resolves to 384 and frontier resolves to 544 at runtime.",
            "No guarded public entry/return mechanism for the frontier dimension has yet been implemented and tested.",
            "No two-client, death, relog, structure, task, recipe, block-entity and rollback smoke test has yet passed.",
            "The requested x=10192,z=-1574 vanilla freeze remains ungenerated; its separate empty-slot/import gates still apply.",
        ],
        "non_actions": {
            "java_started": False,
            "world_modified": False,
            "level_dat_modified": False,
            "production_configuration_modified": False,
        },
    }
    write_json(args.json_output, report)
    args.md_output.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--frontier-audit", type=Path, default=DEFAULT_FRONTIER_AUDIT)
    result.add_argument("--blend-audit", type=Path, default=DEFAULT_BLEND_AUDIT)
    result.add_argument("--vanilla-plan", type=Path, default=DEFAULT_VANILLA_PLAN)
    result.add_argument("--pack-data", type=Path, default=DEFAULT_PACK_DATA)
    result.add_argument("--vanilla-jar", type=Path, default=DEFAULT_VANILLA_JAR)
    result.add_argument("--datapack", type=Path, default=DEFAULT_PACK_OUTPUT)
    result.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    result.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return result


def main() -> int:
    args = parser().parse_args()
    report = build(args)
    print(json.dumps({
        "status": report["status"],
        "production": report["production_release_status"],
        "report": str(args.json_output),
        "markdown": str(args.md_output),
        "datapack": str(args.datapack),
        "tree_sha256": report["frontier_datapack"]["tree_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
