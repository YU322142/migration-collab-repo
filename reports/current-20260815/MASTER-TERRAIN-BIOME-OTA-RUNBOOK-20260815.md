# 地形、生物群系、建筑高度与远端新地形 OTA 总执行手册

日期：2026-08-15  
状态：`READY_FOR_REMOTE_STOPPED_VERIFY_AND_APPLY_LATEST_C_LOCKED`  
用途：这是本任务后续执行的唯一权威流程。旧的 `vanilla-terrain-protection-runbook-20260813.md`、
`terrain-preservation-final-20260813.*` 和早期 28,950 区块口径只作为历史证据，不得单独指导生产操作。

简明且无乱码的现场操作版已迁移到 `outputs/PROTECTED-TERRAIN-OTA-OPERATOR-RUNBOOK-20260815.md`；协作与实际执行优先阅读该文件，本长文档保留完整设计历史。

## 1. 用户不可变要求

1. 主世界 `x=10192, z=-1574` 周围必须保留原版地形与原版生物群系。
2. 核心半径 `1000` 内不得生成 Tectonic、Wythers 或 Mechanomania 的地形、biome、矿物、植被、carver、结构注入。
3. 使用半径 `1536` 的冻结圈吸收跨区块结构、装饰和边界影响。
4. 保护区外冲突以当前服务器状态为准，不得覆盖玩家建设或运行期状态；保护区内普通方块改动按本次直接覆盖授权处理，重要对象另行审计。
5. 主世界建筑上限提高到上边界 `480`，最高可放置方块 Y=`479`。
6. 原版自然地形仍只生成在 Y=`-64..319`；Y=`320..479` 是建筑空气层。
7. 远离已有世界和保护区后，应能生成完整 Mechanomania/Tectonic 地形，且中间不得出现突兀断崖。
8. 最终交付必须是可 dry-run、可验证、幂等、可回滚的 OTA；禁止整世界替换。
9. 用户已明确授权：冻结圈内已经生成的地形与生物群系可以直接由 V 覆盖，不再要求用 B 保留该区域的玩家方块改动。

该授权只适用于选中的保护区 terrain/biome。圈外区块、玩家数据和 entities MCA 仍不得盲目覆盖。
方块实体、离线玩家位置、具名/驯服实体和 POI 必须先审计；能与 V 安全共存的对象可作为例外保留，
不能安全共存的对象进入明确迁移/清除清单，不得静默损坏。

## 2. 固定几何与目标版本

| 项目 | 固定值 |
|---|---|
| 维度 | `minecraft:overworld` |
| 中心 | `x=10192, z=-1574` |
| 中心区块 | `(637,-99)` |
| 核心半径 | `1000` 格 |
| 核心相交区块 | `12,500` |
| 冻结半径 | `1536` 格 |
| 冻结相交区块 | `29,305` |
| 冻结 region | `40` |
| seed | `-794095451117350581` |
| 目标 Minecraft | `1.21.1` |
| 目标 DataVersion | `3955` |
| 维度 min_y | `-64` |
| 维度 height / logical_height | `544` |
| 自然地形 noise height | `384` |
| 最高建筑 Y | `479` |

区块选择必须按离散方块坐标计算：一个区块的 `16×16` 整数方块坐标中，只要至少一个点位于
圆内或圆周上，就纳入。禁止恢复到“区块中心落圆内”的 28,950 口径。

## 3. 四个数据角色

### C：当前公测服务器

文件：`D:\Down\mechanomania-matched-runtime-attempt13-2.zip`  
SHA-256：`ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92`  
大小：`7,936,970,883` bytes  
归档测试：NanaZip `Everything is Ok`

用户已于 2026-08-15 明确确认该文件就是最新服务端文件。它现在是正式的权威 `C`，不再等待额外的 C2。
外层锁定清单：`outputs/protected-terrain-ota-latest-c-lock-20260815.json`。现有早期 plan 未内嵌 ZIP SHA，
因此由该清单绑定 C/V/两个事务包；真正写入前仍由逐文件、逐 slot、逐对象 CAS 校验远端停服前像。

这是后续冲突判定与最终 OTA 的当前状态 `C`。只读中央目录审计已确认：

- 冻结圈 terrain 目标槽已占用 `12,370`；
- entities 目标槽已占用 `89`；
- POI 目标槽已占用 `9`；
- mods 与 KubeJS 闭包未因归档变小而缺失；
- 活动 world 没有相对旧包缺失文件，反而增加约 153 MB。

### R：较早的完整服务器归档

文件：`D:\Down\mechanomania-matched-runtime-attempt13-20260814-ota-final-20260815.zip`  
SHA-256：`92C719AF5A64C775992784326DC73563F0E3AEF6C6A757C9E1E22809497818B4`  
大小：`14,218,857,050` bytes

该归档必须保留。它包含已被远端 SimpleBackups 轮换删除的全量备份候选：

```text
simplebackups/world/world_2026-08-14_18-30-40.zip
6,498,782,005 bytes
```

R 不是自动视为 B；必须审计备份时间、目标区块是否存在、worldgen 闭包及生成阶段。

### B：错误生成时的自然基线

B 用于区分自然生成与玩家修改。优先级：

1. 若 R 中的全量备份已经包含目标区块，并且生成时的 mods/config/KubeJS 与 C 精确一致，则可作为 B 候选；
2. 若该备份中目标区块仍为空，则使用 C 的精确历史 worldgen 闭包，在隔离服务器按同 seed 重生成 B；
3. B 必须先在一批无玩家改动的 C 区块上证明方块、biome、结构及 BE 自然结果一致；无法证明时，已生成区块自动修复保持 `BLOCKED`。

用户授权后，B 不再阻塞**保护区 terrain/biome 直接替换**。B 仍用于审计、解释历史差异、处理保护区外
可能需要保留玩家修改的地形，以及验证远端过渡生成器。

### V：目标原版参考世界

V 使用同 seed 和目标 1.21.1 注册表生成：

- 维度高度 544，原版自然地形高度 384；
- 保护区使用严格原版 biome 定义、feature、ore、carver 和结构闭包；
- 禁止加载 Tectonic、Wythers、Mechanomania 全局世界生成注入；
- 生成全部 29,305 个冻结区块；
- 输出 terrain/entities/POI、逐 slot SHA、语义哈希和完整注册表清单。

V 已于 2026-08-15 完成并冻结，后续不得重新生成后沿用旧清单：

- 严格参考世界：`D:\Trans\migration-audit-work\vanilla-reference-v-20260815\strict-reference-world\vanilla-reference-v`
- 精确 `29,305` 个 terrain chunk、`40` 个 region，missing=`0`、extra=`0`
- DataVersion=`3955`、Status=`minecraft:full`、seed 与本手册一致
- 维度高度 `544`，Y=`320..479` 无自然方块
- 非 `minecraft` biome/block/structure=`0`，external `.mcc`=`0`
- 最终门禁 `19/19 PASS`
- `final-verification-report.json` SHA-256：`5507B0D06A0CDD3D9E4D362477A840D8EE4C20656265886F7AAA2C91B60BA05E`
- `strict-world-manifest.json` SHA-256：`4BD4883295C8E0EFDF584A81AEB4FE19DAAA0EA0AE0B4B3BC3455E9768B2FCB1`

## 4. 为什么新 ZIP 变小

当前活动世界没有缩水。SimpleBackups 配置为：

```toml
backupType = "MODIFIED_SINCE_LAST"
fullBackupTimer = 525960
backupsToKeep = 5
timer = 240
```

第五个增量备份出现后，6.499 GB 的全量基线被轮换删除，因此新外层 ZIP 小了约 6.28 GB。
剩余五个 116–149 MB 文件是增量备份，不应视为独立可恢复的完整链。

在地形 OTA 完成前：

- 不得删除 R；
- 不得删除 C；
- 不得把新 ZIP 变小理解为活动世界丢失；
- 服务器备份策略后续改为可靠的定期全量备份，不能继续一年一次全量、只留五个增量。

## 5. 未来同主世界生成策略

冻结掩码 `F` 不是单一圆，而是：

```text
F = 当前公测服所有已存在区块 ∪ 指定的 29,305 个原版保护区块
```

对任意尚未生成位置，计算到 F 的距离：

| 距离 | 生成规则 |
|---|---|
| F 内且位于保护圈 | 已生成与空缺的目标 chunk slot 均写入 V；重要对象按例外清单处置 |
| F 内但位于保护圈外 | 已有区块保持 C |
| `0..1024` 格 | 原版延续区，确保旧边界自然延伸 |
| `1024..4096` 格 | 密度、气候、biome、carver、feature、ore、structure 平滑过渡 |
| `>=4096` 格 | 完整 Mechanomania/Tectonic 地形 |

过渡必须在噪声采样/方块级执行，不能按整个区块二选一。初始宽度为 4096；高度、水体、biome、
结构引用门禁失败时只允许扩大。

为避免原版保护区仍被全局 biome JSON 改写：

1. 恢复 `minecraft:*` biome 为目标原版定义；
2. 将远端改造后的 biome/feature 集合放入独立 namespace；
3. 由距离感知生成器在过渡区和远端选择对应 biome；
4. 所有结构与矿物注入必须带同一距离/biome 门禁。

该实现预计需要 BOTH-side NeoForge 兼容模组，因为自定义 worldgen codec/registry 需要客户端参与握手。
测试期间禁用 MCModSync；最终客户端发布时再恢复 MCModSync，并确保目录不会降级该兼容模组。

## 6. 三方合并算法

保护区外或需要保留玩家建设的位置，默认规则仍是：

```text
C == B ? V : C
```

- `C == B`：可证明仍是未修改的错误自然生成，替换为 V；
- `C != B`：视为玩家或运行期状态，保留 C；
- 没有可信 B：已生成区块不得自动恢复，只修空槽和未来生成规则。

保护区内采用授权后的直接规则：

```text
terrain/biome/structure/ticks/heightmap/light := V
保护区实体 := 以 C 为权威载荷，按 V 碰撞结果做确定性对象级迁移
圈外 chunk slot := C（字节不变）
```

实现时必须按 chunk slot 在旁路重建 MCA，不能把 V 的整份 region 文件覆盖过去。当前 C 中保护区已有
`12,370` 个 terrain slot；这些与其余空槽一起都以 V 为目标。保护区内普通玩家方块可能被覆盖，
这是本次授权的预期效果；重要 BE、玩家和具名/驯服实体仍先做安全审计。

数据域规则：

- block states：逐方块三方比较；
- biomes：逐 4×4×4 cell 三方比较；
- block entities：新增、删除或 NBT 改变时保留 C，并保留支撑方块；
- entities MCA：圈外 slot 与未变对象保持 C；保护区内 `198` 个 C 实体必须全部保留载荷。与 V 冲突的对象仅允许按签名迁移账本修改位置/必要运动字段；禁止静默删除；
- POI：按坐标和类型语义合并；
- structures：只有完整 start/reference 闭包可安全替换；
- ticks/PostProcessing：按最终方块坐标合并；
- Heightmaps：从最终方块重算；
- lighting：只重照明，不回退 chunk Status，不重跑地形或装饰；
- LastUpdate/InhabitedTime/attachments/capabilities：保留 C。

## 7. 固定执行顺序

### 阶段 A：输入锁定

1. 保存 C/R 的 SHA、大小、文件清单和 ZIP CRC 结果；
2. 只读检查 nested full backup；
3. 从 C 锁定 mods/config/KubeJS/datapack/worldgen 闭包；
4. 创建工作目录时只在 D 盘使用精确子目录，不复制无关世界。

### 阶段 B：建立 B（不再阻塞保护区直接替换）

1. 判断 R 中全量备份是否已含目标区块；
2. 若为空，用 C 的精确历史生成栈建立隔离 B；
3. 只生成 C 中已经占用的目标区块及必要结构闭包；
4. 用未修改样本验证确定性；不一致则自动合并 BLOCKED。

### 阶段 C：建立 V

1. 使用同 seed、544 维度高度、384 原版 noise；
2. 生成严格离散选择的 29,305 个区块；
3. 验证 DataVersion=3955、无 external `.mcc`、无计划外区块；
4. 生成冻结 manifest。

### 阶段 D：分类与构建

1. 分类为空槽、保护区直接替换、重要对象例外、圈外保持、解析阻断；
2. 生成只读 preflight 报告；
3. 在旁路目录以 C 为底重建目标 MCA；
4. terrain/POI 包不写 entities；实体迁移由独立对象级 CAS 包执行，并与 terrain 包绑定同一 C/V/计划哈希；
5. 对所有结果重新解析并生成 post SHA。

### 阶段 E：副本动态验证

必须在独立副本完成：

- 两轮完整启动、保存、停止和重启；
- Y=479 可建筑、Y=480 拒绝；
- 原版核心的地形、biome、植被、矿物、结构与 V 一致；
- 过渡带高度跳变、水体断连、悬空流体、结构断链均为 0；
- 远端完整 Tectonic 生成成功；
- 玩家建筑、BE、entities、POI、Create 网络无回滚；
- apply/verify/rollback 均通过 CAS 负例测试。

当前已完成第一轮基础动态验证：

- D 盘测试根：`D:\Trans\migration-audit-work\protected-terrain-ota-test-server-20260815\mechanomania-matched-runtime-attempt13-20260814`
- terrain/POI bundle 在副本上 preverify、apply、postverify 均 PASS；原始 C ZIP 未修改
- NeoForge 21.1.241 / Java 21 / `-Xmx8G`，仅监听测试端口 `12351`
- 2026-08-15 19:36:21 到达 `Done (6.814s)!`
- Y=`479` 放置成功，Y=`480` 被正确拒绝
- MineAstr 0.6.27 成功连接并完成绑定同步
- 2026-08-15 19:38:13 干净停止，当前无该测试 Java 进程

第一轮同时发现两个必须先解决的 P0：

1. 保护区 `198` 个 C 实体中，`51` 个与 V 实体方块发生硬碰撞、`21` 个需复核；必须先完成确定性实体迁移包。其中 `15` 个掉落物实体携带共 `27` 件物品，载荷必须逐字节保留。
2. 旧 384 高度区块的 Heightmaps 是 `37` longs，而高度 544 运行时要求 `43` longs。当前游戏会丢弃旧高度图并内存重算，但警告会反复出现。必须用严格的 9-bit→10-bit 非跨 long 语义等价转换兼容层处理，不能伪造高度。

在这两个 P0 完成前，第一轮基础启动 PASS 不等于生产 GO，也不得加载保护区实体密集坐标。

### 阶段 F：生产 OTA

1. 正式服停服并取得最终 preimage；
2. 再次检查文件与 slot 哈希仍等于 preflight；
3. 原子替换经过验证的 MCA 与 worldgen 文件；
4. 首次维护启动不允许玩家进入；
5. verify PASS 后开放；失败立即按 journal 回滚。

## 8. 明确禁止

- 禁止整份 world 或整个 region 盲目覆盖；
- 禁止从运行中的服务器复制 MCA；
- 禁止整文件盲目覆盖 entities MCA；保护区冲突实体只允许由已签名的对象级迁移账本修改位置/必要运动字段，所有载荷与其余 NBT 必须保持 C；
- 保护区外禁止用 V 覆盖玩家修改坐标；保护区内普通玩家方块按本次授权可覆盖，但玩家本体、具名/驯服实体和重要 BE 必须先审计并形成明确处置清单；
- 禁止只改 biome source 却保留全局 Wythers/Mechanomania biome 覆盖；
- 禁止只改 `height=544` 就让 Tectonic 在旧边界直接生成；
- 禁止使用错误路径 `data/minecraft/worldgen/dimension_type/overworld.json` 作为有效高度配置；
- 缺少 B 时，不得宣称保护区外已生成区块可以无损自动恢复；保护区内按本次明确授权直接使用 V，不作“保留普通玩家方块”的承诺；
- 禁止删除旧 14.2 GB 归档，直到 B/V/OTA/回滚全部验收完成；
- 禁止把服务端世界补丁交给 MCModSync；MCModSync 只负责最终客户端文件分发。

## 9. 当前检查点

- [x] 用户要求和严格几何已锁定；
- [x] C 与 R 的外层 SHA 已锁定；
- [x] C ZIP 完整性 PASS；
- [x] C 冻结圈占用概况已取得；
- [x] 新 ZIP 变小的原因已确认；
- [x] 用户已授权保护区 terrain/biome 直接覆盖；
- [x] C 保护区重要对象只读审计完成：玩家当前位置/出生点 `0`，block entity `1,333`，实体 `198`，POI `40`，需关注区块 `185`；
- [x] 对象处置账本完成：`1,333` 个 BE 全部可随 V 替换，真实非空库存/液体均为 `0`，需搬运 BE 为 `0`；
- [x] 槽位级 OTA/回滚工具完成并通过 `13/13` 测试；选中槽取 V、圈外原始记录取 C、entities 只做字节守卫；
- [x] V 严格参考世界完成：`29,305/29,305`、40 regions、最终 `19/19 PASS`；
- [x] terrain/POI 正式 bundle 已构建并独立复核：69 个 payload 文件，状态 `READY_FOR_STOPPED_SERVER_APPLY`；
- [x] terrain/POI bundle 已仅应用到 D 盘测试副本，preverify/apply/postverify 全 PASS；
- [x] 有效 544 高度 overlay 已构建并在副本验证：Y=`479` 成功、Y=`480` 拒绝；
- [x] 第一轮测试副本完整启动到 `Done (6.814s)`，MineAstr 0.6.27 实际连接，随后干净停止；
- [x] POI 门禁完成：V 的 180 个占用槽/345 条记录与 V 方块一致，C 的旧 40 条 POI 全部应随 donor selected slot 替换；
- [x] 实体碰撞门禁完成：198 个实体中 126 PASS、21 REVIEW、51 COLLISION；因此“entities 全字节不动”策略已明确否决；
- [ ] nested full backup 内容与时间点审计；
- [ ] B 的确定性重建与样本验证；
- [x] V 的 29,305 区块生成；
- [x] 保护区 V 直接替换分类与重要对象例外清单；
- [ ] 保护区外/过渡带 B/C/V 三方分类（不阻塞保护区恢复）；
- [ ] 距离感知过渡模组；
- [x] terrain/POI 静态 OTA 与回滚包；
- [x] 实体保留迁移 OTA 与回滚包（D 克隆已应用并后验 40/40）；
- [x] 384→544 Heightmap 兼容模组及双构建门禁；
- [x] 副本第二轮动态验证（实体迁移、旧区块 Heightmap、保护区代表坐标）；
- [ ] 生产应用。

当前下一步：停止远端服务端并对其受影响文件运行 terrain/POI 与 entity 两个事务包的 prestate/CAS 校验；
若与已锁定的最新 C 完全匹配，直接应用现有事务包，无需重新规划。D 克隆已经完成动态稳定 V 语义后验，
29,305/29,305 区块一致。若远端前像不匹配则必须在零写入状态中止并重建；首次维护启动和远端语义后验通过前仍不开放玩家。

重要对象审计证据：`outputs/protected-zone-important-object-audit-20260815.json`，SHA-256
`3940CE6CB60FAC9DD37890C3AA74C47A8DBB4CCD7923E3657E0E8590CFADA2A7`。

对象处置账本：`outputs/protected-zone-object-disposition-20260815.json`，SHA-256
`97E7B0AEF2460B632FDABA774498495F8AB691CF3D4CB428973D6EDDF70039C3`。

槽位级工具：`outputs/tools/protected_zone_terrain_ota.py`，SHA-256
`2716F2B4A345EC0FE32C7AFCCB5649741ADC1627C204013457B4C4CDA02A2D8C`。

正式 terrain/POI bundle：`D:\Trans\migration-audit-work\protected-terrain-ota-20260815\bundle`；
plan SHA-256 `483DD2073E7C31691CF15E1BA507556288FF37A11523D3383F6BE34C09C8096E`，
build report SHA-256 `02EFC30B640FF1C54EF44D0AEC993825BF41803838AD62A07DC5694F3F4911FD`，
verify report SHA-256 `8ED6E0765090C74A7926301D11CDBC32FB2AC7284A4789594F03B00630E48676`。

V 已完成。Chunky 先生成 `29,861` 个确定性超集区块，再在不可变原始输出之外裁成严格 `29,305` 个目标区块；
多出的 `556` 个槽未进入 OTA。严格世界审计 SHA-256：
`854A2EFFFCF2EDEE7C126FBFD897A3B117FDCE9B22EBA49846E092CFDDC18D6B`。

高度与远端生成附录：`outputs/WORLDGEN-HEIGHT-544-AND-FRONTIER-APPENDIX-20260815.md`。
当前高度 overlay 可发布；“同一主世界远处完整 Tectonic 且无断崖”仍为 `BLOCKED_FAIL_CLOSED`，
未完成距离感知 BOTH-side 生成模组前只允许使用独立 `mechanomania_frontier:frontier` 作为安全 fallback。

动态复测证据：`outputs/protected-terrain-dynamic-clean-run-20260815.json`。
单实例启动达到 `Done (4.589s)`，Heightmap `expected: 43, got: 37` 新警告为 0，
MineAstr 0.6.27 连接成功，MCModSync 未加载，实体后验 40/40 PASS。
严格 terrain 字节后验因运行时正常重写 MCA 容器而不再作为启动后的最终判据。动态稳定 V 语义后验已 PASS：29,305/29,305 选中区块一致，Heightmap 不一致 0，圈外 1,764 个 C 记录漂移 0。证据见 `outputs/protected-terrain-settled-v-dynamic-validation-20260815.json`。用户确认的最新 C 已锁定；远端停服前像匹配现有 CAS 时直接应用，不匹配时才重新生成事务包。
