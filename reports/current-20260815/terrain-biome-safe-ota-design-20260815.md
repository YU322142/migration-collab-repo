# 受保护区地形与生物群系安全 OTA 方案

> **已被后续授权部分取代。** 用户已在 2026-08-15 明确授权：保护区内已生成的 terrain/biome
> 可以直接由 V 覆盖。本文件原有的 `C == B ? V : C` 规则只继续适用于保护区外及过渡带。
> 后续唯一权威流程见 `outputs/MASTER-TERRAIN-BIOME-OTA-RUNBOOK-20260815.md`；不得仅凭本文件执行生产操作。

日期：2026-08-15  
状态：`SUPERSEDED_FOR_PROTECTED_ZONE_DIRECT_REPLACEMENT`  
作用域：主世界 `x=10192, z=-1574`，核心半径 `1000` 格；实际冻结/修复半径 `1536` 格。

## 先给结论

不能把一批新的 `.mca` 文件直接覆盖到已经公测的服务器。那会把同一 region
里的玩家建筑、方块实体、实体、POI、计划刻与近期世界变化一并回滚。

安全 OTA 必须是三方合并：

- `B`：这些区块第一次被错误生成时的精确基线（同一整合包版本、模组、配置、
  seed 与生成顺序），或者公测前的停服快照；
- `C`：远端服务器停服后取得的当前快照；
- `V`：使用受审计的原版兼容生成器、同一 seed 生成的目标地形与生物群系。

逐坐标规则是：`C == B` 才允许用 `V` 替换；只要 `C != B`，默认认为它是玩家或
运行期状态，保留 `C`。冲突策略固定为“公测服务器当前状态优先”。

如果拿不到精确的 `B`，已经生成的区块无法自动判断“这是 Tectonic 自然生成的
石头”还是“玩家后来放置的石头”。这种情况下不存在既恢复全部原版地形、又
保证不误删玩家改动的无损算法；OTA 只能修复未来生成规则、填充仍未生成的空槽，
并把已生成区块列入人工裁决清单。

## 已核实的本地事实

- 原始迁移基线在该区域没有历史 terrain chunk；因此这里的“保持原样”不是恢复
  一份历史 MCA，而是按原服务器 seed `-794095451117350581` 确定性生成原版兼容
  地形与原版 biome source。
- 正式选择规则按离散 Minecraft 方块计算：只要一个区块的 `16×16` 闭合整数方块
  坐标中至少有一个点落在圆内或圆周上，就必须纳入。不能只判断区块中心。
- 核心半径 `1000` 与圆相交的区块精确为 `12,500` 个；半径 `1536` 的冻结圆精确为
  `29,305` 个区块、涉及 `40` 个 terrain region，并完整覆盖全部核心区块。相较旧的
  “区块中心落圆内”口径，新增 `355` 个边缘区块。
- 当前本机最终服务端副本中，这 `29,305` 个 terrain/entity/POI 槽位仍全部为空。
  这说明本机最终包没有覆盖或预生成该区域；用户看到的错误地形应在另一台已经
  公测、并实际加载过该坐标的服务器上确认。
- 当前本机最终服务端已经合入地形隔离蓝图中的全部 `data/**` 文件，`206` 个数据
  文件无缺失、无哈希不一致（蓝图清单另含 `pack.mcmeta` 与 `README.md`，合并到
  KubeJS tree 时本来就不复制）。它把主世界恢复为 384 高度的
  `minecraft:overworld`，把 544 高度的 Tectonic 放到
  `mechanomania_frontier:frontier`。
- 旧主世界的完整生成前沿共有 `21,018` 条边，`18,120` 个边界区块全部没有
  `blending_data`；Tectonic 与原版高度相差 `160`。因此不能在同一主世界里简单地
  让圆外继续 Tectonic，并承诺边界无断崖。
- 旧的 `current-final-protected-zone-audit-20260815.json` 把源世界
  DataVersion `4671` 写死，因此在目标 1.21.1 / DataVersion `3955` 世界上结果为
  `BLOCKED`；它只能作为历史诊断，不能作为 PASS 证据。正式本地空槽证据改用
  `current-final-protected-zone-target1211-audit-20260815.json`。

## OTA 输入门禁

实际制作补丁前必须取得以下四组只读输入，并全部锁定 SHA-256：

1. `C-current`：远端正式服务器完全停服后的世界快照。必须包含 `world/region`、
   `world/entities`、`world/poi`、`level.dat`，以及最终模组/KubeJS/config 清单。
2. `B-bad-base`：错误生成器的精确基线。首选公测前快照；次选用产生这些区块的
   **每一个历史发布版本**分别重生成，并逐区块证明与当前未改动部分一致。仅凭
   seed 或当前最新版整合包不能替代这个证明。
3. `V-vanilla-reference`：在 D 盘隔离环境中，以同 seed、NeoForge 1.21.1、
   `backport-1.5.jar` 和受审计的原版生成闭包生成半径 1536。禁止加载 Tectonic、
   Mechanomania biome modifier、结构注入或其他世界生成模组。
4. `W-worldgen-overlay`：主世界固定为原版 384 高度、原版 multi-noise biome
   source；Tectonic 仅存在于 `mechanomania_frontier:frontier`。如果要求连矿物、
   植被与结构装饰都与原版一致，还必须把所有全局 biome modifier/structure
   injection 限定到 frontier，不能只改 noise settings。

任一输入 seed、维度、DataVersion、注册表闭包或目标圆区不一致，立即
`BLOCKED`，不得尝试“尽量合并”。

## 三方合并规则

| 数据域 | 默认规则 |
|---|---|
| `sections[*].block_states` | 逐方块坐标比较 B/C/V。C 等于 B 时写 V；C 不等于 B 时保留 C。 |
| `sections[*].biomes` | 逐 4×4×4 biome cell 比较 B/C/V，采用同一规则；不能整段覆盖 section。 |
| `block_entities` | 当前 C 优先。即使方块状态没变，只要 BE NBT 与 B 不同，也保留当前方块和 BE；新增/删除同样视为玩家状态。 |
| `entities/*.mca` | OTA 不写入，逐字节保持 C。应用前后哈希必须一致。 |
| `poi/*.mca` | 不可整文件覆盖。保留与最终方块仍匹配的当前 POI 及 `free_tickets`；仅在未改动坐标导入 V 的 POI；悬空或类型不符的记录阻塞人工审查。 |
| `structures.starts/References` | 只有在整个 structure start 与引用闭包都位于修复范围、且相关方块未被玩家修改时才导入 V；跨边界或已有改动则保持 C/跳过并报告。 |
| `block_ticks` / `fluid_ticks` / `PostProcessing` | 按坐标三方合并。玩家保留坐标使用 C；被替换坐标使用 V；失去对应方块的刻不得保留。 |
| `Heightmaps` | 不能复制 B、C 或 V；必须用最终合并后的方块和最终模组注册表重新计算。 |
| `BlockLight` / `SkyLight` / `isLightOn` | 受影响 section 标记为待重照明；只允许重算光照，不允许回退 chunk Status 或重新跑地形/装饰阶段。 |
| `Status`、`LastUpdate`、`InhabitedTime`、Forge attachments/capabilities | 保留 C；不得用 V 回滚运行期状态。 |

玩家保护掩码至少包含：

- 所有 `C != B` 的方块坐标；
- 所有新增、删除或 NBT 改变的方块实体坐标；
- 多方块结构的完整闭包（门、床、双箱、Create 网络/储罐/保险柜等）；
- 当前实体 AABB 及安全余量，尤其是村民、载具、画、矿车、Create contraption；
- 当前 POI、计划刻、流体刻涉及的坐标。

如果目标 V 地形会把保留实体埋入实体方块、切断多方块结构、使方块实体对应的
方块消失，或者在玩家建筑中产生大量原版地形残片，该区块不能静默自动通过；
应保留当前区块或进入人工合并。

## 精确区块 CAS 与 region 提交

补丁以 chunk slot 为最小语义单位，不以整个 region 为替换单位：

1. 停服后先读取所有目标 `region/entities/poi` MCA 的文件 SHA-256、每个 slot 的
   原始 record SHA-256、解压 NBT 语义哈希与时间戳表；生成 `preflight.json`。
2. 先在旁路目录构造全部新的 region 文件。每个新文件以 C 为底，只替换计划中
   已通过三方门禁的 terrain slot；实体文件不生成写入项，POI 仅做语义级 patch。
3. 对旁路结果重新解析全部 MCA allocation、NBT、坐标、DataVersion、palette、
   BE/POI/structure 引用、光照与 heightmap；生成预期 post SHA-256。
4. 正式提交前再次读取生产文件。文件哈希和每个目标 slot 哈希必须仍等于
   preflight；任一个不一致则全局拒绝提交。
5. 所有新 region 都准备并验证完成后才提交。每个文件使用同目录临时文件、
   flush/fsync 与原子 rename；维护 commit journal。中途失败时按 journal 将已提交
   文件恢复到 preimage。
6. 不修改 `level.dat`、玩家数据、实体 MCA、服务器端口/RCON/query。世界生成规则
   通过单独的 KubeJS/data OTA 安装，并有独立 CAS。

不要在 MCA 内原地改 sector；不要先覆盖 region 再尝试恢复实体或 BE。

## 幂等与回滚

- Apply：当前哈希等于 `pre` 才应用；等于 `post` 视为已经应用；其他值拒绝。
- Rollback：当前哈希等于 `post` 才恢复；等于 `pre` 视为已经回滚；其他值拒绝。
- 回滚包只需保存被修改的 MCA preimage、被修改的 KubeJS/data 文件和 manifest，
  不需要再复制一份 400 GB 世界；但正式操作前仍建议使用文件系统/虚拟机快照。
- 第一次维护启动必须在快照副本验证。生产首次启动后如果服务器重照明或刷新 POI，
  要记录新增变化；在玩家重新进入前发现异常就立即回滚。

## 未来生成规则

最安全且与既有审计一致的策略是：

- 主世界永久使用原版兼容 384 高度 noise、原版 multi-noise biome source；
- 半径 1536 内所有仍为空的 slot 用 V 预生成结果填充，已有 slot按上述 CAS 合并；
- Tectonic 544 高度世界生成只在 `mechanomania_frontier:frontier`；
- 如果要求主世界连装饰也严格原版，继续隔离所有 Mechanomania 全局 biome feature、
  ore、structure modifier，改为只作用于 frontier。

若坚持“同一个 Overworld 中，半径外继续 Tectonic”，现有证据下无法保证无断层、
水体连通和 biome 连续，不能作为无损 OTA 承诺。

## 明确无法无损自动 OTA 的情况

以下任一情况只能保留当前状态、人工选区处理或接受数据损失：

- 没有公测前快照，也无法用完全相同的历史生成栈重建 B；
- 同一区块曾由多个不同整合包版本分阶段生成，且没有逐区块来源记录；
- 玩家改动与自然方块在 B/C 中语义相同，或自然生长/流体/爆炸与玩家改动不可区分；
- V 地形与玩家建筑、地下工程、方块实体、实体或 POI 大范围重叠；
- 结构 start/reference 跨出修复闭包，或者结构区块已有玩家改动；
- 未知/缺失模组导致 B、C 或 V 中的方块状态、BE、实体、biome 无法反序列化；
- MCA 损坏、external `.mcc`、重复坐标、非 full chunk、DataVersion 无受审升级路径；
- 要求同时在同一 Overworld 保留 Tectonic 544 新地形和原版 384 地形并做到无缝；
- 要求主世界装饰逐字节原版，同时又允许整合包的全局 biome/structure 注入继续作用。

## 实际交付物

取得远端停服快照后，最终 OTA 应只包含：

- `manifest.json`：seed、维度、圆区、输入/输出 SHA、版本与策略；
- `preflight-report.json/.md`：每个 chunk 的分类与冲突；
- `patch/region` 与必要的 `patch/poi`：只包含通过 CAS 的 region 新文件；
- `worldgen-overlay/`：主世界原版 + frontier Tectonic 的固定数据闭包；
- `apply.ps1`、`verify.ps1`、`rollback.ps1`：全程 fail-closed；
- `receipts/`：提交 journal、pre/post 哈希、幂等状态与人工冲突清单。

远端 `C-current` 没有到手之前，可以完成生成器固定和工具准备，但不能诚实地生成
“保留所有公测建筑”的最终世界补丁。
