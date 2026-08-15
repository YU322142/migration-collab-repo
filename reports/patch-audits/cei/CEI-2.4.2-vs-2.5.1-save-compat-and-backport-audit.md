# Create: Enchantment Industry 2.4.2 ↔ 2.5.1 存档兼容与回移可行性审计

审计日期：2026-08-14（Asia/Shanghai）

## 1. 范围与安全边界

本报告比较以下两个 NeoForge 1.21.1 JAR：

- 2.4.2：D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3\instances\Mechanomania-Ultimate-Aeronautics-1.1.11.1\minecraft\mods\create-enchantment-industry-2.4.2.jar
- 2.5.1：D:\Trans\migration-audit-work\mechanomania-attempt2-compat-backup-20260814\runtime\create-enchantment-industry-2.5.1.jar

审计覆盖：

- 注册 ID：方块、物品、方块实体、实体、菜单、流体、配方类型/序列化器、数据组件、统计、创造模式标签页、自定义 registry。
- 持久化：方块实体 NBT、ItemStack 数据组件、Codec、旧键回退、DataFix/MissingMappings/remap。
- 运行兼容：Mixin 配置、依赖版本、资源与数据包、配方和 DataMap。
- 实际世界命中：关联三套候选世界的只读扫描结果，重点复核 Blaze Forger。
- 回移可行性：以 2.4.2 依赖底座承载 2.5.1 内容与修复的源码基线、裁剪项和构建路径。

安全约束：

- 未启动 Minecraft、NeoForge 客户端或服务端。
- 未写入任何世界。
- 未覆盖、重签名或修改上述两个 JAR。
- 所有反编译、源码和报告均位于 D 盘的独立审计目录。

## 2. 结论摘要

### 2.1 通用的 2.5.1 → 官方 2.4.2 回退

结论：NO_GO。

官方 2.4.2 不具备 2.5.1 新增的 blaze_composer、3 个半成品模板物品、affix_template 与 overlimit_affixes 数据组件，也不能理解 Blaze Forger 新的 Operation 键。只要世界或玩家物品实际使用这些内容，直接换回官方 2.4.2 就可能出现：

- 新方块/物品注册缺失；
- ItemStack 新组件无法被旧版无损读取；
- 超限词缀真实等级丢失或被降为旧版可表达的值；
- 非零 Forger Operation 被旧版当作默认 Mode=0；
- 新预览/工作状态被旧版忽略；
- 依赖或 required mixin ABI 不匹配时启动硬崩。

因此，“2.5.1 保存过”不能被视为可以无条件回退到官方 2.4.2。

### 2.2 当前候选世界的 CEI 实际数据

结论：CONDITIONAL_GO，仅限本次扫描到的 CEI 数据状态。

只读世界扫描没有发现：

- create_enchantment_industry:blaze_composer；
- 3 个 incomplete_*_affix_template；
- affix_template 或 overlimit_affixes 组件；
- compose_affix 统计的持久化命中。

handoff/attempt2 中仅有两个需要重点处理的 Blaze Forger：

| 坐标 | 2.5.1 字段 | 旧版读取后果 |
|---|---|---|
| (-176, 63, -127) | ForgingMode=0；Inventory.Operation=0；Inventory.Size=6 | 2.4.2 忽略 ForgingMode/Operation，缺少 Mode 时得到 0，语义仍为默认 MERGE；Size=6 可安全载入 |
| (27319, 72, -12892) | ForgingMode=0；Inventory.Operation=0；Inventory.Size=6 | 同上 |

所以，这两个目标方块实体在当前值为 0 的前提下，可被 2.4.2 语义等价地读成默认模式。若 Operation 以后变成非零，则不再成立。

特别注意：原始世界中对应 Inventory.Size=4。CEI 2.4.2 的 BlazeForgerInventory 内部构造容量是 6，但对外 getSlots() 返回 4；NeoForge ItemStackHandler 反序列化会按 NBT 的 Size 重设内部列表。Size=4 可能让内部槽 4/5 消失，而 CEI 的 onLoad/updateResult 仍访问它们，存在 IndexOutOfBounds 风险。目标候选的 Size=6 反而是正确、安全的结构；不要把它改回 4。

### 2.3 以旧依赖底座制作兼容回移版

结论：GO，可实现性高。

最佳方案不是把官方 2.5.1 源码/二进制强行降依赖，而是从官方提交 9317ba99d4647892873d9d56678a1b448b7959b4 建立独立 worktree。该提交已经包含几乎全部 2.5.0 玩法和关键修复，同时仍使用 2.4.2 时代的依赖：

- NeoForge 21.1.219，运行范围 [21.1.0,)；
- Create: Dragons Plus 1.11.2b，运行范围 [1.11.1,)；
- Apotheosis 8.5.4；
- Apothic Enchanting 1.5.3；
- Apothic Spawners 1.3.4；
- Sable 1.2.2。

9317ba9 到供应 JAR 对应的官方 2.5.1 源码 f1c38e07d1934ffb8020ac898c9ffe9a88d5dd46 之间仅 18 个文件变化，核心是依赖版本和 Apotheosis 8.7 材料名适配，并没有新增一套必须依赖 Sable 2.0.3 的玩法代码。

## 3. JAR 身份与完整性

| 版本 | 大小 | SHA-256 |
|---|---:|---|
| 2.4.2 | 1,283,517 B | 81F192BB53888E01F87A82EAAC2F261C93715F2221DBCF5D8A8D414F912F75EF |
| 2.5.1 | 1,573,096 B | 0D27024C0F8E94261689EB198D96003BA5A1697D4478B41E298BCA707CEAE988 |

结构统计：

- ZIP 文件项：735 → 846。
- 新增 115，删除 4，同路径内容变化 107，同路径字节完全一致 624。
- 新增项由 96 个 class、9 个 assets、10 个 data 文件组成。
- 删除项仅 4 个旧 class；没有删除任何旧 data/assets。
- JSON：271 → 288；严格解析错误 0；重复 ZIP 项 0。

## 4. 注册 ID 差异

### 4.1 旧 ID 稳定性

对 common 与 integration registry 类、字段、静态初始化字符串和注册代码比对后：

- 没有发现 2.4.2 已有的方块、物品、方块实体、流体、配方序列化器或组件 ID 被删除或改名。
- 两版都没有 CEI 自定义 EntityType 或 MenuType 注册；不存在实体/菜单 ID 迁移。
- 流体注册、配方类型/序列化器的既有 ID 保持。
- 完整模板物品 brass_affix_template、crystal_affix_template、apotheotic_affix_template 的 ID 保持，虽然实现类从旧 affixComposer 包迁至 blazeComposer.template。

这构成 2.4.2 → 2.5.1 正向兼容的主要静态证据。

### 4.2 2.5.1 新增

| 类别 | 新增 |
|---|---|
| BLOCK + BLOCK_ITEM + BLOCK_ENTITY | create_enchantment_industry:blaze_composer |
| ITEM | incomplete_brass_affix_template；incomplete_crystal_affix_template；incomplete_apotheotic_affix_template |
| DATA_COMPONENT_TYPE | create_enchantment_industry:affix_template；create_enchantment_industry:overlimit_affixes |
| CUSTOM_STAT | create_enchantment_industry:compose_affix |
| CREATIVE_MODE_TAB | create_enchantment_industry:apotheotic |
| Create arm interaction point | blaze_composer |
| DataMap | enchantment_processing/rules |
| 自定义 registry key | create_enchantment_industry:printing_behaviour，sync(false) |
| 内建 printing provider | package_address；package_pattern；copy；custom_name；enchanted_book；written_book；banner_pattern |

## 5. 持久化兼容性

### 5.1 数据组件与 Codec

2.4.2 的 CEIAXDataComponents 为空；2.5.1 新增：

- affix_template：AffixTemplateData Codec，持久化 rarity 和 entries；每个 entry 包含 affix、level、source_categories、transcendent。
- overlimit_affixes：持久化 levels 映射。

OverlimitAffixHelper 把大于 2.0 的真实等级保存在 overlimit_affixes 中，而原生 Apotheosis 组件只能保留被限制的表示。2.4.2 没有该组件注册，也没有对应 AffixHelperMixin，因此直接降级无法保证超限词缀的无损读取和再次保存。

旧版完整模板本身没有保存词缀内容。2.5.1 在缺少 affix_template 时会把旧模板当作空白模板，因此 2.4.2 → 2.5.1 是安全的；反向则只有在模板没有新组件时才可视为安全。

Ender Woven Bag 的 CEIADataComponents、StoredEntities、EnderWovenBagBlockEntity 在两版字节完全一致，stored_entities 组件没有变化。

### 5.2 Blaze Forger

2.4.2：

- 方块实体写 ProcessingTime、Inventory。
- Inventory 写 Cost、Mode、Conflicting、OverCap。

2.5.1：

- 方块实体写 ProcessingTime、ForgingMode、Inventory。
- Inventory 写 Cost、Operation、Conflicting、OverCap。
- 读取 Operation；缺失时显式回退旧 Mode。
- 方块实体还会从旧 Inventory.Mode 回填模式。

这说明官方只实现了 2.4.2 → 2.5.1 的显式兼容，没有实现 2.5.1 → 2.4.2 的非零模式兼容。旧版读取新 NBT 时：

- 忽略 ForgingMode；
- 找不到 Mode，getInt 返回 0；
- Operation=0 时偶然语义等价；
- Operation 非零时被错误降为 0。

建议兼容回移版同时写 Operation 和 legacy Mode，并继续双读。这样既保留 2.5 结构，也为紧急回退到官方 2.4.2 留出有限的兼容路径。

### 5.3 其他方块实体

既有关键字段保持：

- Blaze Enchanter：Seed、ProcessingTime、HeldItem。
- Classic Enchanter：ProcessingTime、HeldItem。
- Blaze Forger：ProcessingTime、Inventory，另见上述迁移。
- Affix Augmentor / Gem Cutter：ProcessingTicks、Powered；2.5.1 新 active/preview 字段读取时使用 contains 检测，旧存档缺字段走默认值。
- Infuser：Running、Ticks、ProcessingTicks、InfusionStats。

2.5.1 新增的预览/状态键包括 ActiveAffix、ActiveCost、HeldPreview*、PendingBlockedSuper*、SuperUnlocked 等。2.4.2 会忽略这些信息，可能使正在进行的界面预览或中间状态重置，但本次世界扫描未命中新组件/Composer 数据。

### 5.4 DataFix、重映射与旧键

未发现：

- CEI 自定义 DataFixer；
- MissingMappings 处理；
- 注册 ID remap；
- 可以把 2.5.1 新组件自动降级成 2.4.2 表示的通用迁移器。

因此不能依赖游戏自动修复通用降级。

## 6. Mixins、资源与玩法规则

### 6.1 Mixins

两版保留相同的 5 个 required mixin 配置，没有删除配置。2.5.1 新增：

- 主配置：FishingHookMixin。
- Apotheosis 配置：apotheosis.AffixHelperMixin。

配置仍为 required=true、defaultRequire=1。若所配依赖的类或方法 ABI 不符，这类差异可能在启动阶段硬崩，而不是安静禁用。

### 6.2 资源和数据

新增资源完整覆盖：

- blaze_composer blockstate、模型、物品模型、两张贴图和 loot。
- 3 个半成品模板模型及 sequenced assembly 配方。
- smithing 配方、advancement 和标签。
- penalty curse allow/deny 标签。
- 新 enchantment_processing/rules DataMap。

没有删除旧模型或贴图路径。

13 个语言 JSON 变化；en_us 与 zh_cn 各新增 202 个键、删除 0 个。zh_cn 另有 34 个值调整。

旧配方 ID 没有删除。5 个 dissolve_* 配方保持 ID，只把 Apotheosis 旧材料输入换成 8.7 新材料名；affix_augmentor 从 mythic_material 改为 godforged_pearl。这些是依赖 API/资源名适配，不是新世界 ID。

super_enchanting/custom_level_extension 仍存在但 values 被清空，限制规则迁到 enchantment_processing/rules。世界自定义 datapack 如果覆盖旧路径，需要显式迁移；否则可能出现玩法规则变化，但不属于区块/物品 ID 损坏。

## 7. 依赖变化与真实硬门槛

官方发布 metadata 的最低版本变化：

| 依赖 | 2.4.2 | 2.5.1 |
|---|---:|---:|
| NeoForge | 21.1.0 | 21.1.228 |
| Create: Dragons Plus | 1.11.1 | 1.11.3 |
| Apothic Enchanting | 1.5.3 | 1.6.0 |
| Apotheosis | 8.5.4 | 8.7.0 |
| Apothic Spawners | 1.3.4 | 1.4.0 |
| Sable | 1.2.2 | 2.0.3 |

Create 仍为 >=6.0.10，Touhou Little Maid 仍为 >=1.2.0。

源码/字节码证据显示：

- integration/sable 的 7 个类两版字节完全一致。
- integration/sable_apotheosis 的 6 个类两版字节完全一致。
- TL Maid/Sable 集成没有 2.5.1 新玩法源码变化。
- 9317ba9 的完整新玩法已经以 NeoForge 21.1.219、Sable 1.2.2、Apotheosis 8.5.4 成功作为官方开发基线。

所以 Sable 2.0.3、NeoForge 21.1.228、CDP 1.11.3 等是官方 2.5.1 发布依赖抬升，不是 9317ba9 新玩法代码的普遍硬门槛。

但 Blaze Composer/词缀模板属于 Apotheosis 集成。审计时目标 Prism 客户端目录未发现 Apotheosis、Apothic Enchanting、Apothic Spawners JAR；不安装兼容旧栈时，这部分只能保持可选/不注册，无法实际游玩。若要求完整玩法，客户端与服务端都必须匹配安装旧兼容栈。

## 8. 回移实现清单

### 8.1 可直接采用，且不必抬高依赖

推荐基线 9317ba9 已包含：

- Blaze Composer 和 affix template 全套类、注册、组件、统计、Mixin、配方、模型、贴图、语言和战利品。
- 3785595：Blaze Enchanter 区块同步崩溃修复。
- 51358b3：16–30 级经验数学修复。
- c138d25：Deployer 钓竿修复及 FishingHookMixin。
- e836d74：惩罚诅咒过滤。
- a3c81ed：扳手拆除保留经验。
- f830c07：标签化避雷针。
- f656e68：完成经典附魔导出。
- c6cee539：动态灌注输出数据保留，仍基于 Apothic Enchanting 1.5.3。
- c3d8f046：扩展染料色。
- 9317ba9：显式 printing behaviour registry。
- Forger 的 legacy Mode → Operation 回退。
- 旧 DataMap 的兼容回退与警告。

### 8.2 必须针对旧底座适配

1. 配置迁移

2.5 预览把 enchantmentMaxLevelExtension 拆成 blazeEnchanterMaxLevelExtension 与 blazeForgerMaxLevelExtension。官方没有为旧配置提供完整自动回退。应在新键没有被显式配置时，用旧键初始化二者，并写一次明确迁移日志，避免服主升级后玩法静默改变。

2. Apotheosis 8.5.4 材料

保留 9317ba9 使用的旧 ID/常量：

- common_material；
- uncommon_material；
- rare_material；
- epic_material；
- mythic_material。

不要直接复制 f1c38 的 8.7 canonical 材料名。涉及 CEIAXItems、CEIAXRecipeProvider、CEIAXPonderScenes 和生成配方。若以后要同时兼容 8.5/8.7，应集中封装按运行时资源存在性选择，避免直接链接已更名字段。

3. Create: Dragons Plus 1.11.2b 资源名

旧版本实际模型名是 rare_marble_gate_pacakge.json。不要复制 1.11.3 修正后的 rare_marble_gate_package。更稳妥的做法是把 advancement 图标改为 CEI 自身或原版物品，解除资源拼写耦合。

4. 旧 DataMap

继续保留 fallback/warning，并把：

- super_enchanting/custom_level_extension；
- forging/cost_multiplier；
- forging/split_enchantment_cost_multiplier

映射到新 enchantment_processing/rules.*。为服主写清覆盖迁移日志。

5. Industrial Foregoing

保留旧 essence 映射。f1c38 删除它不是玩法回移的必要条件。

6. Forger 双写

继续双读 Mode/Operation，并建议同时写 Operation 与 Mode。对于当前 Operation=0 的两个方块实体不是硬需求，但能防止以后非零模式在紧急回退时静默变成 0。

### 8.3 不应带入旧依赖版

- Apotheosis 8.7 / Apothic Enchanting 1.6 专属材料常量和生成配方。
- CDP 1.11.3 的资源拼写与 metadata 最低版本。
- Sable >=2.0.3 的强制最低版本。
- NeoForge >=21.1.228 的强制最低版本。
- Apothic Spawners 1.4 等只有构建/metadata 意义的发布门槛。

### 8.4 若继续以官方 2.5.1 提交 f1c38e 为开发基线

该路线本身可以走，但必须区分两种目标：

1. 只把 Sable 恢复到 1.2.2，继续保留 Apotheosis 8.7、Apothic Enchanting 1.6、CDP 1.11.3、NeoForge >=21.1.228：
   - 静态结论为 GO。
   - Sable 与 Sable-Apotheosis 集成类在 2.4.2/2.5.1 间字节一致，没有发现 Sable 2.0.3 专属链接。
   - 注册表和存档结构不会因为单独降低 Sable metadata 而改变。
   - 仍必须做一次真实编译和双端启动测试，但没有已知的源码/注册硬阻断。

2. 以 f1c38e 为基线，同时要求回到 2.4.2 时代的完整旧依赖栈：
   - 仅修改 Sable 和版本号不够。
   - 必须把下面的 2.5.1 专属依赖点恢复/裁剪，否则会出现编译链接失败、配方引用不存在物品或 advancement 缺图标。

必须修改的源码/构建项：

- gradle.properties：
  - NeoForge 恢复到可用旧基线及旧运行范围；
  - CDP 恢复 1.11.2b / [1.11.1,)；
  - Placebo、Apothic Attributes、Apothic Enchanting、Apothic Spawners、Apotheosis 恢复旧栈；
  - Sable 恢复 1.2.2；
  - Create Aeronautics 编译依赖按目标包恢复；
  - 设置独立 backport 版本，不保留官方 2.5.1 标识。
- src/integration/apotheosis/.../common/registry/CEIAXItems.java：
  godforged_pearl 恢复 mythic_material。
- src/integration/apotheosis/.../data/CEIAXRecipeProvider.java：
  MYSTERIOUS_SCRAP_METAL、TIMEWORN_FABRIC、LUMINOUS_CRYSTAL_SHARD、ARCANE_SANDS、GODFORGED_PEARL 恢复旧五级材料常量。
- src/integration/apotheosis/.../client/ponder/CEIAXPonderScenes.java：
  GODFORGED_PEARL、LUMINOUS_CRYSTAL_SHARD 恢复 MYTHIC_MATERIAL、RARE_MATERIAL。
- src/main/java/.../registry/CEIDataMaps.java：
  恢复 industrialforegoing:essence 映射，以免丢失旧玩法。
- src/main/java/.../config/CEIEnchantmentsConfig.java：
  为旧 enchantmentMaxLevelExtension → 两个新 max-level 键，以及旧 splitEnchantmentRespectLevelExtension → extractEnchantmentRespectLevelExtension 提供显式迁移/回退。

必须同步恢复或重新 datagen 的生成资源：

- advancement/assembly_aesthetics.json：
  旧 CDP 资源是 rare_marble_gate_pacakge；也可改用 CEI/原版图标彻底去耦。
- recipe/crafting/affix_augmentor.json。
- recipe/mixing/dissolve_common_material.json。
- recipe/mixing/dissolve_uncommon_material.json。
- recipe/mixing/dissolve_rare_material.json。
- recipe/mixing/dissolve_epic_material.json。
- recipe/mixing/dissolve_mythic_material.json。
- recipe/sequenced_assembly/brass_affix_template.json。
- recipe/sequenced_assembly/apotheotic_affix_template.json。
- tags/item/blaze_composer/super_activators.json。

f1c38e 相对 9317ba9 的其他变化中：

- build.gradle 的发布类型 ALPHA → BETA 不影响运行。
- CHANGELOG.md 与 MODPACK-README.md 不影响二进制。
- 除 CEIDataMaps 删除一个映射外，没有引入新的 NeoForge API 源码；静态差异没有显示必须使用 NeoForge 21.1.228 的代码理由。因此若恢复 NeoForge 21.1.219 编译基线，预期不存在源代码 API 阻断，但仍应以干净构建结果作为最终证据。

结论：父流程当前以 f1c38e 开发、只降 Sable 的做法没有已知硬阻断；若其实际目标还包含旧 Apotheosis/CDP 依赖，则必须完成上述精确裁剪。9317ba9 的优势是这些裁剪天然已经完成，返工和漏项风险更低，而不是注册表能力更强。

## 9. 源码基线、版本标识与构建路径

官方源码分支：1.21.1/6.0.0-dev。

关键提交：

| 用途 | 提交 |
|---|---|
| 官方 2.4.2 基线 | 56d1d50a282f015a322769f98353d0d7b1d88b87 |
| 首次 Blaze Composer | c7822dcd776e81765a16b825943bca416c397ab5 |
| 推荐旧依赖完整功能基线 | 9317ba99d4647892873d9d56678a1b448b7959b4 |
| 官方 2.5.0 | 37ec6810531895292d51d878ef8e7f7e8f83e992 |
| 供应 2.5.1 JAR 对应源码 | f1c38e07d1934ffb8020ac898c9ffe9a88d5dd46 |

官方远端未发现对应 tag。

推荐发布标识：

- mod_id 和 namespace 必须继续使用 create_enchantment_industry，所有注册 ID 原样保留，否则世界无法识别原内容。
- 建议版本：2.4.2-cei251-backport.1。
- 建议 JAR：create-enchantment-industry-2.4.2-cei251-backport.1.jar。
- 显示名可写 Create: Enchantment Industry (2.4.x Backport)。
- 必须保留 LICENSE，并附非官方 fork、源码基线与改动清单。
- 不得伪装成官方 2.4.2 或官方 2.5.1。

最小构建路线：

1. 从 9317ba9 创建独立 worktree，不在审计 clone、成品实例或世界目录内构建。
2. 应用上述配置迁移、旧材料/资源兼容、Forger 双写和独立版本标识。
3. JDK 21；Gradle wrapper 9.5.0；NeoForge ModDev 2.0.141。
4. Windows 构建：.\gradlew.bat build；需要重建数据时：.\gradlew.bat runData。
5. 产物位于 build\libs。
6. build 依赖 spotlessApply，会改源码格式；只允许在隔离 worktree 执行。
7. 4 GiB 内存机器建议：
   - GRADLE_USER_HOME 指向 D:\Trans\migration-audit-work\gradle-cache-cei-backport-20260814；
   - --no-daemon；
   - --max-workers=2；
   - -Dorg.gradle.jvmargs=-Xmx1536m。

审计用 filtered clone：

D:\Trans\migration-audit-work\cei-official-source-audit-20260814

该目录仅用于证据回溯；正式开发应另建 worktree。

## 10. 上线前最低验证门槛

完成兼容回移版后，至少通过：

1. 注册清单比对：2.4.2 全部旧 ID 保留，2.5.1 新 ID 与目标 JAR 一致，无 MissingMappings。
2. 服务端与客户端安装完全相同的 CEI 回移版及依赖版本；禁止一端官方 2.4.2、一端回移版。
3. 空世界启动测试：Mixin、registry、datagen、配方和 DataMap 均无错误。
4. 世界副本测试，不可直接用唯一主世界：
   - 加载并保存两个 Forger 坐标；
   - 验证 Inventory.Size 保持 6；
   - 验证 Mode/Operation 双写；
   - 逐项测试 MERGE/SPLIT 等非零模式。
5. ItemStack 往返：
   - 旧模板无组件；
   - 新 affix_template；
   - overlimit_affixes 大于 2.0；
   - 玩家背包、容器、掉落物、网络同步和重启后均保持。
6. Blaze Composer 全流程：半成品 sequenced assembly、smithing、配方解锁、统计、方块实体保存和拆除。
7. Apotheosis 8.5.4 材料、CDP 1.11.2b 图标、旧自定义 datapack 路径全部验证。
8. 从升级前备份恢复演练一次；不得把“能启动”当作“数据无损”。

## 11. 最终判定

| 场景 | 判定 | 条件 |
|---|---|---|
| 官方 2.4.2 存档升级到官方 2.5.1 | GO | 旧注册 ID 无删除；Forger 有显式旧键回退 |
| 任意 2.5.1 存档直接降到官方 2.4.2 | NO_GO | 新 ID、组件、非零 Operation 无法保证读取 |
| 本次 handoff/attempt2 候选降到 2.4.2，仅看已扫描 CEI 数据 | CONDITIONAL_GO | 没有新 ID/组件命中；两个 Forger 均 Operation=0、Size=6 |
| 从 9317ba9 制作 2.4.2 依赖底座的 2.5 内容回移版 | GO | 完成配置、旧材料/CDP、Forger 双写适配并通过测试 |

推荐最终路线：不要直接使用官方 2.4.2 承接未来运行；制作有独立版本标识的兼容回移版，以 9317ba9 为源码底座，保留 CEI 注册空间和 2.5 新组件，继续兼容旧 NBT/DataMap，并让客户端与服务端完全匹配。

## 12. 证据目录

- 本 JAR 审计：
  D:\Trans\migration-audit-work\cei-2.4.2-vs-2.5.1-save-compat-audit-20260814
- 世界实际数据审计：
  D:\Trans\migration-audit-work\cei-world-data-compat-audit-20260814
- 官方源码 filtered clone：
  D:\Trans\migration-audit-work\cei-official-source-audit-20260814
- 依赖 API 审计：
  D:\Trans\migration-audit-work\cei-dependency-api-audit-20260814

本目录中的 class-path-diff.json、per-class-nbt-key-diff.json、codec-fields-*.json、mixin-diff.json、data-diff.json、assets-diff.json、javap-*.txt 和反编译输出构成可复查证据。
