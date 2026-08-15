#!/usr/bin/env python3
"""Assemble the standalone Mechanomania UI-sanitization handoff on D:."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import unittest
import zipfile

from build_c6c_purified import sha256_file, stable_json, transform
from prepare_mechanomania_ui_overrides import build_overlay
from test_build_c6c_purified import verify
import test_build_c6c_purified_unit
from test_prepare_mechanomania_ui_overrides import verify_overlay
import test_prepare_mechanomania_ui_overrides_unit


TOOL_NAMES = (
    "build_c6c_purified.py",
    "test_build_c6c_purified.py",
    "test_build_c6c_purified_unit.py",
    "prepare_mechanomania_ui_overrides.py",
    "test_prepare_mechanomania_ui_overrides.py",
    "test_prepare_mechanomania_ui_overrides_unit.py",
    "audit_mechanomania_title_ui.py",
    "validate_mechanomania_ui_release.py",
    "package_mechanomania_ui_release.py",
)


def read_mod_id(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        text = archive.read("META-INF/neoforge.mods.toml").decode("utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("modId="):
            return stripped.split("=", 1)[1].split("#", 1)[0].strip().strip('"')
    raise RuntimeError(f"no modId in {path}")


def compare_variants(full: Path, lite: Path) -> dict:
    with zipfile.ZipFile(full, "r") as full_zip, zipfile.ZipFile(lite, "r") as lite_zip:
        full_files = {info.filename for info in full_zip.infolist() if not info.is_dir()}
        lite_files = {info.filename for info in lite_zip.infolist() if not info.is_dir()}
    full_only = full_files - lite_files
    lite_only = lite_files - full_files
    return {
        "full": {
            "path": str(full.resolve()),
            "bytes": full.stat().st_size,
            "sha256": sha256_file(full),
            "mod_id": read_mod_id(full),
            "file_entries": len(full_files),
        },
        "lite": {
            "path": str(lite.resolve()),
            "bytes": lite.stat().st_size,
            "sha256": sha256_file(lite),
            "mod_id": read_mod_id(lite),
            "file_entries": len(lite_files),
        },
        "common_file_entries": len(full_files & lite_files),
        "full_only_file_entries": len(full_only),
        "lite_only_file_entries": len(lite_only),
        "full_only_data_files": sum(name.startswith("data/") for name in full_only),
        "full_only_class_files": sum(name.endswith(".class") for name in full_only),
        "full_only_asset_files": sum(name.startswith("assets/") for name in full_only),
        "full_only_examples": sorted(full_only)[:80],
        "lite_only_entries": sorted(lite_only),
        "observed_loader_behavior": {
            "evidence": (
                "read-only Prism debug.log dated 2026-08-08: UniqueModListBuilder "
                "found 2 candidates for modid c6c and selected c6c-1.2.5.1.jar "
                "as the most recent version"
            ),
            "full_selected": True,
            "lite_classes_merged": False,
        },
        "decision": (
            "ship purified C6C full 1.2.5.1 only; do not co-install original full "
            "or C6C-lite because both declare modId c6c, NeoForge selected only full "
            "in the observed launch, and lite omits most full gameplay"
        ),
    }


def component_verdicts(
    audit_path: Path, variants: dict, entry_diff: dict, overlay: dict
) -> dict:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    hits = {row["name"]: row for row in audit.get("jar_hits", [])}

    def find(prefix: str) -> dict:
        matches = [row for name, row in hits.items() if name.lower().startswith(prefix)]
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one audited component starting with {prefix!r}; got {len(matches)}"
            )
        return matches[0]

    full = find("c6c-1.2.5.1")
    lite = find("c6c-lite-1.0.0.0")
    iris = find("iris-neoforge")
    torchmaster = find("torchmaster-neoforge")
    create = find("create-1.21.1")
    controllers = find("create_tweaked_controllers")
    modernfix = find("modernfix-neoforge")
    kubejs = find("kubejs-neoforge")
    overlay_rows = {row["path"]: row for row in overlay["emitted"]}
    excluded_rows = {row["path"]: row for row in overlay["excluded_not_copied"]}
    return {
        "schema": 1,
        "scope": "static title/branding/main-menu audit; no Minecraft runtime started",
        "components": [
            {
                "component": full["name"],
                "sha256": full["sha256"],
                "verdict": "purify_and_keep",
                "evidence": [
                    "c6c.mixins.json declares BrandingControlMixin, UI.LogoRendererMixin, and UI.TitleScreenMixin",
                    "TitleScreenMixin cancels TitleScreen.init and redirects menu.online to XYEBBS/BisectHosting",
                    "C6C replaces Minecraft title textures and menu.online translations",
                    f"purified output SHA-256 {entry_diff['output_sha256']}",
                    "all retained non-UI entries and data entries verified byte-identical",
                ],
            },
            {
                "component": lite["name"],
                "sha256": lite["sha256"],
                "verdict": "exclude",
                "evidence": [
                    "contains the same C6C title/branding/hosting hooks as full",
                    "declares the same modId c6c",
                    "observed NeoForge launch selected only full 1.2.5.1 as the newer candidate",
                    f"omits {variants['full_only_file_entries']} files present only in full",
                    "its 9 lite-only patch classes are version-specific follow-up audit items, not safe UI merge material",
                ],
            },
            {
                "component": iris["name"],
                "sha256": iris["sha256"],
                "verdict": "keep_unchanged",
                "evidence": [
                    "declared MixinTitleScreen injects after init",
                    "bytecode calls Iris.onLoadingComplete once and adds no button, logo, branding, or URL",
                    "removal could break shader initialization",
                ],
            },
            {
                "component": torchmaster["name"],
                "sha256": torchmaster["sha256"],
                "verdict": "keep_unchanged",
                "evidence": [
                    "MixinTitleScreen.class exists but is not declared by Torchmaster's NeoForge mixin configs",
                    "class bytecode only logs an example message and version when applied",
                    "undeclared class creates no title entry",
                ],
            },
            {
                "component": create["name"],
                "sha256": create["sha256"],
                "verdict": "keep_mod_disable_main_menu_button",
                "evidence": [
                    "Create declares no TitleScreen mixin",
                    "screen-init handler adds only Create's optional config button",
                    "menu.online is used as a row anchor, not as a hosting click handler",
                    "mainMenuConfigButtonRow=0 disables the title button while preserving the in-game row",
                    f"overlay SHA-256 {overlay_rows['config/create-client.toml']['output_sha256']}",
                ],
            },
            {
                "component": controllers["name"],
                "sha256": controllers["sha256"],
                "verdict": "keep_mod_disable_main_menu_button",
                "evidence": [
                    "menu.online is used only as a row anchor for Controller Settings",
                    "config_button_main_menu_row=0 disables the title button while preserving the in-game row",
                    f"overlay SHA-256 {overlay_rows['config/createtweakedcontrollers-client.toml']['output_sha256']}",
                ],
            },
            {
                "component": modernfix["name"],
                "sha256": modernfix["sha256"],
                "verdict": "keep_mod_disable_branding_mixin",
                "evidence": [
                    "feature.branding.BrandingControlMixin appends ModernFix branding",
                    "overlay sets exactly one active mixin.feature.branding=false",
                    f"overlay SHA-256 {overlay_rows['config/modernfix-mixins.properties']['output_sha256']}",
                ],
            },
            {
                "component": kubejs["name"],
                "sha256": kubejs["sha256"],
                "verdict": "keep_mod_clear_window_title_only",
                "evidence": [
                    "pack client config set window_title to Mechanomania 1.1.11.1",
                    "overlay clears only window_title and retains all other KubeJS client settings",
                    f"overlay SHA-256 {overlay_rows['kubejs/config/client.json']['output_sha256']}",
                ],
            },
        ],
        "non_mod_assets": [
            {
                "path": "icon.png",
                "verdict": "exclude_not_copied",
                "sha256": excluded_rows["icon.png"]["sha256"],
            },
            {
                "path": "config/create-client-1.toml.bak",
                "verdict": "exclude_stale_backup",
                "sha256": excluded_rows["config/create-client-1.toml.bak"]["sha256"],
            },
        ],
    }


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise RuntimeError(f"missing required source: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def file_hash_map(root: Path, excluded: set[str]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).as_posix() not in excluded
    }


def run_unit_tests() -> dict:
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    suite.addTests(loader.loadTestsFromModule(test_build_c6c_purified_unit))
    suite.addTests(loader.loadTestsFromModule(test_prepare_mechanomania_ui_overrides_unit))

    def test_ids(node: unittest.TestSuite) -> list[str]:
        rows: list[str] = []
        for test in node:
            if isinstance(test, unittest.TestSuite):
                rows.extend(test_ids(test))
            else:
                rows.append(test.id())
        return rows

    ids = test_ids(suite)
    result = unittest.TestResult()
    suite.run(result)
    report = {
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun,
        "test_ids": ids,
        "failures": [name for name, _ in result.failures],
        "errors": [name for name, _ in result.errors],
        "skipped": len(result.skipped),
    }
    if report["status"] != "PASS":
        raise RuntimeError("UI purifier/overlay unit tests failed")
    return report


def build_readme(entry_diff: dict, overlay: dict, variants: dict) -> str:
    output_sha = entry_diff["output_sha256"]
    source_sha = entry_diff["source_sha256"]
    lite_sha = variants["lite"]["sha256"]
    return f"""# Mechanomania UI 净化交接包

生成日期：2026-08-13。该包只处理标题、品牌和主菜单入口，不修改世界、服务器配置、端口、玩法数据或其它客户端功能；构建和校验过程没有启动 Minecraft，也没有写入生产、staging 或 Prism 实例。

## 最终选择

- 使用 `mods/c6c-1.2.5.1-purified.jar`，SHA-256：`{output_sha}`。
- 原始 C6C full 1.2.5.1：`{source_sha}`。
- 不要再放入原始 full，也不要放入 `c6c-lite-1.0.0.0.jar`（`{lite_sha}`）。full/lite 都声明 `modId=c6c`；现有只读启动日志证明 NeoForge 会按版本只选择 full 1.2.5.1，并不会把 lite 的类与 full 合并。lite 相比 full 少 {variants['full_only_file_entries']} 个 full-only 文件，其中包括 {variants['full_only_data_files']} 个数据文件和 {variants['full_only_class_files']} 个类文件，因此无法单独满足“保留全部玩法”。

## 已净化

- C6C：删除取消并重建原版标题页的 `UI.TitleScreenMixin`、改绘徽标的 `UI.LogoRendererMixin`、清空 NeoForge 品牌列表的 `BrandingControlMixin`，同时移除对应声明、标题纹理、`menu.online` 的 “Acquire a server” / “开服”覆盖和两个托管站外链。
- KubeJS：仅把 OS 窗口标题 `Mechanomania 1.1.11.1` 清空。
- ModernFix：显式设置 `mixin.feature.branding=false`，避免它重新向标题/F3 加入 ModernFix 品牌串。
- Create：仅把 `mainMenuConfigButtonRow` 设为 0；游戏内配置按钮仍为 row 3。
- Create Tweaked Controllers：仅把 `config_button_main_menu_row` 设为 0；游戏内按钮仍为 row 3。
- 整合包 `icon.png` 不复制到覆盖层；旧备份 `config/create-client-1.toml.bak` 也不复制，避免人工恢复或工具扫描时重新带回主菜单按钮值。

## 明确保留

- C6C 除上述 UI/品牌项之外的全部条目；结构校验确认 79 个实际 `data/` 文件未删改，所有保留条目逐字节一致。
- Iris `MixinTitleScreen`：它在标题页初始化结束后调用 Iris 加载完成钩子，不绘制品牌或托管按钮；删除会破坏着色器初始化。
- Torchmaster `MixinTitleScreen.class`：类存在但不在其 NeoForge mixin 配置中声明，属于未加载示例代码，保留不产生入口。
- Create 与 Create Tweaked Controllers 的模组本体及游戏内配置入口。
- FTB Quests 中解释“开服服务器配置”的普通任务文本；它不是主菜单托管入口，删除会误伤玩法文档。

## full / lite 独有补丁边界

lite 有 9 个 full 中不存在的类文件：`CombatEvents`、Aeronautics wheel mount、Create schematicannon、Jigsaw structure、两个 chunk/container 优化、一个 vertex-buffer 优化，以及两个 FXNT backpack mixin。现有启动日志明确显示这些类没有与 full 合并加载。它们属于不同 C6C 版本的补丁差异，不是本次可安全进行的 UI 净化项；直接跨版本拼接 mixin 会引入未经验证的目标方法与崩溃风险。因此本包保留最新 full 的原始行为，并把这 9 项记录在 `manifests/c6c-full-vs-lite.json`，交给后续兼容专项逐项判断，而不谎称已经做了二进制并集。

## 合并方法

1. 从目标客户端和服务端模组目录中排除原始 `c6c-1.2.5.1.jar` 与 `c6c-lite-1.0.0.0.jar`。
2. 把 `mods/c6c-1.2.5.1-purified.jar` 作为唯一 C6C 放入双方模组目录。
3. 将 `overrides/` 合并到客户端实例根目录；不要把该覆盖层应用到世界目录。
4. 不复制原整合包根目录 `icon.png` 或 `config/create-client-1.toml.bak`。
5. 先运行 `python tools/validate_mechanomania_ui_release.py .`。`manifests/release.json` 记录所有交付文件哈希。

## 审计结论

| 对象 | 决策 | 原因 |
|---|---|---|
| C6C full 1.2.5.1 | 净化后保留 | 是玩法更完整的唯一 C6C 选择 |
| C6C lite 1.0.0.0 | 排除 | 同 modId；运行时未被选择，且缺少 full 的大量玩法/世界数据 |
| Iris | 原样保留 | TitleScreen mixin 只完成初始化 |
| Torchmaster | 原样保留 | TitleScreen 示例类未声明加载 |
| Create | 原样保留本体，配置禁用主菜单按钮 | `menu.online` 只用于定位按钮行，不是托管跳转 |
| Create Tweaked Controllers | 原样保留本体，配置禁用主菜单按钮 | 同上 |
| ModernFix | 保留本体，禁用 branding mixin | 避免标题/F3 品牌串 |
| KubeJS | 保留全部功能，仅清空窗口标题 | 去掉整合包标题且不影响脚本玩法 |

## 校验范围与尚需人工烟测

自动校验包含：12 个净化/覆盖层单测、JAR CRC、精确移除清单、mixin 声明、禁用链接/文案/类引用、所有保留条目逐字节一致、覆盖层精确文件集、配置值、哈希与双构建确定性。

遵照本任务限制，本包没有启动 Minecraft。合并后的最终模组集合仍需人工烟测：原版标题页无自定义徽标和“开服/Acquire a server”跳转；Iris 着色器初始化；Create 与 C6C 玩法；客户端进入服务器；重启后存档加载。公开再分发修改版 JAR 前请另行核对上游许可。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-full", type=Path, required=True)
    parser.add_argument("--source-lite", type=Path, required=True)
    parser.add_argument("--overrides-source", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--tools-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"refusing to merge into non-empty release: {output}")
    output.mkdir(parents=True, exist_ok=True)
    manifests = output / "manifests"
    tests = output / "tests"
    manifests.mkdir(parents=True, exist_ok=True)
    tests.mkdir(parents=True, exist_ok=True)

    source_full = args.source_full.resolve()
    source_lite = args.source_lite.resolve()
    purified = output / "mods/c6c-1.2.5.1-purified.jar"
    entry_diff = transform(source_full, purified)
    entry_diff["output"] = "mods/c6c-1.2.5.1-purified.jar"
    structural = verify(source_full, purified)
    if structural["status"] != "PASS":
        raise RuntimeError("purified JAR failed structural verification")
    structural["output"] = "mods/c6c-1.2.5.1-purified.jar"
    (manifests / "entry-diff.json").write_bytes(stable_json(entry_diff))
    (tests / "c6c-structural.json").write_bytes(stable_json(structural))

    overlay = build_overlay(args.overrides_source, output / "overrides")
    overlay["output"] = "overrides"
    (manifests / "overlay-diff.json").write_bytes(stable_json(overlay))
    overlay_check = verify_overlay(output / "overrides")
    if overlay_check["status"] != "PASS":
        raise RuntimeError("generated overlay failed structural verification")
    overlay_check["overlay"] = "overrides"
    (tests / "overlay-structural.json").write_bytes(stable_json(overlay_check))
    unit_tests = run_unit_tests()
    (tests / "unit-tests.json").write_bytes(stable_json(unit_tests))

    variants = compare_variants(source_full, source_lite)
    (manifests / "c6c-full-vs-lite.json").write_bytes(stable_json(variants))
    audit_destination = manifests / "title-ui-audit.json"
    audit_source = args.audit.resolve()
    copy_file(audit_source, audit_destination)
    verdicts = component_verdicts(audit_source, variants, entry_diff, overlay)
    (manifests / "component-verdicts.json").write_bytes(stable_json(verdicts))

    tools_source = args.tools_source.resolve()
    for name in TOOL_NAMES:
        copy_file(tools_source / name, output / "tools" / name)

    (output / "README.md").write_text(
        build_readme(entry_diff, overlay, variants), encoding="utf-8", newline="\n"
    )

    release = {
        "schema": 1,
        "created": "2026-08-13",
        "purpose": "Mechanomania title/branding/main-menu hosting purification",
        "runtime_started": False,
        "production_modified": False,
        "staging_modified": False,
        "prism_modified": False,
        "selected_c6c": "mods/c6c-1.2.5.1-purified.jar",
        "selected_c6c_sha256": entry_diff["output_sha256"],
        "excluded_c6c": [
            {"name": "c6c-1.2.5.1.jar", "sha256": entry_diff["source_sha256"]},
            {"name": "c6c-lite-1.0.0.0.jar", "sha256": variants["lite"]["sha256"]},
        ],
        "policy": {
            "c6c_full": "purified_and_keep",
            "c6c_lite": "exclude",
            "iris_title_mixin": "keep_initialization_hook",
            "torchmaster_title_class": "keep_undeclared_example",
            "create": "keep_mod_disable_main_menu_button_only",
            "create_tweaked_controllers": "keep_mod_disable_main_menu_button_only",
            "modernfix": "keep_mod_disable_branding_mixin",
            "kubejs": "keep_features_clear_window_title_only",
            "pack_icon": "exclude",
        },
        "files": {},
    }
    release["files"] = file_hash_map(output, {"manifests/release.json"})
    (manifests / "release.json").write_bytes(stable_json(release))
    print(json.dumps({
        "output": str(output),
        "c6c_sha256": entry_diff["output_sha256"],
        "file_hashes": len(release["files"]),
        "structural_status": structural["status"],
    }, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
