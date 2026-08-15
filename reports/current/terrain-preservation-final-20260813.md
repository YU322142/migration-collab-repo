# 旧主世界地形零覆盖裁决与 Mechanomania Frontier 方案

生成日期：2026-08-13  
状态：`READY_FOR_ISOLATED_RUNTIME_VALIDATION`  
生产发布：`BLOCKED_FAIL_CLOSED`

## 裁决

不在旧 Overworld 的任何边界直接启用 Tectonic。旧主世界继续解析为
Minecraft 1.21.1 原版兼容的 `384` 高度噪声几何；Mechanomania 的
Tectonic `544` 高度世界生成完整放入独立维度
`mechanomania_frontier:frontier`。这不是删减玩法，而是隔离两个不兼容的地形
坐标系，避免让旧服务器地形成为试验品。

当前只能判定为“静态方案已就绪，等待隔离运行验证”，不能写成生产
PASS；本轮没有启动 Java，也没有修改世界、`level.dat`、
`server.properties`、端口、RCON 或 query 配置。

## 权威证据

| 项目 | 结果 |
|---|---:|
| 旧 Overworld terrain 区块 | 927,157 |
| 旧地形到未生成区块的完整基数边界 | 21,018 |
| 旧边界区块 | 18,120 |
| 相邻未生成区块 | 18,190 |
| 检查 blending marker 的边界区块 | 18,120 |
| 缺少 `blending_data` | 18,120 |
| 原版 Overworld 高度 | 384 |
| Mechanomania/Tectonic 高度 | 544 |
| 高度差 | 160 |
| x=10192,z=-1574 的 1536 格冻结计划 | 28,950 区块 |
| 该冻结区现有地形 | 0 区块 |

`blending_data` 在 18,120 个边界区块中
全部缺失。因此，把悬崖风险简单外推到 1000/1536 格之外不能解决问题；
旧世界实际存在 21,018 条不规则边界，任一处都可能
被玩家加载。

## 零覆盖实现

生成的静态数据包蓝图：`outputs\terrain-preservation-frontier-datapack-20260813`

它执行三件事：

1. 恢复 `minecraft:overworld` 的原版 1.21.1 dimension type、noise
   settings，以及从原版 noise settings 可达的噪声/密度函数闭包；新主
   世界区块保持 384 高度几何，旧的 927,157
   个区块完全不写入。
2. 把 Mechanomania/Tectonic noise settings 及其可达依赖闭包重命名到
   `mechanomania_frontier:*`，消除与主世界使用同名
   `minecraft:overworld` 资源的冲突。
3. 新增 `mechanomania_frontier:frontier`，沿用整合包的 7,593
   条 multi-noise biome 参数（53 个唯一
   biome）以及整合包全局加载的结构、biome feature、任务与 KubeJS 玩法。

闭包统计：原版主世界 61 个资源；
Tectonic frontier 139 个资源，来自
131 个唯一资源 ID。蓝图树哈希：
`B45C9E9940ABECFB3EC2FF094AE2AF1532EF673E02EA3F346FEB259D64A7CF2D`。

首选集成方式是由最终打包器把蓝图中的 `data/**` **最后合并**到最终
KubeJS data tree；这样不依赖数据包优先级。若作为世界 datapack 安装，
必须在隔离服务器证明它排在 Mechanomania KubeJS 数据之上。

注意：主世界的“原版兼容”在这里严格指地形高度、噪声与密度几何。
Mechanomania 的全局 biome feature/structure 注入仍可装饰以后生成的主
世界区块；已有区块不变。如果要求新主世界连装饰也逐字节原版，则还要
隔离所有 biome/structure 注册表修改，这会与“完整保留整合包玩法”冲突，
本方案不作虚假承诺。

## 生产门禁（全部通过才开服）

1. 在 D 盘隔离副本加载最终服务端；确认 registry/datapack 无错误，
   `mechanomania_frontier:frontier` 存在。
2. 读取解析后的注册表：`minecraft:overworld` 的 dimension type 与 noise
   height 必须都是 384；frontier 两项必须都是 544。
3. 用同一 seed 分别生成少量主世界和 frontier 测试区块；主世界高度范围
   不得超过原版边界，frontier 必须实际使用 Tectonic 依赖。
4. 用命令临时进入：
   `/execute in mechanomania_frontier:frontier run tp @s 0 160 0`。验证返回点、死亡、
   重登、两名客户端、结构/任务/配方/方块实体。公开版再提供受保护的传送
   门或命令，而不是依赖管理员命令。
5. 启动前后重新运行旧世界不可变清单；`region/entities/poi` 任一已有文件
   哈希漂移即拒绝发布。保护区预生成只能向审计证明为空的槽位写入。
6. 生产 `server.properties`、25566/25575/25565、RCON、query 与原
   `level.dat` 均不得被打包脚本替换。

当前阻塞项：

- 尚未用隔离 NeoForge 服务端证明 datapack/KubeJS 优先级与 codec 注册解析。
- 尚未在运行时生成测试区块，证明主世界解析为 384 高度而 frontier 解析为 544 高度。
- 尚未实现并测试 frontier 的公开受保护入口、返回点和失败恢复。
- 尚未通过双客户端、死亡、重登、结构、任务、配方、方块实体和回滚冒烟测试。
- x=10192,z=-1574 的原版冻结区尚未预生成；其独立空槽与导入门禁仍然有效。

## 可重复验证

```powershell
python -B outputs/tools/validate_terrain_preservation_final.py `
  --report outputs/terrain-preservation-final-20260813.json `
  --datapack outputs/terrain-preservation-frontier-datapack-20260813 `
  --output outputs/terrain-preservation-final-validation-20260813.json
```

静态门禁状态：`PASS`；隔离运行门禁：
`PENDING`；生产门禁：
`BLOCKED`。
