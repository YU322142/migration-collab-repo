# MCSync 2.0 开发合同

## 产品身份

- 面向玩家的名称、窗口标题、日志前缀和新产物名统一为 **MCSync**。
- 2.0 主产物名为 `MCSync-2.0.0.jar`。
- 技术 `modId` 保持 `mcmodsync`。这是 1.9.x 识别并替换升级器的稳定身份，不是遗留拼写错误。
- Java 包 `io.github.mcmodsync` 在 2.0 初期保持不变，避免一次品牌变更同时扩大为包级重构。

## 必须保留的 1.9.x 迁移入口

| 文件 | 责任 |
|---|---|
| `src/main/resources/fabric.mod.json` | 对外显示 MCSync，保留 `id=mcmodsync`。 |
| `src/main/resources/META-INF/neoforge.mods.toml` | 对外显示 MCSync，保留 `modId=mcmodsync`。 |
| `src/main/java/io/github/mcmodsync/ManagedClientConfig.java` | 继续读取旧配置和固定引导 JAR；后续新名称只能作为兼容别名加入。 |
| `src/main/java/io/github/mcmodsync/LegacyUpgradeManifest.java` | 为只理解 v1/v2 的客户端保留永久升级网关。 |
| `src/main/java/io/github/mcmodsync/ModManifest.java` | 扫描时同时识别旧 `MCModSync-*` 与新 `MCSync-*` 文件名。 |
| `src/main/java/io/github/mcmodsync/ModSyncEngine.java` | 自升级和防自身降级继续以稳定 modId 为准，不以品牌文件名为唯一依据。 |
| `src/test/java/io/github/mcmodsync/LegacyUpgradeIntegrationSmoke.java` | 使用真实历史 JAR 验证 1.9.x 到 2.0 的迁移链。 |
| `src/test/java/io/github/mcmodsync/PostBuildPortableSmoke.java` | 验证旧文件名可被新 `MCSync-*` 产物安全替换。 |

## 2.0 新发布模型

| 文件 | 抽象责任 |
|---|---|
| `ReleaseManifestV5.java` | 把一次 OTA 表达为有身份、有顺序、有文件集合和配置操作集合的不可变发布。拒绝越界路径、重复路径、未知类型和不完整操作。 |
| `StrictJson.java` | 为发布清单提供无隐式容错的最小 JSON 边界；重复键和尾随内容均视为发布错误。 |
| `ReleaseSequenceGate.java` | 维护客户端已成功应用的最高发布序号。低序号和同序号分叉均阻断；只有完整事务成功后才写状态。 |
| `ReleaseTransactionEngine.java` | 在同一事务中暂存、校验、配置变更、自更新、旧同 modId 替换、备份、原子提交、断电恢复和回滚。 |
| `ReleaseArtifactResolver.java` | 解析 publisher/direct/Modrinth/CurseForge/镜像候选；缓存已验哈希文件，任何来源都不能绕过清单 SHA256。 |
| `ParallelDownloadRunner.java` | 为旧清单与 schema-v5 提供统一的有界并发；默认 128，按任务数缩小，并允许通过系统属性下调。 |
| `PublisherModAutoMatcher.java` | 仅识别 `mods/*.jar`；批量计算并匹配 Modrinth SHA-512 与 CurseForge fingerprint，无法精确匹配时回退本地托管。 |
| `PublisherPlatformResolver.java` | 仅在发布者本机把 CurseForge fileId/API 解析为固定文件 URL；API key 不进入清单、JAR、客户端或日志。 |
| `ConfigMutationEngine.java` | 对 TOML、严格 JSON、properties 做键级 set/merge；凭据键、歧义键、类型漂移和无前像替换失败闭锁。 |
| `ManagedPathPolicy.java` | 定义可 OTA 的路径边界，拒绝存档、区块、玩家数据、缓存、原生库、符号链接和 `servers.dat` 普通覆盖。 |
| `MinecraftWindowStatus.java` / `SyncStatusReporter.java` | 在已有 Minecraft 窗口标题和 `.modsync/ui-status.json/.txt` 输出启动期状态；无额外更新器窗口，失败回退日志。 |
| `PublisherProjectV5.java` / `PublisherMain.java` | 发布项目审查、哈希物化、许可来源分离、镜像预设、v5 清单和发布报告；上游文件不会被复制到发布目录。 |

`releaseSequence` 是发布顺序，而不是整合包展示版本。展示版本可以包含语义化名称，但发布序号必须严格单调递增。GUI 默认在实际导出开始前以系统本地时间生成 `yyyyMMddHHmmssSSS`（17 位）序号；保存项目时同时记录是否启用自动刷新。关闭自动刷新仅用于精确复现或重放已经审计的固定发布。相同序号只允许同一 `releaseId` 和同一清单 SHA256 重放，以支持幂等启动检查。

### 文件来源与再分发边界

发布工具仍由 `java -jar MCSync-2.0.0.jar` 打开。主窗口已重构为发布项目、文件与来源、同步范围、配置 OTA、验证与导出五个工作区；1.9.x 工具保留为独立兼容页。来源决策只属于 Mod：发布器对 `mods/*.jar` 自动精确匹配平台，无法匹配才使用本地文件；其余目录固定本地托管，不参与模组站或许可来源选择。schema 为旧项目保留五种来源表达：

- `publisher-hosted`：发布者确认允许再分发，并由自己的发布目录提供文件；手工适配、自制兼容模组继续使用这种原有方式。
- `direct`：使用作者或项目提供的固定 HTTPS 文件地址。
- `modrinth`：固定项目 ID 和版本 ID，通过官方 API或受控镜像解析文件。
- `curseforge`：固定项目 ID 和 file ID；发布者 API key 只存在本机，不写入清单。
- `manual`：无法合法自动下载时提供人工处理信息；必须模组不得使用该模式发布。

下载方式和分发许可是两个独立但必须匹配的字段：

- `redistributable` 可以使用 `publisher-hosted`。
- `upstream-only` 只能使用作者官方直链或平台来源，发布器不得复制进我们的文件目录。
- `manual` 只能搭配 `manual` 来源。

schema 会拒绝 `publisher-hosted + upstream-only`。出于中国大陆或其他特殊网络环境考虑，`upstream-only` 仍可使用第三方 API 或文件代理，但镜像端点必须显式声明 `role=mirror` 与 `thirdParty=true`，发布器也必须展示来源警告。这样做不会把文件复制进我们的发布目录；无论官方源还是第三方镜像，客户端最终只接受与清单锁定 ID、大小和 SHA256 完全一致的文件。

首个内置中国区预设为 MCIMirror 的 API 前缀：Modrinth 使用 `https://mod.mcimirror.top/modrinth/v2/`，CurseForge 使用 `https://mod.mcimirror.top/curseforge/v1/`。该预设可关闭，异常时回退官方 API，且解析结果仍受固定项目/版本或文件 ID、大小和 SHA256 约束。

中国镜像只改变传输路径，不改变发布身份。所有候选下载最终都必须满足 v5 中固定的文件大小和 SHA256；镜像返回的“最新版”、文件名或元数据不能覆盖清单锁定值。

schema-v5 和旧版下载共用 `ParallelDownloadRunner`。默认上限为 128，少于 128 个任务时只创建对应数量的线程；系统属性 `mcsync.downloadThreads` 可在 1–128 内下调。发布器的平台识别通过 Modrinth/CurseForge 批量接口完成，不把下载并发数转换成 API 请求并发数。

## 配置 OTA 边界

v5 将配置变更与文件替换分开描述：

- `config-set`：改变一个已知键。
- `config-merge`：合并一个受控配置片段。
- `file-replace`：只用于明确批准为整文件托管的配置。

每个操作都声明路径、格式、键、期望旧值、目标值、冲突策略和是否需要重启。配置状态不匹配时默认失败并保留玩家文件，不做猜测性覆盖。

以下内容不属于 MCSync 发布状态：单人/多人存档、玩家数据、地图探索缓存、gamerule、统计、成就、实体和区块数据。

## 启动与重启边界

MCSync 的检查、下载和校验发生在模组与配置被 NeoForge 消费之前。可以在 Minecraft 窗口内显示进度，但 Mod、KubeJS、注册表相关资源及大多数配置发生变化后仍必须重启。隐藏 helper 只负责在 JVM 退出后原子替换被占用文件，不把热替换伪装成安全能力。

## 当前阶段（2026-08-18）

- 已完成：MCSync 品牌与 2.0.0 构建身份；新旧文件名扫描兼容；v5 结构解析与下载规划；配置键级 OTA；单调发布序号门禁；同版本篡改修复；断电事务日志恢复；旧 1.9.x 同 modId 自更新；NeoForge 原窗口标题进度；无弹窗状态 JSON；发布器平台/镜像解析与完整回归测试。
- 动态待验证：真实 NeoForge 渲染层内嵌覆盖层（当前安全实现使用原窗口标题，不创建第二窗口）；真实公网下的 Modrinth/CurseForge 镜像矩阵；在用户指定客户端之外的发布实例验证。
- 禁止：在上述门禁完成前将开发 JAR 放入活动客户端或交由 MCModSync/MCSync 清单自动分发。
