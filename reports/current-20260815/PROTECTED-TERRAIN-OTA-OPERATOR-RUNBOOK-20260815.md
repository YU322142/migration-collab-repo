# 原版保护区地形 OTA 操作手册

这是后续协作时应优先阅读的简明权威流程。旧的乱码版长文档仅保留历史证据，不再作为直接操作说明。

当前状态：`READY_FOR_REMOTE_STOPPED_VERIFY_AND_APPLY_LATEST_C_LOCKED`  
生产状态：尚未写入远端；远端停服后通过两个事务包的 prestate/CAS 校验即可执行

## 固定目标

- 维度：`minecraft:overworld`
- 中心：`x=10192, z=-1574`
- 原版核心半径：`1000`，严格相交区块 `12,500`
- 冻结半径：`1536`，严格相交区块 `29,305`，涉及 `40` 个 region
- Seed：`-794095451117350581`
- Minecraft：`1.21.1`，DataVersion `3955`
- 维度高度：`min_y=-64`、`height=544`、最高可建筑 Y=`479`
- 原版自然地形仍只生成到 Y=`319`；Y=`320..479` 是建筑空气层

## 已冻结输入

- 当前公测快照 C：`D:\Down\mechanomania-matched-runtime-attempt13-2.zip`
  - SHA-256：`ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92`
  - 用户已于 2026-08-15 明确确认：这就是最新服务端文件，不再等待 C2
- 最新 C 外层锁定清单：`outputs/protected-terrain-ota-latest-c-lock-20260815.json`
- 原版严格参考 V：`D:\Trans\migration-audit-work\vanilla-reference-v-20260815\strict-reference-world\vanilla-reference-v`
- 动态稳定参考 V：`D:\Trans\migration-audit-work\vanilla-reference-v-20260815\settled-reference-world\vanilla-reference-v-settled`
- Terrain/POI bundle：`D:\Trans\migration-audit-work\protected-terrain-ota-20260815\bundle`
- Entity bundle：`D:\Trans\migration-audit-work\protected-entity-ota-20260815\bundle`
- 最新 C 离线候选（已应用两个事务包，尚未动态启动）：`D:\Trans\migration-audit-work\mechanomania-latest-c-extracted-20260815\mechanomania-matched-runtime-attempt13-20260814`
- Heightmap 兼容 JAR SHA-256：`AD26B1F429F0E39FCD19D6EFD151DF93A62F3B0F7262312C7BA1D8340E13EFBF`
- 544 高度 overlay：`outputs/worldgen-height-544-overlay-20260815`

## 已通过的门禁

1. V 参考世界 `29,305 / 29,305`、40 regions、19/19 PASS。
2. Terrain/POI slot OTA 静态测试 13/13 PASS，并在 D 盘克隆 pre/apply/post 全部通过。
3. 198 个当前实体全部保留；72 个确定性迁移；UUID、物品载荷和其余 NBT 无漂移。
4. 384→544 Heightmap 兼容模组双构建同哈希；动态加载时新警告为 0。
5. Y479 可放置，Y480 正确拒绝。
6. D 盘整合服克隆干净启动、保存、停服；MineAstr 0.6.27 正常连接；MCModSync 未加载。
7. 动态稳定后的整合服保护区与动态稳定原版 V：29,305 区块语义不一致为 0；圈外 C 记录漂移为 0。

## 正式远端 OTA 的固定顺序

1. 停止远端服务端，确认 Java 进程退出、`session.lock` 释放。
2. 对远端服务端根做完整备份；不要从运行中的服务器复制 MCA。
3. 将停服后的远端根视为这份最新 C 的部署目标；先运行只读 `verify-bundle` 和两个事务包的 prestate/target 校验。
4. 若 Terrain/POI 与 Entity 两套 CAS 前像全部匹配，直接复用已冻结的两个 bundle，不需要再生成 C2，也不需要重建计划。
5. 若任一受影响文件、slot、实体载荷或对象关系不匹配，必须在首次写入前停止；仅此时才从该停服状态重新审计并重建两包。
6. 核对外层锁定清单中的 C、V、plan、bundle 和动态语义报告哈希。
7. 应用 544 高度 overlay 和 Heightmap 兼容 JAR；服务端、最终客户端都使用同一 JAR 哈希。
8. 应用 Terrain/POI slot bundle，再应用 Entity 对象级 bundle。禁止整 region、整 world 覆盖。
9. 首次维护启动不开放玩家进入；加载中心与边界代表区块，等待计划刻稳定，`save-all flush` 后干净停服。
10. 运行语义后验：保护区对动态稳定 V，圈外对锁定的最新 C；方块、群系、结构、Heightmap 必须 0 不一致。
11. 实体后验必须保持全部 UUID/载荷，且无碰撞、无静默删除。
12. 第二次启动确认无新错误后再开放玩家。

## 回滚纪律

- 首次启动前：允许使用原事务字节级回滚。
- 首次启动保存后：原 postimage 已被正常 tick/save 改写，旧字节回滚必须拒绝。
- 禁止绕过 CAS。需回滚时重新停服、取得新快照，并生成新的语义/对象级回滚事务。

## 仍然阻断的功能

“同一主世界在远处平滑过渡到完整 Tectonic、且无断崖”仍是 `BLOCKED_FAIL_CLOSED`。在 BOTH-side 距离感知 worldgen 模组、最终冻结 mask、boundary atlas 和跨边界写入门禁完成前：

- 主世界未来生成应保持原版兼容；
- 完整 Tectonic 只允许使用独立 `mechanomania_frontier:frontier` 维度；
- 不得仅靠 JSON 切换 noise settings，也不得在旧边界外直接启用 544 高度 Tectonic。

## MCModSync

- 服务端永不安装。
- 自动测试期间禁用，防止把已修复模组降级。
- 最终客户端发布时必须恢复，但 manifest 必须锁定最终审核版本，不能指向旧模组清单。

## 核心证据

- 状态机：`outputs/terrain-biome-ota-current-state-20260815.json`
- 最新 C 锁定清单：`outputs/protected-terrain-ota-latest-c-lock-20260815.json`
- 动态语义报告：`outputs/protected-terrain-settled-v-dynamic-validation-20260815.json`
- 动态测试报告：`outputs/protected-terrain-dynamic-clean-run-20260815.json`
- Entity ledger：`outputs/protected-zone-entity-relocation-ota-20260815.json`
- Heightmap 审计：`outputs/heightmap-384-to-544-compat-audit-20260815.json`
- 未来生成附录：`outputs/WORLDGEN-HEIGHT-544-AND-FRONTIER-APPENDIX-20260815.md`
