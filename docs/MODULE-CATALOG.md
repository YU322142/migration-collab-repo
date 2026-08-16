# 模组与适配模块目录

本文用于协作导航：说明每类模块在哪里、解决什么问题、涉及哪些重构边界。不记录底层实现步骤，也不是生产发布清单。需要进一步查看模组内部模块与既有重构时，阅读 `docs/MODULE-INTERNAL-REFACTOR-MAP.md`。

## 快速定位

| 需求 | 位置 |
| --- | --- |
| 来源模组的 1.21.1 移植或等价性 | `projects/ports/` |
| 单一崩溃、兼容缺口或玩法边界 | `projects/patches/` |
| 自维护的轻量 NeoForge 模组与诊断工程 | `outputs/projects/` |
| 配置、KubeJS、数据包模板 | `pack/` |
| 审计、转换、OTA、门禁和测试 | `outputs/tools/` |

## 长期移植与内容等价

| 模块组 | 位置 | 抽象职责 / 重构主题 | 范围 |
| --- | --- | --- | --- |
| CEI 兼容线 | `projects/ports/cei-2.4.2-with-2.5.1-backport` | 旧存档可读性与新玩法内容共存；依赖、数据和配置语义保持稳定。 | 双方 |
| 内容回移线 | `projects/ports/content-backport-cat-serializer-fix`、`create-nerfad-1.21.1-neoforge`、`potted-farms-1.21.1-equivalence-full` | 将来源版本内容收束到目标运行时，避免用一次性覆盖替代长期兼容。 | 双方或数据侧 |
| Kaleidoscope 系列 | `projects/ports/kaleidoscope-cookery-1.21.1-neoforge`、`kaleidoscope-nether-1.21.1-equivalence`、`kaleidoscope-end-1.21.1-equivalence`、`kaleidoscope-tavern-1.21.1` | 烹饪、下界、末地与酒馆内容的版本等价；世界数据、玩法与显示分层维护。 | 多数双方 |
| 生态等价线 | `projects/ports/happy-ghast-1.21.1-equivalence`、`mishanguc-1.21.1-equivalence`、`froglight-patch-1.21.1-equivalence`、`barched` | 生物、方块、装饰与交互语义的平稳迁移。 | 双方 |
| 航海与生物线 | `projects/ports/nautilus-equivalence`、`nautilus-alias-adapter`、`nautilus-spears-tracked-source` | 命名、物品兼容与玩法等价分层维护。 | 双方 |
| 基础设施线 | `projects/ports/toms-storage-neoforge-1.21.1-perf-port`、`respawn-pitch-compat` | 常用基础设施的可用性、性能预期和体验一致性。 | 双方 |

## 稳定性、认证与服务治理

| 模块组 | 位置 | 抽象职责 / 重构主题 | 范围 |
| --- | --- | --- | --- |
| 身份与登录 | `projects/ports/trueuuid-login-proxy-fix`、`projects/ports/xiyuslogin-migration`、`projects/patches/xiyuslogin-auto-session-ota` | 正版身份、密码认证、单人世界和专用服务器策略分离；不由历史身份猜测继承认证。 | 服务端主导，客户端配套 |
| 生命周期保护 | `projects/ports/hotbath-trigger-registry-fix`、`projects/ports/end-client-harness`、`outputs/projects/cctweaked-startup-shutdown-guard-neoforge` | 将启动、注册和关闭期风险收束为明确的策略边界。 | 按模块而定 |
| 规则保护 | `outputs/projects/deferred-content-protection-neoforge`、`outputs/projects/create-dynamic-blocking-neoforge`、`outputs/projects/create-chute-unload-guard-neoforge` | 对延迟内容、物流和自动化建立可审查的服务端规则。 | 服务端主导 |
| 诊断工程 | `outputs/projects/poi-migration-diagnostic`、`outputs/projects/recipe-set-diagnostic`、`outputs/projects/create-saveddata-probe` | 为迁移判断提供观察点；不是默认玩法内容。 | 诊断专用 |

## 客户端呈现与交互

| 模块组 | 位置 | 抽象职责 / 重构主题 | 范围 |
| --- | --- | --- | --- |
| 画框翻译兼容 | `projects/patches/immersive-paintings-mineastr-compat` | 画框图片、翻译服务和空间显示形成可选体验链；翻译缺席时保留基础画框功能。 | 客户端主导，双方配套 |
| WorldEdit 属性兼容 | `projects/patches/worldedit-7.3.8-direction-property-fix` | 编辑平台与目标运行时的方向属性语义一致。 | 双方 |
| Yuushya 指南兼容 | `projects/patches/yuushya-2.3.0-patchouli-safety` | 指南展示资源与玩法引用分层，保证阅读体验而不锁死未来扩展。 | 双方 |
| TLM 平衡层 | `projects/patches/tlm-patchouli-spawn-box-balance` | 女仆指南、配方和服务器玩法限制保持一致。 | 服务端权威，客户端展示 |
| 本地视觉与资源层 | `outputs/projects/chest-colorizer-neoforge-1.21.1`、`outputs/projects/resource-error-overlay-1.21.1`、`outputs/projects/waypoint-fire-equivalence` | 渲染状态、资源错误可见性和导航体验；不改写世界权威数据。 | 客户端主导 |

## 世界、地形与数据迁移

| 模块组 | 位置 | 抽象职责 / 重构主题 | 范围 |
| --- | --- | --- | --- |
| 高度与世界生成 | `outputs/projects/heightmap-384-to-544-compat-neoforge`、`pack/terrain-preservation-frontier-datapack-20260813`、`pack/worldgen-height-544-overlay-20260815` | 可建造高度、旧区块兼容和未来生成策略分层维护；高度扩展不等于同主世界过渡已获准。 | 双方与数据侧 |
| Create 世界对象 | `outputs/projects/create-carriage-orientation-guard-neoforge`、`outputs/projects/create-chute-unload-guard-neoforge` | 特定方块实体和自动化对象的可迁移行为语义。真实恢复由 OTA 工具负责。 | 服务端权威 |
| 配方与模板 | `pack/client-kubejs`、`pack/server-kubejs`、`pack/client-config`、`pack/server-config` | 脱敏的内容规则与配置模板，供审查和重建使用。 | 按侧别 |

## 分发边界

| 模块 | 位置 | 当前规则 |
| --- | --- | --- |
| MCModSync 资料 | `projects/ports/mcmodsync-1.9.2-pinned-source`、`pack/mcmodsync-local-template` | 只保留协议、目录和 catalog 研究资料；当前全局禁用，服务端绝不安装。 |
| 客户端导入与地图资料 | `outputs/tools/` 中的 Prism、JourneyMap/Xaero、资源相关脚本 | 帮助重建客户端体验，不属于世界 OTA，也不得覆盖协作者当前客户端改动。 |
| 外部制品索引 | `artifacts/EXTERNAL-ARTIFACTS.md`、`artifacts/EXTERNAL-ARTIFACTS.json` | 记录仓库外构建产物的身份与用途；索引不是分发目录。 |

## 协作原则

1. 先归入模块组，再判断影响客户端、服务端、世界或数据包。
2. 玩法重构、存档兼容、客户端呈现和发布流程分别记录。
3. 补丁保持单一职责；长期依赖迁入对应 `projects/ports/` 维护线。
4. 本文描述目标和边界；哈希、试验结果和执行证据放在 `reports/` 或外部制品索引。
