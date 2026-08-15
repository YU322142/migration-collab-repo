"""Generate a deterministic candidate JAR inventory for the 1.21.1 NeoForge port.

The inventory intentionally reads only explicitly listed JARs.  It never walks a
world, log, player database, or the read-only production tree.  Smoke paths are
used only for byte/hash comparison with the canonical candidate.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from typing import Any


TOOLS_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from inspect_candidate_jars import inspect  # noqa: E402


AUDIT_ROOT = pathlib.Path(r"D:\Trans\migration-audit-work").resolve()
PRODUCTION_ROOT = pathlib.Path(r"D:\Trans\20260807").resolve()
OUTPUT_DIR = pathlib.Path(__file__).resolve().parents[1]
JSON_OUTPUT = OUTPUT_DIR / "final-mod-bundle-inventory-20260809.json"
MD_OUTPUT = OUTPUT_DIR / "final-mod-bundle-inventory-20260809.md"


def path(raw: str) -> pathlib.Path:
    return pathlib.Path(raw).resolve()


def under(candidate: pathlib.Path, root: pathlib.Path) -> bool:
    """Case-insensitive containment for Windows paths."""

    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return str(candidate).lower().startswith(str(root).lower().rstrip("\\") + "\\")


def checked_path(raw: str) -> pathlib.Path:
    result = path(raw)
    if under(result, PRODUCTION_ROOT):
        raise ValueError(f"production path is forbidden: {result}")
    if not under(result, AUDIT_ROOT):
        raise ValueError(f"path is outside audit root: {result}")
    return result


def hash_file(file_path: pathlib.Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest().upper()


def metadata(file_path: pathlib.Path) -> dict[str, Any]:
    """Return stable, user-facing metadata without embedding archive contents."""

    if not file_path.is_file():
        return {
            "path": str(file_path),
            "exists": False,
            "zip_valid": False,
            "bytes": None,
            "sha256": None,
            "loader": None,
            "mods": [],
            "mandatory_dependencies": [],
        }
    record = inspect(file_path)
    return {
        "path": str(file_path),
        "exists": True,
        "zip_valid": bool(record.get("zip_valid")),
        "bytes": record.get("bytes"),
        "sha256": record.get("sha256"),
        "loader": record.get("loader"),
        "manifest_files": record.get("manifest_files", []),
        "mods": record.get("mods", []),
        "mandatory_dependencies": record.get("mandatory_dependencies", []),
        "error": record.get("error"),
    }


def smoke_compare(canonical: dict[str, Any], smoke_raw: str) -> dict[str, Any]:
    smoke_path = checked_path(smoke_raw)
    result: dict[str, Any] = {"path": str(smoke_path)}
    if not smoke_path.is_file():
        result.update({"state": "absent", "exists": False, "bytes": None, "sha256": None})
        return result
    size, digest = hash_file(smoke_path)
    result.update({
        "state": "exact" if digest == canonical.get("sha256") else "stale",
        "exists": True,
        "bytes": size,
        "sha256": digest,
    })
    return result


def item(
    component: str,
    role: str,
    sides: str,
    canonical_raw: str,
    status: str,
    notes: str,
    smoke: list[str] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    canonical_path = checked_path(canonical_raw)
    canonical = metadata(canonical_path)
    if canonical.get("exists") and not canonical.get("zip_valid"):
        status = "invalid-candidate"
    smoke_records = [smoke_compare(canonical, raw) for raw in (smoke or [])]
    return {
        "component": component,
        "role": role,
        "install_sides": sides,
        "canonical": canonical,
        "smoke_comparisons": smoke_records,
        "status": status,
        "notes": notes,
        "evidence": evidence or [],
    }


def stale_item(component: str, raw: str, reason: str) -> dict[str, Any]:
    file_path = checked_path(raw)
    record = metadata(file_path)
    return {"component": component, "path": str(file_path), "metadata": record, "reason": reason}


def build_inventory() -> dict[str, Any]:
    # Candidate paths are deliberately explicit so a future world/log file can
    # never be pulled into the report by a broad recursive scan.
    candidates = [
        item(
            "Barched", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\mod-candidates\barched-neoforge-0.0.12-migration.1-asm.jar",
            "conditional-candidate",
            "已在服务端冒烟中使用；必须与 Architectury 13.0.11 和 Cloth Config 15.0.140 配套。真实客户端 GUI/渲染门禁仍未关闭。",
            [r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\barched-neoforge-0.0.12-migration.1-asm.jar"],
            ["outputs/barched-migration-audit-20260808.md"],
        ),
        item(
            "Chest Colorizer", "candidate", "client-only",
            r"D:\Trans\migration-audit-work\mod-candidates\chest-colorizer-1.6.1-equivalence.2+mc1.21.1-neoforge.jar",
            "conditional-candidate",
            "客户端候选；每个客户端的 colorizer.csv 需单独迁移，真实 GUI/渲染冒烟尚未完成；不放入专用服务端 mods。",
            [],
            ["outputs/chest-colorizer-equivalence-audit-20260808.md"],
        ),
        item(
            "Create Dynamic Blocking", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\create-dynamic-blocking-neoforge\build\libs\create-dynamic-blocking-1.0.0+neoforge.1.21.1-equivalence.1.jar",
            "conditional-candidate",
            "Create 6.0.10 API/Mixin/config/命令和真实对象 fixture 已通过；多 tick 双列车、真实客户端冷启动与全栈冲突仍需验证。",
            [r"D:\Trans\migration-audit-work\create-dynamic-blocking-smoke1\mods\create-dynamic-blocking-1.0.0+neoforge.1.21.1-equivalence.1.jar"],
            ["outputs/create-dynamic-blocking-equivalence-audit-20260809.md"],
        ),
        item(
            "Create NERFAD", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\mod-candidates\create-nerfad-1.2.3-neoforge+mc1.21.1.jar",
            "conditional-candidate",
            "16/16 配方结构、冷启动和 reload hash 通过；实际机器处理、JEI 与最终全栈仍需验证。",
            [r"D:\Trans\migration-audit-work\create-6.0.10-smoke3\mods\create_nerfad-1-2-3.jar"],
            ["outputs/create-nerfad-equivalence-audit-20260808.md"],
        ),
        item(
            "Happy Ghast", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\HappyGhast-1.21.1-equivalence\build\libs\happyghast-equivalence-1.0.0-equivalence.1+mc1.21.1.jar",
            "conditional-candidate",
            "NeoForge 两次启动、home_pos/home_radius NBT 往返和静态 client hook 通过；第三人称相机、temptation/player 客户端门禁仍在。",
            [r"D:\Trans\migration-audit-work\happyghast-equivalence-smoke1\mods\happyghast-equivalence-1.0.0-equivalence.1+mc1.21.1.jar", r"D:\Trans\migration-audit-work\nautilus-equivalence-smoke2\mods\happyghast-equivalence-1.0.0-equivalence.1+mc1.21.1.jar"],
            ["D:/Trans/migration-audit-work/HappyGhast-1.21.1-equivalence/SMOKE-20260808.md"],
        ),
        item(
            "Kaleidoscope Cookery", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\KaleidoscopeCookery-1.21.1-neoforge\build\libs\kaleidoscopecookery-1.4.1.7-migration.3-neoforge+mc1.21.1.jar",
            "conditional-candidate",
            "migration.3 是最新构建；配方/交易/官方 1.21.1 fixture 通过，生产 chef UUID/accounting 和真实客户端仍需关闭。",
            [r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\kaleidoscopecookery-1.4.1.7-migration.3-neoforge+mc1.21.1.jar", r"D:\Trans\migration-audit-work\tavern-migration-smoke1\mods\kaleidoscopecookery-1.4.1.7-migration.3-neoforge+mc1.21.1.jar"],
            ["outputs/cookery-official-1.21.1-fixture-audit-20260809.md"],
        ),
        item(
            "Kaleidoscope End", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\KaleidoscopeEnd-1.21.1-equivalence\build\libs\kaleidoscope_end-1.0.14-migration.7-neoforge+mc1.21.1.jar",
            "conditional-candidate",
            "migration.7 是最新构建；服务端升级 fixture 通过，模型/粒子/交互的真实客户端门禁仍需验证。",
            [r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\kaleidoscope_end-1.0.14-migration.7-neoforge+mc1.21.1.jar", r"D:\Trans\migration-audit-work\end-official-upgrade-smoke1\mods\kaleidoscope_end-1.0.14-migration.7-neoforge+mc1.21.1.jar"],
            ["outputs/end-official-upgrade-smoke-20260808.md"],
        ),
        item(
            "Kaleidoscope Nether equivalence overlay", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\KaleidoscopeNether-1.21.1-equivalence\build\libs\kaleidoscope-nether-equivalence-backport-1.1.9-equivalence.3+mc1.21.1.jar",
            "conditional-candidate",
            "这是 Nether 等价 overlay（含 Froglight 覆盖），不是独立 Froglight JAR；依赖 Nether 1.1.2、Cookery migration.3、Tavern 1.2.0。",
            [r"D:\Trans\migration-audit-work\tavern-migration-smoke1\mods\kaleidoscope-nether-equivalence-backport-1.1.9-equivalence.3+mc1.21.1.jar", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\kaleidoscope-nether-equivalence-backport-1.1.9-equivalence.3+mc1.21.1.jar"],
            ["outputs/froglight-equivalence-audit-20260808.md"],
        ),
        item(
            "Kaleidoscope Tavern", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\KaleidoscopeTavern-1.21.1\build\libs\kaleidoscopetavern-1.2.0-neoforge+mc1.21.1.jar",
            "conditional-candidate",
            "build/libs 版本是最新候选；world-migration-smoke1 仍有旧字节副本，必须替换后再做最终全栈和客户端验证。",
            [r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\kaleidoscopetavern-1.2.0-neoforge+mc1.21.1.jar", r"D:\Trans\migration-audit-work\tavern-migration-smoke1\mods\kaleidoscopetavern-1.2.0-neoforge+mc1.21.1.jar"],
            ["outputs/tavern-migration-audit-20260808.md"],
        ),
        item(
            "MineAstr", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\mineastr-validation\neoforge-1.21.1-current\build\libs\mineastr-0.6.25.jar",
            "conditional-candidate",
            "0.6.25 是当前 NeoForge 候选；静态/服务端 gate 通过，真实客户端 GUI/网络、AstrBot bridge、权限和客户端 TOML 迁移仍未关闭。",
            [r"D:\Trans\migration-audit-work\mineastr-validation\smoke1\mods\mineastr-0.6.25.jar"],
            ["outputs/mineastr-neoforge-1.21.1-current-validation-20260809.md", "outputs/mineastr-data-closure-validation-20260809.md"],
        ),
        item(
            "Mishang UC Pale Oak overlay", "candidate", "server+client (Fabric base via Connector)",
            r"D:\Trans\migration-audit-work\MishangUC-1.21.1-equivalence\build\libs\mishanguc-pale-oak-equivalence-backport-1.6.3-beta.5-equivalence.1+mc1.21.1.jar",
            "conditional-candidate",
            "Overlay 候选可用，但基础 mishanguc 仍是 Fabric JAR，经 Connector 运行；Connector 生产稳定性和真实客户端仍是门禁。",
            [r"D:\Trans\migration-audit-work\mishang-equivalence-smoke1\mods\mishanguc-pale-oak-equivalence-backport-1.6.3-beta.5-equivalence.1+mc1.21.1.jar"],
            ["outputs/mishang-pale-oak-equivalence-audit-20260808.md"],
        ),
        item(
            "Nautilus", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\nautilus-backport-audit\nautilus-equivalence\build\libs\nautilus-equivalence-0.1.0-equivalence.2+mc1.21.1.jar",
            "conditional-candidate",
            "BODY armor lifecycle/save-restart parity 已通过；41 个实体、骑乘/冲刺/繁殖/生成/掉落、玩家 GUI、模型音频和多人旧存档仍需验证。JAR 已嵌入 VanillaBackport 类，不要重复装 reference JAR。",
            [r"D:\Trans\migration-audit-work\nautilus-equivalence-smoke2\mods\nautilus-equivalence-0.1.0-equivalence.2+mc1.21.1.jar"],
            ["outputs/nautilus-body-lifecycle-smoke-20260809.md"],
        ),
        item(
            "Potted Farms", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\Potted-Farms-1.21.1-equivalence\potted-farms-1.1.1-equivalence3.jar",
            "conditional-candidate",
            "equivalence3 是最新候选；官方旧存档/Mending/Unbreaking11 fixture 通过。world-migration-smoke1 的 equivalence2 必须替换；候选仍缺公开发布/最终全栈签收。",
            [],
            ["outputs/potted-farms-final-audit-20260808.md"],
        ),
        item(
            "Respawn Pitch", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\respawn-pitch-compat\mod\build\libs\respawn-pitch-compat-1.0.0+mc1.21.1.jar",
            "conditional-candidate",
            "静态/NBT/API 通过；真实玩家死亡/重生、客户端 locale 和 HUD 仍需验证。",
            [r"D:\Trans\migration-audit-work\respawn-pitch-compat\smoke-server\mods\respawn-pitch-compat-1.0.0+mc1.21.1.jar"],
            ["outputs/respawn-pitch-equivalence-audit-20260809.md"],
        ),
        item(
            "Resource Error Overlay", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\mod-candidates\migration-resource-overlay-1.1.0+mc1.21.1.jar",
            "conditional-candidate",
            "资源错误覆盖层候选；静态资源检查通过，最终全栈需使用最新 JAR 再验证。",
            [r"D:\Trans\migration-audit-work\resource-overlay-fullstack-smoke1\mods\migration-resource-overlay-1.0.0+mc1.21.1.jar"],
            ["outputs/resource-overlay-equivalence-audit-20260808.md", "outputs/resource-overlay-render-closure-20260810.md"],
        ),
        item(
            "Tom's Simple Storage", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\Toms-Storage-NeoForge-1.21.1-perf-port\NeoForge\build\libs\toms_storage-neoforge-1.21.1-2.4.1-perf5.2.jar",
            "conditional-candidate",
            "perf5.2 候选包含 2.9.2 优化算法/7 filter MCA 转换；Create 6.0.10 空服 smoke 通过，完整世界转换、客户端和全栈仍需验证。",
            [r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\toms_storage-neoforge-1.21.1-2.4.1-perf5.2.jar", r"D:\Trans\migration-audit-work\tavern-migration-smoke1\mods\toms_storage-neoforge-1.21.1-2.4.1-perf5.2.jar"],
            ["D:/Trans/migration-audit-work/Toms-Storage-NeoForge-1.21.1-perf-port/MIGRATION-1.21.11-TO-1.21.1.md"],
        ),
        item(
            "Waypoint Fire", "candidate", "server+client",
            r"D:\Trans\migration-audit-work\waypoint-fire-equivalence\build\libs\waypoint-fire-equivalence-0.1.0-draft+mc1.21.1.jar",
            "draft-candidate",
            "服务端规则/NBT/restart 通过；版本标记为 draft，真实 HUD/icon、双客户端、Floodgate/Geyser 和压力测试仍未关闭。",
            [r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\waypoint-fire-equivalence-0.1.0-draft+mc1.21.1.jar", r"D:\Trans\migration-audit-work\waypoint-fire-equivalence\smoke-server\mods\waypoint-fire-equivalence-0.1.0-draft+mc1.21.1.jar"],
            ["outputs/waypoint-fire-equivalence-audit-20260808.md"],
        ),
        item(
            "XiyusLogin", "replacement", "server+client",
            r"D:\Trans\migration-audit-work\XiyusLogin-migration\build\libs\xiyuslogin-1.4-migration4.jar",
            "conditional-replacement",
            "Replaces EasyAuth. Migration4 retains migration3's packaged bcrypt/bytes runtime fix and disables the non-source blindness effect by default. Four synthetic Java network scenarios passed; Floodgate and proxy scenarios remain blocked.",
            [],
            [
                "outputs/xiyuslogin-auth-readiness-migration3-20260810.json",
                "outputs/xiyuslogin-migration3-synthetic-live-evidence-20260810.json",
                "outputs/xiyuslogin-migration3-synthetic-live-evidence-20260810.md",
                "outputs/xiyuslogin-migration4-render-freeze-audit-20260810.md",
            ],
        ),
    ]

    support = [
        item(
            "Mishang UC base migration.1",
            "support",
            "server+client (Fabric via Connector)",
            r"D:\Trans\migration-audit-work\mod-candidates\mishanguc-1.6.1-1.21.1-migration.1.jar",
            "connector-dependent",
            "Fabric 1.21.1 base with a deterministic full-descriptor GameRenderer mixin selector patch for Connector/NeoForge. It remains subject to the final client gate.",
            [r"D:\Trans\migration-audit-work\mishang-equivalence-smoke1\mods\mishanguc-1.6.1-1.21.1.jar"],
        ),
        item("Content Backport", "support", "server+client", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\backport-1.5.jar", "support-ready", "Happy Ghast、NERFAD、Tavern、Mishang/Potted 的 1.21.1 内容支持。", [r"D:\Trans\migration-audit-work\create-dynamic-blocking-smoke1\mods\backport-1.5.jar"]),
        item("Create", "support", "server+client", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\create-1.21.1-6.0.10.jar", "support-ready", "Create 6.0.10 隔离服基线。", [r"D:\Trans\migration-audit-work\create-dynamic-blocking-smoke1\mods\create-1.21.1-6.0.10.jar"]),
        item("Architectury", "support", "server+client", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\architectury-13.0.11-neoforge.jar", "support-ready", "Barched 和多个客户端/共享组件依赖。", [r"D:\Trans\migration-audit-work\happyghast-equivalence-smoke1\mods\architectury-13.0.11-neoforge.jar"]),
        item("Cloth Config", "support", "server+client", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\cloth-config-15.0.140-neoforge.jar", "support-ready", "Barched 配置界面依赖。", [r"D:\Trans\migration-audit-work\happyghast-equivalence-smoke1\mods\cloth-config-15.0.140-neoforge.jar"]),
        item("Kaleidoscope Nether base", "support", "server+client", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar", "support-ready", "Nether equivalence overlay 的明确 base 版本。", [r"D:\Trans\migration-audit-work\tavern-migration-smoke1\mods\kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar"]),
        item("Mishang UC base", "support", "server+client (Fabric via Connector)", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\mishanguc-1.6.1-1.21.1.jar", "connector-dependent", "基础 JAR 是 Fabric 模组，需 Connector；不是原生 NeoForge 适配。", [r"D:\Trans\migration-audit-work\mishang-equivalence-smoke1\mods\mishanguc-1.6.1-1.21.1.jar"]),
        item("GriefLogger", "replacement", "server-only", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\grieflogger-1.2.10-1.21.1-neoforge.jar", "replacement-ready", "按用户决定替代 Ledger；不迁移 Ledger 历史、查询和回滚数据，属于明确功能/数据取舍。", [r"D:\Trans\migration-audit-work\grieflogger-smoke1\mods\grieflogger-1.2.10-1.21.1-neoforge.jar"]),
    ]

    support = [entry for entry in support if entry["component"] != "Mishang UC base"]

    stale = [
        stale_item("XiyusLogin migration2", r"D:\Trans\migration-audit-work\final-client-mods-candidate3\xiyuslogin-1.4-migration2.jar", "rejected: bcrypt's transitive at.favre.lib:bytes runtime dependency is missing; live synthetic registration failed; use migration4"),
        stale_item("Barched invalid all artifact", r"D:\Trans\migration-audit-work\Barched-source\neoforge\build\libs\barched-neoforge-0.0.12-migration.1-all.jar", "22-byte manifestless Gradle artifact; do not deploy; use tested -asm runtime candidate."),
        stale_item("Kaleidoscope Cookery migration.1", r"D:\Trans\migration-audit-work\KaleidoscopeCookery-1.21.1-neoforge\build\libs\kaleidoscopecookery-1.4.1.7-migration.1-neoforge+mc1.21.1.jar", "older than migration.3"),
        stale_item("Kaleidoscope Cookery migration.2", r"D:\Trans\migration-audit-work\KaleidoscopeCookery-1.21.1-neoforge\build\libs\kaleidoscopecookery-1.4.1.7-migration.2-neoforge+mc1.21.1.jar", "older than migration.3"),
        stale_item("Potted Farms equivalence2 in world smoke", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\potted-farms-1.1.1-equivalence2.jar", "rejected; replace with equivalence3 candidate"),
        stale_item("Kaleidoscope Tavern world-smoke copy", r"D:\Trans\migration-audit-work\world-migration-smoke1\mods\kaleidoscopetavern-1.2.0-neoforge+mc1.21.1.jar", "stale byte copy; replace with build/libs latest"),
        stale_item("MineAstr 0.4.1", r"D:\Trans\migration-audit-work\mineastr-validation\neoforge-0.4.1\build\libs\mineastr-0.4.1.jar", "old branch; use 0.6.25 current candidate"),
        stale_item("Kaleidoscope End official 1.0.11", r"D:\Trans\migration-audit-work\official-candidates\kaleidoscope_end-1.0.11-neoforge+mc1.21.1.jar", "official baseline, not migration.7"),
        stale_item("Kaleidoscope Nether official 1.1.4", r"D:\Trans\migration-audit-work\official-candidates\kaleidoscope_nether-1.1.4-neoforge+mc1.21.1.jar", "not selected because overlay requires base 1.1.2"),
        stale_item("Nautilus legacy i_want_my_nautilus", r"D:\Trans\migration-audit-work\nautilus-backport-audit\i_want_my_nautilus-0.1-neoforge-1.21.1.jar", "reference implementation; do not co-install with embedded equivalence classes"),
        stale_item("Nautilus legacy platform", r"D:\Trans\migration-audit-work\nautilus-backport-audit\platform-neoforge-1.21.1-1.3.3.jar", "reference dependency; not required by final equivalence JAR"),
        stale_item("Nautilus legacy VanillaBackport", r"D:\Trans\migration-audit-work\nautilus-backport-audit\VanillaBackport-neoforge-1.21.1-1.1.7.10.jar", "reference implementation; do not duplicate embedded classes"),
        stale_item("Nautilus alias adapter", r"D:\Trans\migration-audit-work\nautilus-backport-audit\nautilus-alias-adapter\build\libs\nautilus-alias-adapter-0.1.0-audit.1+mc1.21.1.jar", "experimental and requires legacy i_want_my_nautilus; not final bundle"),
    ]

    missing = [
        {
            "component": "cc-chunk-npe-fix",
            "kind": "regression-waiver",
            "status": "covered-by-neoforge-cc",
            "reason": "The Fabric-only callback receives a nullable LevelChunk; NeoForge CC 1.120.0 uses ChunkTicketLevelUpdatedEvent without that parameter. Three-dimension forceload/save smoke completed with NPE=0 and ERROR=0, so no separate NeoForge port is required.",
        },
        {
            "component": "MineAstr AstrBot/client integration",
            "kind": "integration-artifact",
            "status": "needs-validation",
            "reason": "The MineAstr JAR exists, but real client GUI/network and AstrBot account/permission integration are not represented by a standalone candidate JAR.",
        },
        {
            "component": "Chest Colorizer client CSV/rendering harness",
            "kind": "validation-artifact",
            "status": "needs-validation",
            "reason": "The client-only JAR exists; a real client render and per-client colorizer.csv migration gate remains open.",
        },
        {
            "component": "Final full-stack client bundle",
            "kind": "bundle-assembly",
            "status": "assembled-needs-smoke",
            "reason": "Immutable server/client candidate directories exist with deterministic digests; the final 50-JAR cold-start and real-client smoke still must run. The older world-migration-smoke1 copy remains non-authoritative.",
        },
        {
            "component": "Froglight standalone JAR",
            "kind": "intentional-absence",
            "status": "not-required",
            "reason": "Froglight is covered by the Kaleidoscope Nether equivalence overlay and base; no separate standalone JAR is required.",
        },
    ]

    gates = [
        "Complete the strict XiyusLogin six-scenario live-login gate: the synthetic Java network flows cover four scenarios, while Floodgate UUID mapping and the supported proxy topology remain blocked.",
        "Prepare a fresh full-stack smoke from the immutable candidate directories; do not reuse stale world-migration-smoke1 copies.",
        "Run real NeoForge client cold-start/render/HUD/GUI matrix for Chest, Happy Ghast, End, Tavern, MineAstr, Nautilus, Waypoint, Respawn and Mishang/Connector.",
        "Complete MineAstr client GUI/network plus AstrBot integration and permissions; no credentials are included in this inventory.",
        "Run production-like old-save/full-stack and no-write second pass; this report does not perform that pass.",
        "Keep the cc-chunk-npe-fix regression waiver and its three-dimension NPE=0 evidence attached to the release record.",
        "Keep Ledger data-loss caveat explicit: GriefLogger is a replacement and Ledger history is not migrated; EasyAuth is replaced by XiyusLogin.",
    ]

    client_and_integration_gates = [
        {"component": "Chest Colorizer", "gate": "real client render plus per-client colorizer.csv migration", "status": "open"},
        {"component": "Happy Ghast", "gate": "third-person camera and temptation/player client behavior", "status": "open"},
        {"component": "Kaleidoscope End", "gate": "client model, particles, and interaction parity", "status": "open"},
        {"component": "Kaleidoscope Tavern", "gate": "client drink/fluid rendering and interaction parity", "status": "open"},
        {"component": "MineAstr", "gate": "client GUI/network, AstrBot bridge, account permissions, client TOML migration", "status": "open"},
        {"component": "Nautilus", "gate": "player GUI/equip, dispenser/shears, riding/dash/breeding/spawn/loot, client model/audio and multiplayer", "status": "open"},
        {"component": "Waypoint Fire", "gate": "real HUD/icon, dual-client, Floodgate/Geyser and pressure matrix", "status": "open"},
        {"component": "Respawn Pitch", "gate": "real player death/respawn and client locale behavior", "status": "open"},
        {"component": "Mishang UC", "gate": "Connector production stability and real client rendering", "status": "open"},
    ]

    return {
        "schema": 1,
        "generated_on": "2026-08-09",
        "target": {"minecraft": "1.21.1", "loader": "NeoForge", "neoforge": "21.1.241", "java": "21"},
        "scope": {
            "audit_root": str(AUDIT_ROOT),
            "production_root": str(PRODUCTION_ROOT),
            "production_tree_read": False,
            "world_or_log_scan": False,
            "server_started": False,
            "candidate_selection": "latest explicit build/libs or equivalence artifact; smoke copies compared byte-for-byte",
        },
        "release_candidates": candidates,
        "support_and_replacements": support,
        "stale_or_rejected": stale,
        "missing_or_needs_build": missing,
        "validation_gates": gates,
        "remaining_client_and_integration_gates": client_and_integration_gates,
        "privacy": {
            "player_data_included": False,
            "authentication_databases_read": False,
            "logs_read": False,
            "world_nbt_read": False,
            "secrets_embedded": False,
            "hashes_are_jar_sha256_only": True,
        },
    }


def write_outputs(inventory: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT.write_text(json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    candidates = inventory["release_candidates"]
    support = inventory["support_and_replacements"]
    stale = inventory["stale_or_rejected"]
    missing = inventory["missing_or_needs_build"]
    lines = [
        "# Final NeoForge 1.21.1 Mod Bundle Inventory (2026-08-09)",
        "",
        "本清单只记录 `D:\\Trans\\migration-audit-work` 中明确指定的 JAR。生产树 `D:\\Trans\\20260807` 未写入，未启动长时间服务器；未读取世界、日志、玩家资料库或认证数据库。SHA-256 是 JAR 文件摘要，不代表功能门禁已全部关闭。",
        "",
        "## Target",
        "",
        "- Minecraft `1.21.1` / NeoForge `21.1.241` / Java `21`",
        f"- Release-candidate rows: **{len(candidates)}**; support/replacement rows: **{len(support)}**",
        "- `conditional-candidate`/`draft-candidate` means a usable build exists but client or full-stack gates remain; it is not a release approval.",
        "",
        "## Release Candidates",
        "",
        "| Component | Sides | Mod ID / version | Bytes | SHA-256 | Canonical path | Smoke comparison | Status |",
        "|---|---|---|---:|---|---|---|---|",
    ]
    for row in candidates:
        canonical = row["canonical"]
        mod = (canonical.get("mods") or [{}])[0]
        comparisons = ", ".join(f"{c['state']} ({pathlib.Path(c['path']).name})" for c in row["smoke_comparisons"]) or "absent (no smoke copy)"
        lines.append(
            f"| {row['component']} | {row['install_sides']} | `{mod.get('id') or '-'} {mod.get('version') or '-'}` | "
            f"{canonical.get('bytes') if canonical.get('bytes') is not None else '-'} | `{canonical.get('sha256') or '-'}` | "
            f"`{canonical['path']}` | {comparisons} | {row['status']} |"
        )
    lines.extend(["", "## Support and Replacements", "", "| Component | Sides | Bytes | SHA-256 | Canonical path | Status |", "|---|---|---:|---|---|---|"])
    for row in support:
        canonical = row["canonical"]
        lines.append(f"| {row['component']} | {row['install_sides']} | {canonical.get('bytes') or '-'} | `{canonical.get('sha256') or '-'}` | `{canonical['path']}` | {row['status']} |")
    lines.extend(["", "## Stale or Rejected Artifacts", "", "| Component | Bytes | SHA-256 | Path | Reason |", "|---|---:|---|---|---|"])
    for row in stale:
        meta = row["metadata"]
        lines.append(f"| {row['component']} | {meta.get('bytes') or '-'} | `{meta.get('sha256') or '-'}` | `{row['path']}` | {row['reason']} |")
    lines.extend(["", "## Missing or Still Needs Build/Validation", ""])
    for row in missing:
        lines.append(f"- **{row['component']}** (`{row['status']}`): {row['reason']}")
    lines.extend(["", "## Remaining Gates", ""])
    for gate in inventory["validation_gates"]:
        lines.append(f"- {gate}")
    lines.extend(["", "## Client and Integration Gates", "", "| Component | Gate | Status |", "|---|---|---|"])
    for gate in inventory["remaining_client_and_integration_gates"]:
        lines.append(f"| {gate['component']} | {gate['gate']} | {gate['status']} |")
    lines.extend([
        "",
        "## Privacy and Scope Check",
        "",
        "- No player UUIDs, password hashes, login tokens, RCON values, world NBT, or log contents are embedded in this report.",
        "- Every canonical/smoke path is constrained to the audit workspace; the generator rejects paths under `D:\\Trans\\20260807`.",
        "- Ledger history/query/rollback is intentionally not migrated because GriefLogger is the selected replacement; EasyAuth is intentionally replaced by XiyusLogin.",
        "",
    ])
    MD_OUTPUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    inventory = build_inventory()
    write_outputs(inventory)
    print(json.dumps({
        "json": str(JSON_OUTPUT),
        "markdown": str(MD_OUTPUT),
        "candidate_count": len(inventory["release_candidates"]),
        "support_count": len(inventory["support_and_replacements"]),
        "stale_count": len(inventory["stale_or_rejected"]),
        "missing_or_gates": len(inventory["missing_or_needs_build"]),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
