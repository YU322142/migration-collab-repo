# 1.21.11 原版玩法迁移与已知 Bug 总账

更新时间：2026-08-13

## 结论

当前不是‘全部玩法 100% 完成’，也不是‘还有未知数量的反复淘汰’。现有证据已把问题收敛成三类：修复实现已闭环、数据安全已闭环但玩法实测未闭环、以及仍缺有界实现的未完成项。最终状态仍为 **NO-GO：等待唯一新合包的运行门禁**。

本次只汇总并锁定已有报告：没有重新扫描世界、没有启动 Java，也没有修改 source、staging 或 release。

## 数字摘要

- 1.21.1 之后的新原版 ID：50 个；49 个有功能性 backport，1 个（`minecraft:netherite_horse_armor`）当前仅安全载体。
- 最新 dry-run：112 玩家、73,117 实体、5,727 region 文件；8,705 个 Trial Spawner、211,551 条属性别名、2,278 条物品组件别名。
- dry-run 的 unsupported player/entity item、entity、equipment、attribute、gamerule、Create fluid、malformed player/region 均为 0。
- 不能把上一句写成‘全局零 blocker’：5 个源中存在的 Create schematic 外部文件尚未进入该 dry-run 目标，另有 3 个源端本来就缺失的引用必须原样记录。
- 村民基线：1,216 个村民、927 条交易、重复 UUID 0；最新多出的 23 个村民仍需最终 deep compare。

## 三类状态

| 分类 | 含义 | 数量（总账项目） |
|---|---|---:|
| `fixed`（已修） | 修复实现与定向证据已闭环；合入最终大包后仍必须做回归，不能把历史 PASS 当作新包 PASS。 | 10 |
| `data_safe_gameplay_runtime_pending`（数据安全已闭环，玩法/运行实测待闭环） | 注册/载体/转换/保护层已防止静默丢数据，但完整玩法或真实多人/音画实测尚未闭环。 | 7 |
| `unfinished`（未完成） | 尚缺可发布的有界实现、映射或幂等修复；发布门禁保持阻断。 | 3 |

## 原版玩法主项

| 主项 | 分类 | 已做到 | 还缺什么 |
|---|---|---|---|
| `vanilla.new_registry_ids` 50 个 1.21.1 后新增原版 ID | `data_safe_gameplay_runtime_pending` | 识别到 50/50 个实际出现 ID；49/50 有功能性 backport；1/50 由安全载体保活 | 最终合包注册表 dump；双轮保存重启；四个玩法簇的人工矩阵 |
| `vanilla.nautilus` Nautilus / Zombie Nautilus | `data_safe_gameplay_runtime_pending` | canonical ID 与资源存在；BODY 装备即时替换/清空/保存重启与属性生命周期通过；最新 dry-run 的实体/装备未知项为 0 | 41 个源实体逐个对账；GUI/交互/骑乘冲刺/繁殖/自然生成/僵尸骑手/掉落/发射器/剪切；声音/渲染/多人同步 |
| `vanilla.happy_ghast` Happy Ghast | `data_safe_gameplay_runtime_pending` | 兼容 JAR 已进入基线；happy_ghast_one_cm 统计 ID 已识别；存档 ID 不因缺注册表被静默丢弃 | 真实多人骑乘；相机/家锚/声音/模型/动画；运行时注册表 dump 与保存重启 |
| `vanilla.locator_bar` Locator Bar / Waypoint 显示语义 | `data_safe_gameplay_runtime_pending` | 服务端规则、属性跟踪、颜色/位置语义和保存重启已有 smoke；高权限命令树修复并真实入服 PASS | 官方数据驱动 waypoint_style_asset 与 sprites；双真实客户端、GUI scale、shader/resource pack；Geyser/Bedrock 路径与像素对比 |
| `vanilla.netherite_horse_armor` Netherite Horse Armor | `data_safe_gameplay_runtime_pending` | 源与 staging 的同一匹马/同一物品已锁定；保护载体阻止危险操作与静默吞物；稳定 owner UUID、栈哈希和路径别名已记录 | 完整物品模型/配方/属性/装备交互；两轮运行后栈与 owner 精确对账；用完整实现替换载体 |

## 已知 Bug / 数据缺口

| ID | 分类 | 当前结论 | OTA/后续修复路径 |
|---|---|---|---|
| `converter.player_attributes` | `fixed` | 7 个 player.* namespace 修正；211,551 条属性别名转换；unsupported_attributes=0 | 停服副本上执行当前幂等转换器；客户端无单独修复动作 |
| `converter.trial_spawner` | `fixed` | 8,705 个配置已结构转换；最新 dry-run malformed/unsupported region 为 0；旧 stress 报告中的 Not a map 根因已纳入转换 | 停服副本执行幂等 NBT 转换；需要客户端内容变更时再成对发版 |
| `server.recipe_book` | `data_safe_gameplay_runtime_pending` | 精确锁定 62 行/41 ID；确认是 ServerRecipeBook 原生 removed-now 自清理，不是物品/实体拒载 | 无需客户端 OTA；服务器短停运行原生 load/save，自清理必须受 exact allowlist 约束 |
| `server.map_banner` | `unfinished` | 已定位为 4 条持久化地图旗帜字段；修复边界限定为字段级，禁止删除整个地图记录 | 服务端短停执行字段级 datafix，写 ledger/sidecar；MCModSync 不能单独修复 |
| `create.fluids` | `fixed` | 744 个流体栈已审计；Create milk 规范为 minecraft:milk；两条 810 源单位按用户接受策略各转 8 mB，单条误差 +0.5 mB；unsupported_create_fluids=0 | 停服副本执行当前 Create saved-data/NBT 转换器；如 codec 改变则成对发兼容 JAR |
| `kaleidoscope.scarecrow` | `fixed` | 旧 HandItems/ArmorItems list 转 ItemStackHandler；slot-3 dragon head 与 UUID/坐标证据锁定；幂等、错误类型 fail-closed；隔离构建与单元测试通过 | 成对发布 Scarecrow compat JAR；不离线重写整个实体 |
| `waypoint.command_tree` | `fixed` | 命令参数注册完成；permission level 4 真实入服及颜色命令 PASS；服务端规则保存重启 smoke | 成对发布锁定 Waypoint JAR |
| `create.chute_unload` | `fixed` | BOTH-side unload guard 已构建并进入后续基线；旧 stress round1 已进服；该报告 NO_GO 原因是独立 TrialSpawner 错误，不是 chute guard 失效 | 成对发布 Create chute guard |
| `create.carriage_orientation` | `fixed` | 根因锁定为 case-sensitive enum fallback；转换器规范化 InitialOrientation；p0.2 BOTH-side 只读保护，双构建哈希一致；4 个 carriage 与 16 个 controls 静态对账 | 服务端先用当前转换器生成新副本，并成对发布 p0.2 guard |
| `immersive_paintings.orientation` | `fixed` | 标量旋转迁移到 VRotation；127/127 bounded attached entities retained；两轮 reload/save/stop 通过 | 成对发布 patched Immersive Paintings JAR |
| `immersive_paintings.cache` | `data_safe_gameplay_runtime_pending` | 缓存已纳入迁移白名单；权威集合记录为 87 原图 + 87 缩略图；组装脚本已有复制/完整性门禁 | 服务端短停复制权威缓存并做清单校验；客户端渲染 JAR 可成对 OTA |
| `client.resource_assets` | `fixed` | 432 条 form=2 警告有 bounded alias；5 个坏模型与 23 类贴图引用已定点处理；creaking_heart 非法 active 状态从派生包移除；dragon-tea 144 状态与 3 个 blowgun 模型闭环 | 客户端退出后由 MCModSync 更新资源 overlay JAR；不覆盖用户原资源包 ZIP |
| `server.advancement_unlocks` | `unfinished` | 已识别为玩家解锁等价问题，不与物品/区块丢失混淆；禁止删除整个 advancement/player 文件 | 服务端短停运行幂等 advancement datafix；MCModSync 不能单独修复 |
| `create.schematic_dependencies` | `unfinished` | 5 个源中存在的 schematic 已被 dry-run 定位为目标依赖缺失；另有 3 个源端本就缺失的引用被区分为 inherited state | 服务器短停复制外部 schematic 目录并锁定哈希；不通过客户端 OTA 猜测文件 |
| `cctweaked.lifecycle_guard` | `fixed` | 受限 startup/shutdown guard 已进入基线；未放宽普通 Lua 运行超时 | 成对发布受限 guard |

## 发布前硬门禁

1. **`gate.fresh_authority_conversion`**：从权威 stopped source 用当前 convert_world_nbt.py 与 convert_create_saveddata.py 重建唯一副本；转换 marker 绑定当前脚本哈希，不接受旧 marker；不从运行过的测试世界反向取数。
2. **`gate.static_ledger_and_bundle`**：新 release lock/manifests 包含所有 required guard/backport/resource artifacts；server/client side policy 与哈希完全匹配；保护载体与完整 Netherite Horse Armor 实现不得共存。
3. **`gate.two_round_runtime`**：round1 启动、OP4 真入服、关键坐标/实体/方块实体加载、save-all flush、优雅停服；round2 重启重复入服与加载；unknown registry、Invalid item、TrialSpawner Not a map、scarecrow codec、Create carriage/chute crash 为 0；recipe-book round1 精确 62/41，round2 为 0。
4. **`gate.real_client_gameplay_matrix`**：Nautilus、Happy Ghast、Locator Bar、Netherite Horse Armor 分项人工测试；两名真实客户端、重连、维度切换、不同 GUI scale；渲染/声音/交互/多人同步均留日志与截图证据。
5. **`gate.paintings_and_resources`**：Immersive Paintings cache 87 原图 + 87 缩略图；真实图片显示、方向与重启保持；审计范围内缺模型/贴图和 Render-thread ERROR/FATAL 为 0。
6. **`gate_unfinished_data_repairs`**：4 条 map banner 字段级修复完成且幂等；advancement 旧 ID 映射/waiver 完整；5 个现存 Create schematic 外部文件复制，3 个继承缺失仅记录不伪造。
7. **`gate.ota_repairability`**：每个已知问题具有稳定 ID、OTA class、回滚路径和新 release lock；客户端 JAR/overlay 可由 MCModSync 在退出后更新；服务端 JAR 和世界/player NBT 不冒充 MCModSync 热更新；任何未分类 P0/P1 错误均 NO_GO。

## OTA 边界

- 客户端模型、贴图、渲染兼容 JAR：游戏退出后可由 MCModSync 更新。
- BOTH-side 模组：客户端可由 MCModSync 更新，但服务端必须短停并同步换 JAR；必须发布新的 paired release lock。
- 世界、玩家、recipe-book、advancement、map banner、外部 schematic：必须在服务器副本执行幂等 datafix/复制并留 sidecar 与回滚；MCModSync 不能假装热修这些数据。
- 未分类 P0/P1 错误一律 NO-GO；不能靠扩大 allowlist 或删除玩家数据消音。

## 不变量

- 生产端口保持 `25566 / 25575 / 25565`，`server.properties` 不改。
- 原服务器已有地形、区块、实体、地图、物品和未知 payload 不覆盖、不重滚、不静默删除。
- 只从 stopped authority 做一次 fresh conversion；测试世界永不作为转换基线。

机器可读详情、50 个 ID 逐项状态、证据哈希、每项 OTA class 和验收条件见同名 JSON。
