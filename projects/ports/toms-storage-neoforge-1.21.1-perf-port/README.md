# Tom's Simple Storage - 非官方 NeoForge 稳定性 Fork

![Tom's Simple Storage banner](https://raw.githubusercontent.com/tom5454/Toms-Storage/master/banner.png)

这是 [tom5454/Toms-Storage](https://github.com/tom5454/Toms-Storage) 的非官方 Minecraft 1.21.1 NeoForge fork。它完整保留 Tom's Simple Storage 的存储、终端、连接器、无线访问、过滤和漏斗功能，并针对大型模组服的网络扫描、Create Item Vault、跨区块重启恢复、终端容量显示和 JEI 配方转移进行了稳定性修复。

本 fork 的问题请提交到 [fork 仓库](https://github.com/YU322142/Toms-Storage/issues)，**不要向上游项目报告由本 fork 引起的问题**。

## 下载

- 版本：`2.3.0-perf5.2`
- 计划发布 tag：[`neoforge-1.21.1-2.3.0-perf5.2`](https://github.com/YU322142/Toms-Storage/releases/tag/neoforge-1.21.1-2.3.0-perf5.2)
- 发布文件：`toms_storage-neoforge-1.21.1-2.3.0-perf5.2.jar`
- 源码分支：[`port/neoforge-1.21.1`](https://github.com/YU322142/Toms-Storage/tree/port/neoforge-1.21.1)

## 兼容矩阵

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Minecraft | `1.21.1` | 不支持跨 Minecraft 版本混用 |
| NeoForge | `21.1.219+` | 客户端和服务端均需安装 |
| Java | `21` | 启动游戏和本地构建均使用 Java 21 |
| Create | `6.0.10` | 可选；本 fork 的兼容测试目标 |
| JEI | `19.22.0.315` | 可选客户端配方查看器 |
| REI | `16.0.799` | 可选客户端配方查看器 |

JEI 与 REI 不需要安装在纯服务端。Create 也是可选依赖；未安装 Create 时，Tom's Storage 的普通库存网络仍可正常使用。

## 本 Fork 修复内容

- 大型网络使用两阶段库存去重：先按低成本逻辑键折叠多方块成员，再按解析后的物理根库存去除代理别名。原有去重语义、连接优先级和独立物理库存不会被牺牲。
- Create Item Vault 使用 controller 位置作为逻辑键；Vault 合并、拆分和 controller 变化会使缓存失效，避免同一 Vault 被成员方块重复统计。
- 网络扫描采用限界执行与稳定快照，避免超大型仓库不断重启全量扫描，后台扫描也不会直接读取可变 handler 状态。
- 远距离网络和远程存储连接器会持久化通道信息，并在区块分批加载或服务器重启后自动补全网络，无需拆放连接器。
- 终端显示确切的总格子数和空余格子数，不再在大容量网络中显示 `很多/?` 一类哨兵值。
- JEI 配方转移按整个配方进行全局、数量感知的材料分配，正确处理重复材料、重叠候选、组件不同的物品变体和有空位的有序配方。
- 配方填充会在缓存过期时立即刷新库存视图；提取失败会完整回滚，且只扣减失败精确变体的一份可用容量，而不是禁用整个物品种类。
- 配方规划使用容量节点而非按物品数量展开，并有 `10 ms` 规划预算，避免复杂仓库或恶意候选集合阻塞服务器线程。
- JEI 和 REI 适配类随正式 JAR 发布，但不会把配方查看器本体打包进模组。

更完整的实现说明见 [FORK_NOTES.md](FORK_NOTES.md)，发布变更见 [RELEASE_NOTES.md](RELEASE_NOTES.md)。

## 上游功能

- Storage Terminal 与 Crafting Terminal
- Inventory Connector 与 Filtered Inventory Connector
- Open Crate
- Wireless Terminal 与 Advanced Wireless Terminal
- Inventory Hopper
- 库存搜索、排序、过滤和配方终端工作流

若安装 [Create Contraption Terminals](https://www.curseforge.com/minecraft/mc-mods/create-contraption-terminals)，终端也可以用于 Create contraption。该扩展模组不属于本仓库，也不等同于本 fork 内置的 Create Item Vault 兼容修复。

## 安装与升级

1. 备份世界、玩家数据和服务端配置。
2. 确认游戏为 Minecraft `1.21.1`，NeoForge 不低于 `21.1.219`，运行时为 Java `21`。
3. 从客户端和服务端的 `mods` 目录移除旧版或重复的 Tom's Storage JAR。
4. 将同一份 `toms_storage-neoforge-1.21.1-2.3.0-perf5.2.jar` 放入客户端和服务端的 `mods` 目录。
5. 按需安装兼容版本的 Create、JEI 或 REI；不要同时保留面向其他 Minecraft 版本或加载器的文件。
6. 首次升级后先在备份世界验证大型网络、跨区块远程连接和配方终端，再投入正式服务器。

## 从源码构建

```powershell
cd NeoForge
.\gradlew.bat check
.\gradlew.bat build
```

构建产物位于 `NeoForge/build/libs/`。Gradle 需要 Java 21。

## 许可证与归属

上游项目 copyright (c) 2020 tom5454，以 [MIT License](LICENSE) 开源。本 fork 保留原版权与许可声明，fork 修改同样按 MIT License 发布，且不提供任何担保。

- 上游项目：<https://github.com/tom5454/Toms-Storage>
- 非官方 fork：<https://github.com/YU322142/Toms-Storage>
