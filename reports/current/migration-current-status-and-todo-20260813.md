# 1.21.11 → 1.21.1 当前迁移状态与待办

更新时间：2026-08-13

## 结论

当前已经做到：最新备份可被转换器完整扫描，玩家、实体、方块实体、属性、试炼刷怪笼、村民与多数新原版内容的数据不会因未知 ID 而直接丢弃；已知入服/崩溃类问题已有兼容实现或保护层。

当前尚不能宣称：1.21.11 的全部原版玩法在 1.21.1 上百分之百等价。剩余风险集中在少数新增玩法的真实交互、多人同步、渲染/声音、自然生成与掉落，以及最终大整合包运行验证。

## 已完成或已有闭环修复

- 最新源扫描：112 玩家、73,117 实体、1,216 村民；村民重复 UUID 为 0，927 条交易配方可审计。
- 8,705 个 Trial Spawner 配置完成结构转换；此前 `Not a map` 崩溃链已处理。
- 211,551 条属性记录和 2,278 条物品组件别名完成转换；7 个玩家专属属性已修正为 `minecraft:player.*`。
- 玩家、实体、方块实体未知类型、属性、游戏规则、区域解析的主要 blocker 为 0。
- Waypoint Fire 高权限命令树参数已注册，4 级 OP 可入服并执行颜色命令。
- Kaleidoscope Cookery scarecrow 旧库存结构有兼容层，不再因 Slot 范围崩溃。
- Create chute 客户端卸载竞态有 BOTH-side guard。
- Create carriage 小写方向导致 `DOWN`/渲染崩溃已有转换规范化和 p0.2 guard。
- CC:Tweaked 冷启动/停服超时有受限 guard，未放宽普通 Lua 超时。
- 沉浸画框缓存已纳入迁移白名单；权威缓存为 87 原图 + 87 缩略图。
- Yuushya/creaking 等已知资源缺失已有资源闭包候选；整合包标题、品牌和主菜单“开服”入口已从 C6C 完整版中净化。
- JourneyMap 已完成到 Xaero 的静态转换：531 张地图、50 个路标，双轮确定性校验通过。
- Create potion fluid 按用户接受的小误差策略处理：两条 810 源单位各转为 8 mB，误差 +0.5 mB；其他未知非整除形状仍 fail-closed。
- 陈旧 recipe-book 仅允许首轮精确 62 行/41 ID 的受审自清理；二轮必须归零，其他格式继续阻断。

## 数据安全已闭环，但完整玩法仍需实机验证

- Nautilus / Zombie Nautilus：BODY 装备保存、替换、清空、重启属性已通过；仍需玩家 GUI、骑乘冲刺、繁殖、自然生成、僵尸骑手、掉落、发射器、剪切、声音、渲染和多人同步。
- Happy Ghast：存档/兼容实体和移动统计已实现；仍需真实多人骑乘、相机、家锚、声音和渲染回归。
- Locator Bar：保存与兼容资源存在；仍需官方资源/协议、双客户端、不同缩放和 Geyser 路径验证。
- `minecraft:netherite_horse_armor`：当前由延迟内容保护模组保活并阻止危险操作，不会静默吞物；完整模型、配方、装备玩法仍未补齐。
- 1.21.11 新方块/物品：50 个识别 ID 中 49 个有功能性 backport，剩余 1 个即 netherite horse armor 仅为安全载体。

## 当前新增整合包待办

- 合并矩阵静态 PASS：250 个上游 mod ID，解析为 252 行；19 个重叠项保留迁移基线，195 个新增项纳入选择。
- 11 个 side 元数据不完整的模组需要专服/客户端依赖验证，不能只靠 `mods.toml` 猜测。
- JourneyMap 从两侧删除，使用 Xaero Minimap + World Map；最终只复制转换输出的 `staging`，不复制回退目录。
- C6C 使用净化后的完整版本；原 full、lite、标题纹理、品牌、托管链接和“开服”入口均排除。
- 服务器旧主世界 927,157 个已生成 terrain chunks 全部是不可覆盖数据；共有 21,018 条生成前沿边。
- Mechanomania/Tectonic 把主世界高度从原版 384 改为 544；18,120 个旧边界区块没有 vanilla blending marker，因此不能直接在同维度切换并声称无断层。
- 默认安全方案：旧 Overworld 保持原版生成器；Tectonic 完整地形放到独立前沿维度。保护中心 `(10192,-1574)` 半径 1000 的空区用原版兼容生成器隔离预生成，导入只允许写空槽。

## 发布前必须完成

1. 完成旧 Overworld / Tectonic 前沿维度的数据包或兼容模组，并验证不会改写旧世界 `level.dat` 或已有 MCA 槽。
2. 对 11 个 side 不确定模组做 dedicated server + client 依赖验证。
3. 从权威 staging 和新合并矩阵组装唯一新 release lock；不复用旧 runtime，不复制第二份完整世界作为证据。
4. 双轮启动、真实高权限入服，验证列车坐标、沉浸画框、Xaero 地图、试炼刷怪笼、稻草人、CC 电脑和 recipe-book 二轮归零。
5. 客户端严格检查 Render-thread FATAL/ERROR、缺模型/贴图；服务端严格检查 unknown registry、Invalid item、block entity load failure、实体拒载与数据保存差异。
6. 再做 Nautilus、Happy Ghast、Locator Bar 和 netherite horse armor 的完整玩法人工测试；任何未完成项保持 OTA 可升级的稳定 ID、sidecar/ledger 与回滚路径。

## 不会执行的危险操作

- 不会覆盖、重滚或 retrogen 服务器原有地形。
- 不会更改生产端口 25566、RCON 25575、query 25565 或原 `server.properties`。
- 不会把运行过的测试世界当转换基线。
- 不会为消除日志而删除玩家物品、实体、配方书、进度、地图或区块。
