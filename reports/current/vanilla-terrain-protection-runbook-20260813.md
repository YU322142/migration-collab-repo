# x=10192, z=-1574 原版地形保护区执行手册

状态：`READY_TO_PREGENERATE`（工具与只读审计完成；尚未启动 Minecraft，也未修改 staging）

## 结论

- 主世界中心：`x=10192, z=-1574`，中心区块 `(637,-99)`。
- 用户要求的核心保护区：欧氏距离 `<=1000` 格。
- 实际原版兼容预生成区：半径 `1536` 格，即核心外再加 `536` 格缓冲。该缓冲用于吸收结构、地物与邻区生成的跨界影响。
- Chunky 1.4.23 的真实圆形选择规则是“区块中心点落在圆内”。半径 1536 选择 `28,950` 个区块，覆盖 `40` 个 terrain region；它完整包含所有与 1000 格核心相交的 `12,500` 个区块，因此核心没有边缘漏块。
- 权威 staging 的这 `28,950` 个目标区块，在 `region / entities / poi` 三类 MCA 中占用数均为 `0`。无需删除旧区块，也无需保留第二份完整世界。
- 权威 `level.dat` 仍是 seed `-794095451117350581`；overworld generator 为 `minecraft:noise` + `settings=minecraft:overworld` + `multi_noise/minecraft:overworld`。

## 为什么分两阶段但玩法仍一次性保留

第一阶段只在 D 盘隔离服务器中，用同 seed 的 NeoForge 1.21.1 基线生成半径 1536 的小型圆区；禁止把生产世界在“删了一半模组”的状态启动。隔离服务器允许：

1. `backport-1.5.jar`：提供 1.21.11 原版内容等价基线；
2. `Chunky-NeoForge-1.4.23.jar`：只负责预生成。

Happy Ghast / Nautilus 的生成型 biome modifiers 和 Mechanomania 全量世界生成在此阶段不加载，避免保护区被它们写入。隔离世界完成后，只导入本次触及的 `region / entities / poi` MCA，绝不覆盖生产 `level.dat`、`server.properties`、端口、RCON、query 或其他原配置。

第二阶段在冻结清单通过后，一次性启用完整 Mechanomania 游戏玩法、KubeJS、任务、维度、结构与世界生成。半径 1536 外的新区块正常采用完整整合包世界生成；这不会锁死日后加模组的扩展性。

## 固定输入

| 输入 | 固定值 |
|---|---|
| 权威 staging | `D:\Trans\migration-handoff-20260812\02-latest\converted-staging` |
| `level.dat` SHA-256 | `C35D75EF337BB6E1BC12A801F2881A02CA9C9B865C22B0EB6FEBDB588B693269` |
| `backport-1.5.jar` SHA-256 | `167534C66D5E6C09DCB01152EBD37D18CED5CF6278A9228C094F937886133AF5` |
| Chunky 版本 | NeoForge `1.4.23`, Modrinth version id `LuFhm4eU` |
| Chunky SHA-256 | `D72F235CF1F56F2C374F52C00BDDA5034524B28142305A84CFC123A3F92AD274` |
| Chunky SHA-512 | `2DB769DD723F243A21E1881E7C9F825E9C193DA6F2BED454B70CB6FA9E51C57F63FDCF017C0657BBD26F7BBA30815413E27C74D3C7BE0783390A96EE9BAA4BF7` |
| 目标 Minecraft / DataVersion | `1.21.1 / 3955` |
| NeoForge 基线 | `21.1.241`（当前已审计的本地服务端运行库） |
| Java 内存 | `-Xms2G -Xmx4G` |
| 隔离输出 | `D:\Trans\migration-audit-work\vanilla-terrain-freeze-20260813\isolated-server` |

## 真正预生成步骤（本轮未执行）

1. 从已审计的 NeoForge 1.21.1 服务端运行库准备 D 盘隔离根；不得复制权威世界。
2. 只放入 `backport-1.5.jar` 与固定哈希的 Chunky。
3. 使用独立 `server.properties`：`level-name=vanilla-freeze-world`、固定 seed、`server-port=0`、`enable-rcon=false`、`online-mode=false`。这不是生产配置。
4. 启动为 D 盘独立长进程；控制台执行：

   ```text
   chunky world vanilla-freeze-world
   chunky center 10192 -1574
   chunky shape circle
   chunky pattern concentric
   chunky radius 1536
   chunky selection
   chunky start
   chunky progress
   ```

5. 只接受 Chunky 100% 完成、服务端保存并干净停止的结果。
6. 用 `freeze-manifest` 检查 28,950 个 terrain chunk 全部存在、全部 DataVersion=3955、没有计划外区块、没有 external `.mcc`。任一不满足即 `BLOCKED`。
7. 导入前重新对生产目标运行 `audit-empty`，必须仍为 PASS。导入仅限触及的三类 MCA，不碰配置或 `level.dat`。
8. 导入后生成 SHA-256 冻结清单；公开开服前每次运行 `verify-manifest`，哈希漂移即拒绝发布。

## 地形衔接门禁

不能只把垂直断层外推到半径 1536。最终需在同 seed 的 A/B 小样上比较：

- A：原版兼容基线；
- B：完整 Mechanomania 世界生成；
- 半径：`1504 / 1520 / 1536 / 1552 / 1568`；
- 每个半径 720 个角度样本，共至少 3,500 个唯一点；
- 高度图：`WORLD_SURFACE / OCEAN_FLOOR / MOTION_BLOCKING`；
- 海平面水域分类与连通；
- 悬空水/岩浆列；
- 边界相邻方块高度跃迁；
- 跨界结构 References 是否指向真实的同 ID structure start。

失败关闭阈值：

| 检查 | 最大允许值 |
|---|---:|
| 任一配对高度绝对差 | 2 |
| 配对高度绝对差 P99 | 1 |
| 边界相邻高度跃迁 | 8 |
| 海洋分类不一致 | 0 |
| 水连通破坏 | 0 |
| 悬空流体列 | 0 |
| 缺失的跨界结构引用 | 0 |
| 区块解析错误 | 0 |

两个 generator 共用 `minecraft:overworld` noise settings，因此目标是验证并拒绝垂直断墙；但树木、植被、装饰器和群系边缘视觉不能用纯数学承诺“像素级零缝”。若门禁不通过，不导入、不发布，扩大原版缓冲或针对具体世界生成模组调整后重新生成隔离小样。

## 命令

只读占用审计：

```powershell
python -B outputs\tools\vanilla_terrain_freeze.py audit-empty `
  --world 'D:\Trans\migration-handoff-20260812\02-latest\converted-staging\world' `
  --radius 1536 `
  --output outputs\vanilla-terrain-protection-empty-audit-20260813.json
```

隔离世界完成后生成冻结清单：

```powershell
python -B outputs\tools\vanilla_terrain_freeze.py freeze-manifest `
  --world 'D:\Trans\migration-audit-work\vanilla-terrain-freeze-20260813\isolated-server\vanilla-freeze-world' `
  --plan outputs\vanilla-terrain-protection-plan-20260813.json `
  --output 'D:\Trans\migration-audit-work\vanilla-terrain-freeze-20260813\freeze-manifest.json'
```

冻结后防漂移：

```powershell
python -B outputs\tools\vanilla_terrain_freeze.py verify-manifest `
  --world '<导入后的世界>' `
  --manifest '<freeze-manifest.json>' `
  --output '<verify-freeze.json>'
```

A/B 环带取样与门禁：

```powershell
python -B outputs\tools\vanilla_terrain_freeze.py sample-ring --world '<A世界>' --output '<A-ring.json>'
python -B outputs\tools\vanilla_terrain_freeze.py sample-ring --world '<B世界>' --output '<B-ring.json>'
python -B outputs\tools\vanilla_terrain_freeze.py boundary-gate `
  --vanilla-sample '<A-ring.json>' --full-sample '<B-ring.json>' --output '<boundary-gate.json>'
```

## 已完成的静态验证

- 工具语法编译通过。
- `11/11` 单元测试通过：真实 Chunky 几何、核心覆盖、负坐标 region/slot、MCA 读写、external `.mcc` 拒绝、哈希漂移拒绝、边界阈值 PASS/BLOCKED。
- 权威 staging 只读空区审计 PASS。
- 固定输入哈希门禁 PASS，计划状态 `READY_TO_PREGENERATE`。

当前未执行 Minecraft/Java 预生成，未改 staging，也未改任何生产端口配置。
