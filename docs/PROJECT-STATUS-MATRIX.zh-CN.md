# 项目状态与获取方式

快照日期：2026-09-06。

本文只整理迁移适配、维护分支、补丁和工具项目，不代表整合包中的全部上游模组。判断依据是当前 1.21.1 整合包目录、当前服务器玩法链和已公开的 release：

- **当前使用中**：仍在当前服务器、当前客户端整合包，或当前发布流程中。
- **历史使用**：只用于旧整合包、旧加载器、迁移阶段、复现或审查，当前服务器不再要求。
- **可直接下载发布**：仓库 release 已有可验证的 JAR/插件包，页面应直接给出资产入口。
- **需要自行编译/组装**：仓库只提供源码、数据包、overlay、补丁或脚本；使用者应按项目 README 和许可证准备上游文件后构建。

## 当前使用中

### 可直接下载发布

| 项目 | 作用 | 可用资产 |
| --- | --- | --- |
| MineAstr NeoForge | 服务器与客户端的聊天、图片和跨语言联动 | `YU322142/MineAstr` 的 `v0.6.30` JAR |
| MineAstr AstrBot 插件 | 让 AstrBot 接收、翻译并转发服务器消息 | `YU322142/MineAstr` 的 `astrbot-v0.6.30` ZIP |
| Immersive Paintings × MineAstr | 让画框图片进入 MineAstr 的图片/翻译链路 | `YU322142/ImmersivePaintings` 的 `0.7.15+1.21.1` JAR |
| Tom's Simple Storage 稳定分支 | 修复大型存储网络、重启恢复、容量和配方转移 | `YU322142/Toms-Storage` 的 `neoforge-1.21.1-2.3.0-perf5.2` JAR |
| Chest Colorizer NeoForge | 为箱子和木桶提供客户端颜色显示，同时保留原版默认木桶 | `YU322142/Chest-Colorizer-NeoForge` 的 `v1.6.1-equivalence.3` JAR |
| CC:Tweaked Startup/Shutdown Guard | 保护计算机冷启动和关机状态 | `YU322142/CCTweaked-Startup-Shutdown-Guard` 的 `v1.0.0-equivalence.1` JAR |
| Create Chute Unload Guard | 修复溜槽卸载边界，避免转换时物品丢失 | `YU322142/Create-Chute-Unload-Guard` 的 `v1.0.0-equivalence.1` JAR |
| Deferred Content Protection | 缺少完整实现时保护延迟内容安全加载 | `YU322142/Deferred-Content-Protection` 的 `v1.0.0-first-release.1` JAR |
| Hardcore Revival Death Message Fix | 抑制救援阶段的提前死亡提示，保留最终死亡信息 | `YU322142/Hardcore-Revival-Death-Message-Fix` 的 `v1.0.0-neoforge.1.21.1` JAR |
| Heightmap 384→544 Compat | 转换旧高度图，支持扩展建筑高度 | `YU322142/Heightmap-384-to-544-Compat` 的 `v1.0.0-neoforge.1.21.1` JAR |
| Kaleidoscope Cookery Scarecrow Compat | 迁移旧版稻草人实体 NBT 和装备槽 | `YU322142/Kaleidoscope-Cookery-Scarecrow-Compat` 的 `v1.0.0-candidate13.1` JAR |
| Kaleidoscope Nether Backport | 将当前玩法链需要的下界内容回移到 1.21.1 | `YU322142/Kaleidoscope-Nether-Backport` 的 `v1.1.9-equivalence.3` JAR |
| Mishang UC Pale Oak Equivalence | 补齐 1.21.1 的苍白橡木建筑能力 | `YU322142/MishangUC-Pale-Oak-Equivalence` 的 `v1.6.3-equivalence.1` JAR |
| Potted Farms 1.21.1 Equivalence | 提供花盆农场耐久规则的数据包等价实现 | `YU322142/Potted-Farms-1.21.1-Equivalence` 的 `v1.1.1-equivalence.3` JAR |
| Migration Resource Error Overlay | 以资源叠加方式修复迁移包资源缺口 | `YU322142/Migration-Resource-Error-Overlay` 的 `v1.2.0-candidate13` JAR |
| Waypoint and Fire Rule Equivalence | 回移航点和火焰规则，保持客户端与服务端一致 | `YU322142/Waypoint-Fire-Equivalence` 的 `v0.1.1` JAR |

### 需要自行编译/组装

| 项目 | 作用 | 形式 |
| --- | --- | --- |
| Create Carriage Orientation Guard | 保持载具朝向判定与迁移服务端一致 | NeoForge 源码 |
| Create Carriage Orientation Guard | 保持载具朝向判定与迁移服务端一致 | NeoForge 源码（当前 p0.2 尚无公开 JAR） |
| Nautilus Equivalence | 提供 Nautilus 与 Zombie Nautilus 的 1.21.1 等价实现 | 内部源码/构建；因含上游回移内容不公开 JAR |
| WorldEdit Direction Property Fix | 修复 WorldEdit 方向属性并提供复现校验 | 补丁/脚本 |
| Yuushya 2.3.0 Patchouli Safety | 提供 Yuushya 的 Patchouli 安全覆盖 | overlay/脚本 |

## 历史使用

### 可直接下载发布

| 项目 | 作用 | 说明 |
| --- | --- | --- |
| MCSync / MCModSync | 旧版客户端文件同步与 OTA | `YU322142/MCSync` 已归档；`v2.0.3`、`v1.9.6` 等仅作历史发布，不是当前同步方案 |
| Create Enchantment Industry | Fabric 1.21.11 时代的附魔工业玩法 | 旧线预发布 JAR，仅用于复现 |
| Create: Dragons Plus | Fabric 1.21.11 时代的龙内容扩展 | 旧线预发布 JAR，仅用于复现 |
| Create Dynamic Blocking | 回移迁移阶段使用的动态阻挡语义 | `YU322142/Create-Dynamic-Blocking` 的 `v1.0.0-equivalence.1` JAR，仅用于复现 |
| Create SavedData Probe | 检查 Create SavedData 的迁移状态 | `YU322142/Create-SavedData-Probe` 的 `v1.0.0` JAR，仅用于审计 |
| POI Migration Diagnostic | 检查世界迁移后的兴趣点状态 | `YU322142/POI-Migration-Diagnostic` 的 `v0.1.0` JAR，仅用于审计 |
| Recipe Set Diagnostic | 报告配方集合，确认玩法迁移完整性 | `YU322142/Recipe-Set-Diagnostic` 的 `v1.0.0` JAR，仅用于审计 |

### 需要自行编译/组装

| 项目 | 作用 | 形式 |
| --- | --- | --- |
| CC:Tweaked Startup/Shutdown Guard | 保护计算机冷启动和关机状态 | NeoForge 源码 |
| TLM Patchouli Spawn Box Balance | 调整任务书生成盒平衡 | overlay/脚本 |
| XiyusLogin Auto-Session OTA | 提供登录配置 OTA 的预览、备份和回滚流程 | PowerShell 脚本 |
| Kaleidoscope Tavern: Refabricated | Fabric 1.21.11 时代的酒馆内容移植 | 源码 |
| 旧版 MCModSync 资料目录 | 保存 1.9.x 兼容资料和示例 | 文档/配置，不是独立模组 |

## 使用规则

1. 当前使用中且有 release 的项目，优先使用页面给出的直接资产；不要把源码压缩包当作 JAR。
2. 当前使用中但只有源码、数据或 overlay 的项目，按 README 单独构建；不要从运行中的整合包反向打包第三方 JAR。
3. 历史项目只用于旧版本复现或审查；安装历史发布不能替代当前整合包。
4. MCSync 只有一个公开仓库：`YU322142/MCSync`。它已归档，不创建第二个同名仓库。
5. 协作仓库、诊断工具和迁移脚本不是玩家必装模组；它们的作用是开发、验证和运维。
