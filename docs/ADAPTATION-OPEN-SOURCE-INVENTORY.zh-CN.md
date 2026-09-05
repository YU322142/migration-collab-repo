# 服务器迁移期间的模组适配与开源清单

快照日期：2026-09-05。本文是协作入口，回答三件事：做过哪些模组适配、源码和脚本在哪里、哪些内容已经公开或仍需许可/脱敏确认。文件级入口继续以 `MODULE-FILE-INDEX.md` 为准，抽象职责以 `MODULE-CATALOG.md` 和 `MODULE-INTERNAL-REFACTOR-MAP.md` 为准。

## 最新优先：Chest Colorizer

最终稳定修复工程已经单独公开：

- 本地源码：`outputs/projects/chest-colorizer-neoforge-1.21.1/`
- 独立公开仓库：`YU322142/Chest-Colorizer-NeoForge`
- 公开版本：`v1.6.1-equivalence.3`
- 最终 JAR：`chest-colorizer-1.6.1-equivalence.3+mc1.21.1-neoforge.jar`
- SHA-256：`EC8D9D3AAE816C5E0FAF46DFF284C63530E2460B4801D4F6E1EDF7120D8180A2`
- 工程入口：`README.md`、`DEVELOPMENT.md`、`build.gradle`、`src/main/java/net/immortaldevs/colorizer/`

该版本保留未染色/`default` 木桶的原始 `minecraft:barrel` 状态，仅对显式染色木桶使用自定义状态，并使 Sodium 与原生区块渲染路径互斥。它是纯客户端适配，服务端不安装。

## 独立公开的维护项目

| 项目 | 本地项目文件 | 公开状态 |
| --- | --- | --- |
| MCSync | `projects/ports/mcsync-2.0.0/`；完整历史在发布工作区 `MCSync` | GitHub `YU322142/MCSync`，当前公开版本 `v2.0.3` |
| MineAstr NeoForge | 发布工作区 `MineAstr` | GitHub `YU322142/MineAstr`，当前公开版本 `v0.6.30` |
| MineAstr AstrBot 插件 | 发布工作区 `MineAstr-astrbot-plugin` | GitHub `YU322142/MineAstr` 的 `astrbot-plugin` 分支，当前公开版本 `astrbot-v0.6.30` |
| Immersive Paintings × MineAstr | `projects/patches/immersive-paintings-mineastr-compat/` | GitHub `YU322142/ImmersivePaintings`，当前公开版本 `0.7.15+1.21.1` |
| Tom's Storage 性能/平台适配 | `projects/ports/toms-storage-neoforge-1.21.1-perf-port/` | GitHub `YU322142/Toms-Storage`，NeoForge 公开版本 `neoforge-1.21.1-2.3.0-perf5.2`，受上游条款约束 |
| Chest Colorizer | `outputs/projects/chest-colorizer-neoforge-1.21.1/` | 已新建公开仓库并发布 `v1.6.1-equivalence.3` |

### 本次新增的独立公开仓库

下列项目均已从干净源码副本公开；构建缓存、JAR/ZIP 制品、世界数据和凭据未进入仓库。

| 项目 | GitHub 仓库 | 发布边界 |
| --- | --- | --- |
| CC:Tweaked Startup/Shutdown Guard | `YU322142/CCTweaked-Startup-Shutdown-Guard` | 独立 NeoForge 源码，MIT |
| Create Carriage Orientation Guard | `YU322142/Create-Carriage-Orientation-Guard` | 独立兼容源码，MIT；不含 Create JAR |
| Create Chute Unload Guard | `YU322142/Create-Chute-Unload-Guard` | 独立兼容源码，MIT；不含 Create JAR |
| Create Dynamic Blocking | `YU322142/Create-Dynamic-Blocking` | 独立兼容源码，MIT；不含 Create JAR |
| Create SavedData Probe | `YU322142/Create-SavedData-Probe` | 诊断源码，MIT；不含世界数据 |
| Deferred Content Protection | `YU322142/Deferred-Content-Protection` | 独立 NeoForge 源码，MIT |
| Hardcore Revival Death Message Fix | `YU322142/Hardcore-Revival-Death-Message-Fix` | 独立兼容源码，MIT；不含上游 JAR |
| Heightmap 384→544 Compat | `YU322142/Heightmap-384-to-544-Compat` | 独立兼容源码，MIT；不含区块/世界 |
| Kaleidoscope Cookery Scarecrow Compat | `YU322142/Kaleidoscope-Cookery-Scarecrow-Compat` | 独立兼容源码，MIT；不含上游 JAR |
| Kaleidoscope Nether Backport | `YU322142/Kaleidoscope-Nether-Backport` | 自有等价源码/数据，MIT；遵守上游条款 |
| Mishang UC Pale Oak Equivalence | `YU322142/MishangUC-Pale-Oak-Equivalence` | 自有兼容源码，LGPL-3.0-or-later；不含上游 JAR |
| POI Migration Diagnostic | `YU322142/POI-Migration-Diagnostic` | 诊断源码，MIT；不含 POI/世界快照 |
| Potted Farms 1.21.1 Equivalence | `YU322142/Potted-Farms-1.21.1-Equivalence` | 自有数据包快照；不含存档或第三方制品 |
| Recipe Set Diagnostic | `YU322142/Recipe-Set-Diagnostic` | 诊断源码，MIT；不修改存档 |
| Migration Resource Error Overlay | `YU322142/Migration-Resource-Error-Overlay` | 自有资源修复源码/数据；不含上游 JAR |
| Waypoint and Fire Rule Equivalence | `YU322142/Waypoint-Fire-Equivalence` | 独立兼容源码，MIT；不含服务端数据 |
| TLM Patchouli Spawn Box Balance | `YU322142/TLM-Patchouli-Spawn-Box-Balance` | 仅公开 overlay、构建/校验脚本；不含 TLM JAR |
| WorldEdit Direction Property Fix | `YU322142/WorldEdit-Direction-Property-Fix` | 仅公开补丁/构建/校验脚本；不含 WorldEdit JAR |
| XiyusLogin Auto-Session OTA | `YU322142/XiyusLogin-Auto-Session-OTA` | 仅公开 OTA 脚本/文档；不含认证库、凭据或服务端存档 |
| Yuushya 2.3.0 Patchouli Safety | `YU322142/Yuushya-2.3.0-Patchouli-Safety` | 仅公开 overlay/构建/校验脚本；不含 Yuushya JAR |

## 完整适配工程目录

下列目录都属于本次迁移期间的源码、兼容层或验证工程；不是运行中的服务端副本。

### `projects/ports/`：长期移植与等价线

`barched`、`cei-2.4.2-with-2.5.1-backport`、`content-backport-cat-serializer-fix`、`create-nerfad-1.21.1-neoforge`、`end-client-harness`、`froglight-patch-1.21.1-equivalence`、`happy-ghast-1.21.1-equivalence`、`hotbath-trigger-registry-fix`、`kaleidoscope-cookery-1.21.1-neoforge`、`kaleidoscope-end-1.21.1-equivalence`、`kaleidoscope-nether-1.21.1-equivalence`、`kaleidoscope-tavern-1.21.1`、`mcmodsync-1.9.2-pinned-source`、`mcsync-2.0.0`、`mishanguc-1.21.1-equivalence`、`nautilus-alias-adapter`、`nautilus-equivalence`、`nautilus-spears-tracked-source`、`potted-farms-1.21.1-equivalence-full`、`respawn-pitch-compat`、`toms-storage-neoforge-1.21.1-perf-port`、`trueuuid-login-proxy-fix`、`xiyuslogin-migration`。

### `projects/patches/`：单一兼容补丁

`immersive-paintings-mineastr-compat`、`tlm-patchouli-spawn-box-balance`、`worldedit-7.3.8-direction-property-fix`、`xiyuslogin-auto-session-ota`、`yuushya-2.3.0-patchouli-safety`。

### `outputs/projects/`：自维护 NeoForge 模组与诊断工程

`cctweaked-startup-shutdown-guard-neoforge`、`chest-colorizer-neoforge-1.21.1`、`create-carriage-orientation-guard-neoforge`、`create-chute-unload-guard-neoforge`、`create-dynamic-blocking-neoforge`、`create-saveddata-probe`、`deferred-content-protection-neoforge`、`hardcore-revival-death-message-fix-neoforge`、`heightmap-384-to-544-compat-neoforge`、`kaleidoscope-cookery-scarecrow-compat`、`kaleidoscope-nether-backport`、`mishanguc-pale-oak-equivalence`、`poi-migration-diagnostic`、`potted-farms-1.21.1-equivalence`、`recipe-set-diagnostic`、`resource-error-overlay-1.21.1`、`waypoint-fire-equivalence`。

### `pack/` 与 `outputs/tools/`：玩法规则、脚本和迁移工具

- 服务端规则与 KubeJS：`pack/server-kubejs/`、`pack/server-config/`
- 客户端资源与 KubeJS：`pack/client-kubejs/`、`pack/client-config/`
- 女仆自定义资源：`pack/common-tlm-custom-pack/`
- 地形/高度 overlay：`pack/terrain-preservation-frontier-datapack/`、`pack/worldgen-height-544-overlay/`
- 世界、方块实体、存储、地形和玩家数据迁移：`outputs/tools/`
- 仓库检查、清单、脱敏和协作工具：`tools/repository/`

## 公开边界

### 可以公开

- 我们编写或明确拥有维护权的 Java/Kotlin/Python/PowerShell/JavaScript 源码。
- KubeJS、数据包、配置模板、构建脚本、单元测试和不含真实身份的审计样例。
- 适配说明、模块索引、变更日志、合规的第三方许可证文本。
- Chest Colorizer、MineAstr、MCSync 等已经单独公开的仓库和 release。
- 上表列出的独立兼容模组、诊断工程和补丁仓库；没有独立 release 的项目只发布源码，制品仍按上游许可在本地构建。

### 不直接公开

- 线上世界、区块、实体、POI、SavedData、玩家背包和认证数据库。
- 真实服务器地址、RCON/API/TrueUUID 凭据、令牌、私钥、账号绑定信息。
- 客户端实例目录、用户缓存、日志和 crash dump。
- 上游作者未允许再分发的模组 JAR、整合包 ZIP、资源包/光影包和第三方模型纹理。
- 只用于一次性审计的运行时快照；它们只能在 `artifacts/` 中以脱敏索引描述。

## 协作者如何找到未公开材料

1. 先看 `artifacts/EXTERNAL-ARTIFACTS.md`，用记录的用途和 SHA-256 在拥有者机器上寻找外部制品。
2. 再看 `docs/SOURCE-MAP.md` 与 `docs/MODULE-FILE-INDEX.md`，按相对路径进入源码。
3. 如果项目目录只有补丁而没有上游源码，先确认上游许可证和再分发条款；不要从运行中的客户端反向打包。
4. 需要线上数据时，由服务器拥有者提供一次性脱敏快照；仓库只接收转换脚本和结果摘要。

## 公开前检查

```text
python tools/repository/sanitize_snapshot.py
python tools/repository/check_repository.py
git diff --check
```

公开快照中的路径统一使用 `<WORKSPACE>`、`<AUDIT_ROOT>`、`<HANDOFF_ROOT>`、`<INSTANCE_ROOT>`、`<TRANS_ROOT>` 等占位符。若某个文件仍包含真实路径、账号、令牌或未确认的第三方资源，应留在本地并在交接文档中说明原因。
