# 模组内部模块与既有重构图

本文在 `MODULE-CATALOG.md` 之下细化到模组内部的职责边界。内容用于协作定位，采用抽象层级，不记录底层实现步骤。

状态：**已重构**表示已有明确迁移或兼容改动；**兼容保留**表示主要保持来源行为；**边界待验**表示仍需隔离验证；**资料/禁用**表示不进入当前运行时。

## 客户端与显示

### Immersive Paintings × MineAstr

位置：`projects/patches/immersive-paintings-mineastr-compat`

内部模块：画作资源管理、NeoForge 客户端生命周期、图片编码与尺寸策略、MineAstr 翻译桥接、兼容合同测试。

既有重构：**已重构**。已补齐画作图片到 MineAstr 的可选翻译链，并保留原有画作实体存档兼容；MineAstr 缺席时仍保留基础画框能力。最终制品应替换旧同模组制品，不与其并存。

### Chest Colorizer

位置：`outputs/projects/chest-colorizer-neoforge-1.21.1`

内部模块：颜色状态与配置、方块/物品呈现、箱子渲染、区块渲染编译、Sodium 适配、平台装载策略。

既有重构：**边界待验**。已完成 NeoForge 结构化移植与颜色资源整理；普通未染色木桶默认接管、Sodium 与原生渲染互斥仍是独立视觉边界。

### Waypoint Fire

位置：`outputs/projects/waypoint-fire-equivalence`

内部模块：服务端航点状态、客户端状态/HUD、命令与颜色参数、网络同步、世界/实体数据、游戏规则。

既有重构：**兼容保留**。服务端权威状态、客户端显示和网络增量已分层；地图缓存迁移不属于世界 OTA。

### Resource Error Overlay

位置：`outputs/projects/resource-error-overlay-1.21.1`

内部模块：可选资源与依赖边界、客户端资源兜底、资源审计报告。

既有重构：**已重构**。将可选资源缺失从启动级错误降为有条件加载或视觉兜底，不替换真实玩法注册。

## 登录、身份与生命周期

### XiyusLogin

位置：`projects/ports/xiyuslogin-migration`、`projects/patches/xiyuslogin-auto-session-ota`

内部模块：模组入口、玩家认证与冻结、玩家数据、登录/管理命令、配置与文本、玩家/服务器事件、登录网络边界、EasyAuth 迁移资料。

既有重构：**已重构**。已完成 EasyAuth 数据迁移、正版自动认证桥、单人世界绕过与专用服务器认证边界拆分；普通密码登录仍是独立路径。IP session、TrueUUID 回执和远端 OTA 配置不能互相推断。

### TrueUUID

位置：`projects/ports/trueuuid-login-proxy-fix`

内部模块：核心身份 API、服务端登录与决策、会话与 UUID 迁移、代理/网络适配、配置与命令、平台实现。

既有重构：**已重构**。正版会话确认、离线回退、UUID 迁移和代理网络策略已经分层；认证协议版本必须客户端/服务端成对升级。

### CC:Tweaked 启停保护

位置：`outputs/projects/cctweaked-startup-shutdown-guard-neoforge`

内部模块：启停策略、服务端上下文、超时状态、字节码合同。

既有重构：**已重构**。只调整长任务与关闭阶段边界，保留普通脚本执行限制和异常 worker 的 fail-closed 语义；不触碰世界数据。

### Hot Bath / 结束客户端测试线

位置：`projects/ports/hotbath-trigger-registry-fix`、`projects/ports/end-client-harness`

内部模块：触发器与事件注册、客户端启动观测、结束条件、回归记录。

既有重构：**已重构 / 边界待验**。启动期注册故障与客户端测试流程已分离；harness 不属于生产模组。

## Create 与内容保护

### Create Carriage / Chute / Dynamic Blocking

位置：`outputs/projects/create-carriage-orientation-guard-neoforge`、`create-chute-unload-guard-neoforge`、`create-dynamic-blocking-neoforge`

内部模块：车厢方向判定、Chute 生命周期保护、动态阻挡规则、导航边界、各自的策略合同。

既有重构：**已重构**。三条线分别处理方向、卸载时序和导航阻挡，保持最小作用域，不改变 Create 全局方块实体校验。

### Deferred Content Protection

位置：`outputs/projects/deferred-content-protection-neoforge`

内部模块：保护载体与注册、容器与实体交互、配方入口、保护合同测试。

既有重构：**已重构**。将未完成玩法限制在可读、可存储、可安全迁移的载体层；危险交互保持 fail-closed，后续完整玩法必须替换而非并存。

### Kaleidoscope Cookery Scarecrow

位置：`outputs/projects/kaleidoscope-cookery-scarecrow-compat`

内部模块：旧版生物装备数据、目标容器语义、实体加载边界、兼容合同。

既有重构：**已重构**。旧版装备数据与目标容器语义已经分离，保留显式槽位和幂等边界。

## 世界生成、高度与诊断

### Heightmap 384→544

位置：`outputs/projects/heightmap-384-to-544-compat-neoforge`

内部模块：模组入口、高度数组兼容、区块接入、合同测试。

既有重构：**已重构，动态发布边界待验**。只处理旧高度表达与新高度容器兼容，不改变注册表、地形生成、区块脏标记或世界写入。高度 overlay 与同主世界群系过渡是两个议题。

### POI / SavedData / Recipe 诊断

位置：`outputs/projects/poi-migration-diagnostic`、`create-saveddata-probe`、`recipe-set-diagnostic`

内部模块：POI 观察、Create SavedData 观察、配方集合诊断。

既有重构：**诊断专用**。只扩展可观察性，不承担玩法修复，不随生产模组部署。

## 重点移植线

### Barched

位置：`projects/ports/barched`

内部模块：核心内容、实体/物品/AI、数据修复、客户端渲染、NeoForge bridge、mixin、资源与数据注册。

既有重构：**大规模移植**。平台 bridge、玩法实体/物品/AI、客户端呈现和数据修复已经分层；bridge 变化不等同于玩法变化。

### CEI

位置：`projects/ports/cei-2.4.2-with-2.5.1-backport`

内部模块：注册与物品、配方提供、Ponder/指南、数据映射、配置迁移、生成资源。

既有重构：**已重构**。旧版与新版材料、配方、映射和配置键已建立兼容边界；保留旧依赖栈时需整体审查 Apotheosis/CDP，不是只降单个组件。

### Kaleidoscope Nether / End / Tavern

位置：`projects/ports/kaleidoscope-nether-1.21.1-equivalence`、`kaleidoscope-end-1.21.1-equivalence`、`kaleidoscope-tavern-1.21.1`

内部模块：注册内容、流体与物品、配方/战利品、客户端资源、运行时等价守卫。

既有重构：**已重构**。来源内容已经拆成目标平台的注册、资源和数据层；资源 overlay 只处理可选边界，不替代模组本身。

### Happy Ghast / MishangUC / Froglight

位置：`projects/ports/happy-ghast-1.21.1-equivalence`、`mishanguc-1.21.1-equivalence`、`froglight-patch-1.21.1-equivalence`

内部模块：实体或方块内容、客户端粒子/渲染、数据资源、平台兼容、状态合同。

既有重构：**兼容保留**。重点是保持来源玩法和资源语义；缺失内容以等价层补足，不直接改写世界对象。

### Nautilus 系列

位置：`projects/ports/nautilus-equivalence`、`nautilus-alias-adapter`、`nautilus-spears-tracked-source`

内部模块：完整内容等价、命名别名、长矛/生物交互、跟踪资源。

既有重构：**分层重构**。别名适配器与完整等价层独立；名称兼容不代表新注册内容已经存在。

### Tom’s Storage

位置：`projects/ports/toms-storage-neoforge-1.21.1-perf-port`

内部模块：存储对象、网络/同步、容器交互、性能、目标平台适配。

既有重构：**性能与平台适配**。存储语义、客户端显示和性能调优分开维护；世界物品恢复由 OTA 账本负责。

## Patch 与资料线

### WorldEdit

位置：`projects/patches/worldedit-7.3.8-direction-property-fix`

内部模块：NeoForge 属性转换、方向属性分类、离线回归探针。

既有重构：**已重构**。普通枚举属性与方向属性的分类边界已收束，其他属性映射保持不变。

### Yuushya / TLM

位置：`projects/patches/yuushya-2.3.0-patchouli-safety`、`projects/patches/tlm-patchouli-spawn-box-balance`

内部模块：Patchouli 分类/条目资源、客户端展示安全、服务端配方策略、平衡文档。

既有重构：**已重构**。Yuushya 只处理无效展示引用；TLM 只处理明确授权的配方/指南边界，不把客户端补丁扩展成服务端玩法改写。

### MCModSync

位置：`projects/ports/mcmodsync-1.9.2-pinned-source`、`pack/mcmodsync-local-template`、`artifacts/mcmodsync-disabled`

内部模块：协议/目录研究、客户端 catalog 模板、禁用状态说明。

既有重构：**资料整理，当前禁用**。客户端和服务端测试都不使用 MCModSync；服务端绝不安装。

## 协作判断顺序

1. 先定位内部模块，再看其“既有重构”状态。
2. 涉及存档或线上世界时，转到 `outputs/tools/` 的三方审计与 OTA 域。
3. 只涉及显示、资源或客户端缓存时，不扩大到服务端世界变更。
