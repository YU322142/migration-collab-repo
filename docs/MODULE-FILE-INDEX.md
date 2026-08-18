# 模组文件级索引

本文把主要模块落到具体文件。路径均相对于仓库根目录；同一模块的完整资源树仍以项目自身的构建配置为准，但协作者可以直接从下表进入核心职责文件，不需要先猜目录结构。

## Patch 模块

### Immersive Paintings × MineAstr

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 画作资源管理 | `projects/patches/immersive-paintings-mineastr-compat/source/common/src/main/java/net/conczin/immersive_paintings/ClientPaintingManager.java` | 已补充图片读取与客户端缓存边界。 |
| NeoForge 客户端入口 | `projects/patches/immersive-paintings-mineastr-compat/source/neoforge/src/main/java/net/conczin/immersive_paintings/neoforge/ClientNeoForge.java` | 已整理客户端生命周期接入。 |
| 图片编码 | `projects/patches/immersive-paintings-mineastr-compat/source/neoforge/src/main/java/net/conczin/immersive_paintings/neoforge/compat/MineAstrImageCodec.java` | 已建立画作图片与翻译请求之间的资源边界。 |
| MineAstr 桥接 | `projects/patches/immersive-paintings-mineastr-compat/source/neoforge/src/main/java/net/conczin/immersive_paintings/neoforge/compat/MineAstrTranslationCompat.java` | 已重构为可选兼容层；MineAstr 缺席时保留画框基础能力。 |
| 兼容合同 | `projects/patches/immersive-paintings-mineastr-compat/source/neoforge/src/test/java/net/conczin/immersive_paintings/neoforge/compat/MineAstrTranslationCompatTest.java` | 已覆盖兼容边界；不属于运行时模组。 |
| 制品范围 | `projects/patches/immersive-paintings-mineastr-compat/overlay-manifest.json`、`ARTIFACT-REFERENCE.md`、`AUDIT.md` | 已锁定替换范围和旧旋转存档兼容。 |

### WorldEdit 方向属性

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| NeoForge 属性转换 | `projects/patches/worldedit-7.3.8-direction-property-fix/source/com/sk89q/worldedit/neoforge/internal/NeoForgeTransmogrifier.java` | 已收束普通枚举属性与方向属性的分类边界。 |
| 离线回归探针 | `projects/patches/worldedit-7.3.8-direction-property-fix/test/DirectionPropertyCacheProbe.java` | 已验证方向属性修复不改变普通属性映射。 |
| 变更说明 | `projects/patches/worldedit-7.3.8-direction-property-fix/WORLDEDIT-7.3.8-DIRECTION-PROPERTY-FIX-AUDIT.md` | 记录重构范围与保留项。 |

### Yuushya Patchouli

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 指南分类与条目 | `projects/patches/yuushya-2.3.0-patchouli-safety/patch-root/assets/yuushya/patchouli_books/yuushya_guidebook/en_us/categories/mod_functions.json` | 已将展示索引与正文内容分离。 |
| 基础建造指南 | `projects/patches/yuushya-2.3.0-patchouli-safety/patch-root/assets/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/building_techniques/bt_survival_building_material.json` | 已保留正文玩法内容，只处理失效展示引用。 |
| 生存玩法指南 | `projects/patches/yuushya-2.3.0-patchouli-safety/patch-root/assets/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/building_techniques/bt_survival_gameplay.json` | 同上，未扩展成玩法重写。 |
| 验证 | `projects/patches/yuushya-2.3.0-patchouli-safety/test_yuushya_230_patchouli_fix.py` | 已覆盖条目数量和资源范围。 |

### TLM / 女仆指南

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 生成盒指南 | `projects/patches/tlm-patchouli-spawn-box-balance/overlay/kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/maid/spawn_maid.json` | 已恢复与当前服务端配方一致的指南语义。 |
| 祭坛指南 | `projects/patches/tlm-patchouli-spawn-box-balance/overlay/kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/overview/multiblocks_altar.json` | 已保留平衡说明边界。 |
| 静态校验 | `projects/patches/tlm-patchouli-spawn-box-balance/verify_tlm_patchouli_balance_fix.py`、`reports/static-dual-side-verification.json` | 已确认客户端展示与服务端规则分离。 |

### XiyusLogin OTA

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 认证配置 | `projects/patches/xiyuslogin-auto-session-ota/desired/xiyuslogin-session-values.toml` | 已将自动会话配置限制为明确的配置层变更。 |
| OTA 合同 | `projects/patches/xiyuslogin-auto-session-ota/manifest.json` | 已限定模组、配置和回滚范围，不包含世界与玩家数据。 |
| 协作说明 | `projects/patches/xiyuslogin-auto-session-ota/README-zh-CN.md` | 已记录停服、回滚和客户端/服务端边界。 |

## 自维护 NeoForge 模块

### CC:Tweaked 启停保护

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 启停策略 | `outputs/projects/cctweaked-startup-shutdown-guard-neoforge/src/main/java/dev/migration/cctweakedguard/CCTweakedStartupGuard.java` | 已重构长任务与关闭阶段边界。 |
| 服务端上下文 | `outputs/projects/cctweaked-startup-shutdown-guard-neoforge/src/main/java/dev/migration/cctweakedguard/mixin/ServerContextMixin.java` | 保留异常 worker 的安全信号。 |
| 超时状态 | `outputs/projects/cctweaked-startup-shutdown-guard-neoforge/src/main/java/dev/migration/cctweakedguard/mixin/TimeoutStateMixin.java` | 与普通 Lua 执行限制保持分离。 |
| 合同测试 | `outputs/projects/cctweaked-startup-shutdown-guard-neoforge/src/test/java/dev/migration/cctweakedguard/CCTweakedBytecodeContractTest.java` | 已固定重构边界。 |

### Create 兼容保护

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 车厢方向 | `outputs/projects/create-carriage-orientation-guard-neoforge/src/main/java/dev/migration/create_carriage_orientation_guard/CarriageOrientationDecision.java`、`CreateCarriageOrientationGuard.java`、`mixin/OrientedContraptionEntityMixin.java` | 已限定为方向语义保护。 |
| Chute 卸载 | `outputs/projects/create-chute-unload-guard-neoforge/src/main/java/dev/migration/create_chute_unload_guard/ChuteGuardDecision.java`、`CreateChuteUnloadGuard.java`、`mixin/ChuteBlockEntityMixin.java` | 已限定为卸载时序保护。 |
| 动态阻挡 | `outputs/projects/create-dynamic-blocking-neoforge/src/main/java/com/antigravity/create_dynamic_blocking/DynamicBlockingConfig.java`、`DynamicBlockingHandler.java`、`DynamicBlockingMath.java`、`mixin/NavigationMixin.java` | 已限定为导航阻挡，不扩大全局方块校验。 |

### Deferred Content Protection

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 保护载体 | `outputs/projects/deferred-content-protection-neoforge/src/main/java/dev/migration/deferred_content_protection/DeferredContentProtection.java`、`ProtectedDeferredItem.java` | 已将未完成内容限制在可读、可存储载体。 |
| 容器边界 | `outputs/projects/deferred-content-protection-neoforge/src/main/java/dev/migration/deferred_content_protection/mixin/AbstractContainerMenuMixin.java` | 保留普通容器转移，阻断危险处理路径。 |
| 实体边界 | `outputs/projects/deferred-content-protection-neoforge/src/main/java/dev/migration/deferred_content_protection/mixin/AbstractHorseMixin.java`、`EntityMixin.java` | 已保持 fail-closed。 |
| 配方边界 | `outputs/projects/deferred-content-protection-neoforge/src/main/java/dev/migration/deferred_content_protection/mixin/RecipeManagerMixin.java` | 未完成玩法不作为有效加工内容。 |

### Heightmap 384→544

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 模组入口 | `outputs/projects/heightmap-384-to-544-compat-neoforge/src/main/java/dev/migration/heightmap_384_to_544_compat/Heightmap384To544Compat.java` | 已建立独立高度兼容层。 |
| 高度表达 | `outputs/projects/heightmap-384-to-544-compat-neoforge/src/main/java/dev/migration/heightmap_384_to_544_compat/HeightmapArrayConverter.java` | 只处理旧/新高度容器的兼容。 |
| 区块接入 | `outputs/projects/heightmap-384-to-544-compat-neoforge/src/main/java/dev/migration/heightmap_384_to_544_compat/mixin/ChunkAccessMixin.java` | 不改变地形生成和世界写入策略。 |
| 测试 | `outputs/projects/heightmap-384-to-544-compat-neoforge/src/test/java/dev/migration/heightmap_384_to_544_compat/Heightmap384To544CompatTest.java` | 已覆盖高度兼容边界。 |

### Cookery Scarecrow

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 旧 NBT 语义 | `outputs/projects/kaleidoscope-cookery-scarecrow-compat/src/main/java/dev/migration/kaleidoscope_cookery_scarecrow_compat/LegacyScarecrowNbt.java` | 已分离旧装备数据与目标容器语义。 |
| 实体加载 | `outputs/projects/kaleidoscope-cookery-scarecrow-compat/src/main/java/dev/migration/kaleidoscope_cookery_scarecrow_compat/mixin/ScarecrowEntityMixin.java` | 保留显式槽位和幂等边界。 |
| 合同测试 | `outputs/projects/kaleidoscope-cookery-scarecrow-compat/src/test/java/dev/migration/kaleidoscope_cookery_scarecrow_compat/ScarecrowCompatTest.java` | 已固定迁移范围。 |

### Chest Colorizer

| 内部模块 | 文件 | 既有重构 |
| --- | --- | --- |
| 颜色管理 | `outputs/projects/chest-colorizer-neoforge-1.21.1/src/main/java/net/immortaldevs/colorizer/ColorManager.java`、`ColorizerConfig.java`、`ColorizerCsvDocument.java` | 已完成 NeoForge 配置与颜色状态移植；普通木桶默认接管仍是边界待验。 |
| 方块呈现 | `outputs/projects/chest-colorizer-neoforge-1.21.1/src/main/java/net/immortaldevs/colorizer/block/ColorizedBarrelBlock.java`、`BlockColor.java` | 保留染色方块呈现。 |
| 渲染接入 | `outputs/projects/chest-colorizer-neoforge-1.21.1/src/main/java/net/immortaldevs/colorizer/mixin/ChestRendererMixin.java`、`BlockMixin.java`、`ItemMixin.java` | 已分离箱子/物品/方块渲染边界。 |
| 编译器与 Sodium | `outputs/projects/chest-colorizer-neoforge-1.21.1/src/main/java/net/immortaldevs/colorizer/mixin/SectionCompilerMixin.java`、`mixin/sodium/LevelSliceMixin.java` | 互斥策略仍需动态视觉确认。 |

## 大型移植线的文件级入口

### Happy Ghast

| 模块 | 文件 |
| --- | --- |
| 内容入口 | `projects/ports/happy-ghast-1.21.1-equivalence/src/main/java/com/bmt/happyghast_equivalence/HappyGhastEquivalence.java` |
| 语义工具 | `projects/ports/happy-ghast-1.21.1-equivalence/src/main/java/com/bmt/happyghast_equivalence/HappyGhastEquivalenceUtil.java`、`RideStatSemantics.java` |
| 迁移状态 | `projects/ports/happy-ghast-1.21.1-equivalence/src/main/java/com/bmt/happyghast_equivalence/MigratedRideStats.java` |
| 客户端/实体边界 | `projects/ports/happy-ghast-1.21.1-equivalence/src/main/java/com/bmt/happyghast_equivalence/client/HappyGhastClientEvents.java`、`mixin/HappyGhastMixin.java`、`mixin/ServerPlayerMixin.java` |
| 既有重构 | 已重构 ride stats 与实体/客户端边界；统计兼容需与世界实体迁移分开。 |

### MishangUC

| 模块 | 文件 |
| --- | --- |
| 内容与注册 | `projects/ports/mishanguc-1.21.1-equivalence/src/main/java/pers/solid/mishang/uc/migration/MishangPaleOakContent.java`、`MishangPaleOakEquivalence.java` |
| 粒子与客户端 | `projects/ports/mishanguc-1.21.1-equivalence/src/main/java/pers/solid/mishang/uc/migration/MishangPaleOakParticles.java`、`client/MishangPaleOakClientEvents.java`、`client/TintedLeavesParticle.java` |
| 方块类型接入 | `projects/ports/mishanguc-1.21.1-equivalence/src/main/java/pers/solid/mishang/uc/migration/PaleOakColoredLeavesBlock.java`、`mixin/BlockEntityTypeAccessor.java` |
| 既有重构 | 兼容内容、客户端粒子和方块类型已拆分；不改变既有世界方块。 |

### Kaleidoscope End

| 模块 | 文件 |
| --- | --- |
| 末地公共逻辑 | `projects/ports/kaleidoscope-end-1.21.1-equivalence/src/main/java/com/bmt/kaleidoscope_end/common/DragonBreathCloudService.java`、`KEEndermiteInfo.java` |
| 事件与流体物品 | `projects/ports/kaleidoscope-end-1.21.1-equivalence/src/main/java/com/bmt/kaleidoscope_end/event/DragonBreathBucketEventBackport.java`、`item/DragonBreathBucket.java` |
| 食物注册 | `projects/ports/kaleidoscope-end-1.21.1-equivalence/src/main/java/com/bmt/kaleidoscope_end/init/KEFoodBiteRegistry.java` |
| 既有重构 | 注册、事件、物品和资源已分层，资源 overlay 不替代该模组。 |

### Kaleidoscope Nether

| 模块 | 文件 |
| --- | --- |
| 等价入口 | `projects/ports/kaleidoscope-nether-1.21.1-equivalence/src/main/java/com/bmt/kaleidoscope_nether/migration/KaleidoscopeNetherEquivalence.java`、`RuntimeEquivalenceGuard.java` |
| 方块/物品 | `projects/ports/kaleidoscope-nether-1.21.1-equivalence/src/main/java/com/bmt/kaleidoscope_nether/migration/NetherDollBlock.java`、`NetherDollItem.java` |
| 流体 | `projects/ports/kaleidoscope-nether-1.21.1-equivalence/src/main/java/com/bmt/kaleidoscope_nether/migration/NetherJuiceFluids.java`、`NetherJuiceFluidType.java` |
| 既有重构 | 注册、流体和运行时守卫已拆开，配方/战利品资源保持独立。 |

### Nautilus

| 模块 | 文件 |
| --- | --- |
| 核心实体 | `projects/ports/nautilus-equivalence/src/main/java/com/blackgear/vanillabackport/common/level/entity/mob/animal/nautilus/AbstractNautilus.java`、`Nautilus.java`、`ZombieNautilus.java` |
| AI | `projects/ports/nautilus-equivalence/src/main/java/com/blackgear/vanillabackport/common/level/entity/ai/behavior/ChargeAttack.java`、`NautilusAi.java`、`ZombieNautilusAi.java` |
| 客户端模型/渲染 | `projects/ports/nautilus-equivalence/src/main/java/com/blackgear/vanillabackport/client/level/model/entity/nautilus/NautilusModel.java`、`NautilusRenderer.java`、`ZombieNautilusRenderer.java` |
| 交互界面 | `projects/ports/nautilus-equivalence/src/main/java/com/blackgear/vanillabackport/common/level/inventory/NautilusInventoryMenu.java`、`client/level/gui/inventory/NautilusInventoryScreen.java` |
| 既有重构 | 核心实体、AI、客户端模型和界面分层；别名适配器单独维护。 |

### Tom’s Storage

| 模块 | 文件 |
| --- | --- |
| 模组入口/配置 | `projects/ports/toms-storage-neoforge-1.21.1-perf-port/Fabric/src/main/java/com/tom/storagemod/StorageMod.java`、`Config.java`、`StorageModComponents.java` |
| 方块实体 | `projects/ports/toms-storage-neoforge-1.21.1-perf-port/Fabric/src/main/java/com/tom/storagemod/block/entity/OpenCrateBlockEntity.java`、`PaintedBlockEntity.java` |
| 存储与过滤 | `projects/ports/toms-storage-neoforge-1.21.1-perf-port/Fabric/src/main/java/com/tom/storagemod/inventory/BlockFilterComponent.java`、`InventoryChangeTracker.java`、`InventorySlot.java` |
| 客户端显示 | `projects/ports/toms-storage-neoforge-1.21.1-perf-port/Fabric/src/main/java/com/tom/storagemod/client/BakedPaintedModel.java` |
| 既有重构 | 存储语义、容器变化追踪、过滤器和客户端显示已分层；存档物品恢复由 OTA 账本负责。 |

### TrueUUID

| 模块 | 文件 |
| --- | --- |
| Common API | `projects/ports/trueuuid-login-proxy-fix/platform/common/src/main/java/cn/alini/trueuuid/api/TrueuuidApi.java` |
| Fabric 登录 | `projects/ports/trueuuid-login-proxy-fix/platform/fabric/common/src/main/java/cn/alini/trueuuid/fabric/login/FabricLoginTransaction.java`、`FabricSessionCheck.java`、`MigrationCoordinator.java` |
| Fabric 认证来源 | `projects/ports/trueuuid-login-proxy-fix/platform/fabric/common/src/main/java/cn/alini/trueuuid/fabric/login/FabricAuthenticationSource.java`、`FabricVerifiedProfiles.java` |
| Forge 服务端 | `projects/ports/trueuuid-login-proxy-fix/platform/forge/1.20.1/src/main/java/cn/alini/trueuuid/server/AuthDecider.java`、`AccountStatusTracker.java`、`mixin/server/ServerLoginMixin.java` |
| 既有重构 | 正版会话、离线回退、UUID 迁移和代理网络策略已分层；协议升级必须双端同步。 |

### XiyusLogin

| 模块 | 文件 |
| --- | --- |
| 模组入口 | `projects/ports/xiyuslogin-migration/src/main/java/org/xiyu/yee/xiyuslogin/Xiyuslogin.java` |
| 认证与冻结 | `projects/ports/xiyuslogin-migration/src/main/java/org/xiyu/yee/xiyuslogin/manager/AuthManager.java`、`FreezeManager.java` |
| 玩家数据 | `projects/ports/xiyuslogin-migration/src/main/java/org/xiyu/yee/xiyuslogin/data/PlayerDataManager.java` |
| 命令 | `projects/ports/xiyuslogin-migration/src/main/java/org/xiyu/yee/xiyuslogin/command/AuthCommands.java`、`AdminCommands.java` |
| 配置与事件 | `projects/ports/xiyuslogin-migration/src/main/java/org/xiyu/yee/xiyuslogin/config/XiyusLoginConfig.java`、`event/PlayerEventHandler.java`、`event/ServerEventHandler.java` |
| 既有重构 | EasyAuth 迁移、TrueUUID 自动认证和单人世界策略已拆分；密码登录仍保留。 |

### Hardcore Revival death-message fix

| 模块 | 文件 |
| --- | --- |
| 模组入口 | `outputs/projects/hardcore-revival-death-message-fix-neoforge/src/main/java/dev/migration/hardcore_revival_death_fix/HardcoreRevivalDeathFix.java` |
| 兼容注入 | `outputs/projects/hardcore-revival-death-message-fix-neoforge/src/main/java/dev/migration/hardcore_revival_death_fix/mixin/HardcoreRevivalManagerMixin.java` |
| 注入声明 | `outputs/projects/hardcore-revival-death-message-fix-neoforge/src/main/resources/hardcore_revival_death_fix.mixins.json` |
| 模组元数据 | `outputs/projects/hardcore-revival-death-message-fix-neoforge/src/main/resources/META-INF/neoforge.mods.toml` |
| 构建/验证 | `outputs/projects/hardcore-revival-death-message-fix-neoforge/build.gradle`、`outputs/tools/test_hardcore_revival_death_message_fix.py` |
| 既有重构 | 将 Hardcore Revival 的“可救援倒地”和“真正死亡”分成两种可见性语义；倒地不再冒充死亡，超时死亡仍显示；MineAstr 保持原样，仅在真正死亡事件上报 `player_death`。 |

## 数据与脚本入口文件

| 工作域 | 入口文件 |
| --- | --- |
| 世界转换 | `outputs/tools/convert_world_nbt.py`、`outputs/tools/convert_create_saveddata.py`、`outputs/tools/prepare_fast_migration.py` |
| 物品/储存 OTA | `outputs/tools/create_storage_object_ota.py`、`outputs/tools/audit_item_migration_three_way.py` |
| 保护区地形 | `outputs/tools/protected_zone_terrain_ota.py`、`outputs/tools/protected_zone_entity_ota.py`、`outputs/tools/audit_protected_zone_entity_poi_gate.py` |
| 世界生成/高度 | `outputs/tools/audit_terrain_biome_ota_inputs.py`、`outputs/tools/audit_protected_zone_target1211.py`、`outputs/tools/validate_worldgen_height_overlay.py` |
| 客户端地图 | `outputs/tools/convert_journeymap_to_xaero.py`、`outputs/tools/import_mechanomania_attempt13_to_prism.ps1` |
| 启动门禁 | `outputs/tools/run_mechanomania_startup_gate.py`、`outputs/tools/preflight_candidate14_release_gate.py`、`outputs/tools/run_mechanomania_startup_gate_attempt12.py` |
| 仓库维护 | `tools/repository/check_repository.py`、`tools/repository/refresh_repository_manifest.py`、`tools/repository/sanitize_snapshot.py`、`outputs/tools/build_collaboration_repo.py` |

## 维护规则

- 文档中引用的每个模块都必须至少有一个具体文件入口。
- 文件重命名或模块拆分时，先更新本文，再更新 `MODULE-INTERNAL-REFACTOR-MAP.md` 的抽象职责。
- 构建产物、运行时 JAR、世界和玩家数据不作为源码入口写入本文，只通过 `artifacts/` 索引引用。
