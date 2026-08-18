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

`releaseSequence` 是发布顺序，而不是整合包展示版本。展示版本可以包含语义化名称，但发布序号必须严格单调递增。相同序号只允许同一 `releaseId` 和同一清单 SHA256 重放，以支持幂等启动检查。

### 文件来源与再分发边界

发布工具仍由 `java -jar MCSync-2.0.0.jar` 打开，但 UI 将从单层表格重构为发布项目、文件来源、配置操作、验证与导出四个工作区。文件来源有五种：

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

## 配置 OTA 边界

v5 将配置变更与文件替换分开描述：

- `config-set`：改变一个已知键。
- `config-merge`：合并一个受控配置片段。
- `file-replace`：只用于明确批准为整文件托管的配置。

每个操作都声明路径、格式、键、期望旧值、目标值、冲突策略和是否需要重启。配置状态不匹配时默认失败并保留玩家文件，不做猜测性覆盖。

以下内容不属于 MCSync 发布状态：单人/多人存档、玩家数据、地图探索缓存、gamerule、统计、成就、实体和区块数据。

## 启动与重启边界

MCSync 的检查、下载和校验发生在模组与配置被 NeoForge 消费之前。可以在 Minecraft 窗口内显示进度，但 Mod、KubeJS、注册表相关资源及大多数配置发生变化后仍必须重启。隐藏 helper 只负责在 JVM 退出后原子替换被占用文件，不把热替换伪装成安全能力。

## 当前阶段

- 已完成：MCSync 品牌与 2.0.0 构建身份；新旧文件名扫描兼容；v5 结构解析；配置操作模型；单调发布序号门禁；本地状态原子提交；便携自升级烟测。
- 待接入：v5 下载规划与现有同步事务；配置格式适配器；Minecraft 内进度界面；启动退出后的自替换/回滚统一事务；真实 1.9.x JAR 升级矩阵。
- 禁止：在上述门禁完成前将开发 JAR 放入活动客户端或交由 MCModSync/MCSync 清单自动分发。
