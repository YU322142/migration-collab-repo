# JourneyMap → Xaero 静态转换报告

- 状态：`STATIC_VALIDATION_PASSED`
- 构建日期：`2026-08-13`
- 一次性审计身份：`play.example.invalid:12341`（仅用于确定缓存主机名）
- 生产服务器：`play.example.invalid:25566`（未修改）
- Xaero 缓存根：`Multiplayer_play.example.invalid`（Xaero 当前格式会从目录名剥离端口）
- Minecraft 启动：`false`

## 结果

- JourneyMap 原始 waypoint：50 个；Xaero 输出记录：50 个。
- JourneyMap day 区域图：531 张；Xaero v4 region ZIP：531 个。
- 静态解析通过：531 / 531。
- 非透明像素：65,953,792；精确命中调色板：0.0883%。
- 加权平均颜色距离：27.606；RMSE：30.552；P95：47.021。

## 明确保留但未原生表达的内容

- 地图来自 JourneyMap day 栅格，不含原始方块身份；每个 RGB 被确定性量化到 Xaero 1.41.2 可解析的最近旧版方块状态。完整 RGB→状态 LUT 已保存在 manifests/color-lut.bin.gz。
- 地图高度统一写为 Y=64、biome 统一写为 plains；Nether 使用满光照。源高度切片、biome、topo、night、JMD/JMM 均未伪装导入，而是由 source-inventory/reference-layers 清单和原 ZIP/解压根保留。
- 全透明 16×16 图块保持 void；非空图块内部的透明像素显式写为 air，避免黑色填洞。部分透明像素的 alpha 无法由 Xaero v4 表达，其 RGB 仍参与量化并在统计中单列。
- Waypoint 坐标、名称、维度、启用状态与分组→set 被迁移；颜色缩减为 Xaero 16 色。JourneyMap GUID、原色、图标资源、opacity、group 设置等完整保存在 waypoints-audit.json。
- JourneyMap death 分组映射为 Xaero OLD_DEATH，保留历史死亡点语义并降低被“到达后删除当前死亡点”设置误删的风险。
- 主 staging 使用原生 Xaero waypoint 文件；alternatives/legacy-waypoint-import 是可回退的一次性导入方式，二者不得同时安装。
- 为保证首次连接即可命中已转换缓存，本服务器专属 Xaero 缓存配置把 World Map 和 Minimap 绑定到 mw$default，并忽略服务端 levelId。此设置不改服务端，也不是全局模组限制；若以后需要按 levelId 分隔多个同维度世界，应先迁移缓存目录，再在该服务器的 Xaero 配置中重新启用 levelId。
- 所有不可原生表达的信息仍可从原始 ZIP、D 盘解压审计根及本输出 reference/manifests 恢复；转换未改动源文件。

## 安装边界

`staging/` 是可复制到客户端 `.minecraft/` 的主路径；`alternatives/legacy-waypoint-import/` 只是一次性旧格式导入备选，不能与原生 waypoint 文件同时安装。

`12341` 是一次性审计/测试端口；生产服务器端口保持 `25566`。Xaero 目录名会剥离端口，因此本输出只绑定主机 `play.example.invalid`，不写入生产端口配置。

本任务没有修改 Prism 实例、现有 release、服务器端口或任何 Minecraft 配置。转换输出也不包含 JourneyMap 模组。
