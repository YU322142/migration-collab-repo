# 544 建筑高度与主世界远端 Tectonic 配置附录

日期：2026-08-15  
用途：给主 OTA runbook 提供可独立审计的配置层和未来生成器接口。本文不启动
Minecraft、不修改世界、不替代主 runbook 的 V 槽位收敛结果。

## 结论先行

当前可以安全交付的是一个“高度层” overlay：真正生效的注册表路径
`kubejs/data/minecraft/dimension_type/overworld.json` 改为
`min_y=-64,height=544,logical_height=544`。主世界的噪声设置仍然是
`min_y=-64,height=384`，所以自然地形仍停在 Y=319，Y=320..479 是可建筑的
上层空气。这个改动不写入任何区块，也不会因为高度上限变化而重跑旧世界地形。

同一主世界在冻结区外逐渐切换到完整 Mechanomania/Tectonic，不能由这个 JSON
overlay 或普通 datapack 单独完成。原因有三个：

1. 冻结集合 `F` 是“最终 C 已存在区块的并集 + 严格 29,305 个保护区槽位”，
   不是一个固定圆。普通 worldgen JSON 没有读取这份动态区块集合、计算到其边界
   距离、也没有对跨区块写入加围栏的接口。
2. 原版和 Tectonic 的噪声高度分别是 384 与 544；直接把
   `minecraft:overworld` 换成 Tectonic 会在旧边界形成高度、流体、洞穴和
   carver 的不连续，且会让装饰/结构从新块跨写入冻结块。
3. biome 是注册表对象而不是带坐标的实例。把 Wythers/Mechanomania 的全局
   biome modifier 直接挂在 `minecraft:*` 上，会把保护区也污染，不能靠一个
   biome JSON 选择“只在远处启用”。

因此 overlay 的静态状态是 `PASS`，同一主世界过渡状态必须保持
`BLOCKED_FAIL_CLOSED`。完整 Tectonic 仍可通过已经隔离的
`mechanomania_frontier:frontier` 维度使用；这是一条安全 fallback，不冒充主世界
远端方案。

## 已交付文件

```text
outputs/worldgen-height-544-overlay-20260815/
  kubejs/data/minecraft/dimension_type/overworld.json
  .ota-delete-list.json
  OVERLAY-CONTRACT.json
  README.md
outputs/tools/validate_worldgen_height_overlay.py
outputs/tools/test_validate_worldgen_height_overlay.py
outputs/worldgen-height-overlay-validation-20260815.json
outputs/worldgen-height-overlay-assembled-dryrun-20260815.json
outputs/worldgen-height-overlay-test-report-20260815.json
```

overlay 目录下唯一可部署文件是有效的 `dimension_type` 文件。旧的
`kubejs/data/minecraft/worldgen/dimension_type/overworld.json` 只出现在有哈希
保护的删除清单中，不能把它当成有效配置路径；只有 preimage SHA-256 等于
`F037D47507D099F2BC74D1D6093E3D580EE8E62312AD15F41B46DF4EA801A817` 才允许删除。

## 与冻结 V 槽位的关系

高度 overlay 与槽位 OTA 是正交的两层：

```text
停止服务端
  -> C preimage/CAS 锁定
  -> 保护区 terrain/biome 选中槽位由 V donor 写入
  -> entities MCA 保持 C 字节不变，POI 按槽位规则重建
  -> 合并本 overlay 的 dimension_type 文件
  -> 按哈希清单删除 stale path
  -> verify / 失败则 journal rollback
```

V 槽位决定保护区“已经存在的块长什么样”；高度 overlay 只决定该维度允许的 Y
范围。两者都不能覆盖保护区外 C 的普通玩家区块，也不能替换 `level.dat`、
`server.properties` 或运行中的 `entities/*.mca`。

## 必须的主世界过渡模组接口（尚未实现）

需要一个服务端和客户端都安装的 NeoForge 模组（建议独立命名空间，例如
`terrainfrontier`），其职责不是改存档，而是在新 chunk 生成阶段提供坐标感知的
生成器。建议接口如下：

```java
interface FrozenMask {
    boolean containsChunk(int chunkX, int chunkZ);
    // exact block-space distance to the union of occupied/frozen chunk squares
    double distanceToBoundary(int blockX, int blockZ);
    BoundarySample sampleBoundary(int blockX, int blockZ);
}

interface TransitionChunkGenerator extends ChunkGenerator {
    DensityFunction vanillaDensity544();   // vanilla 384 density padded with air above 319
    DensityFunction tectonicDensity544();  // isolated mechanomania_frontier closure
    Climate.Sampler vanillaClimate();
    Climate.Sampler tectonicClimate();
    PlacementGate placementGate();
    WriteFence writeFence();
}
```

### 生成算法

1. 读取只读、哈希绑定于最终停服 C 快照的冻结掩码。掩码必须包含 C 中所有已
   占用 chunk，再并入严格离散圆的 29,305 个 V chunk；不能只存圆形或 region
   文件列表。
2. 对每个 density/biome/placement 采样点计算到 `F` 的块级距离 `d`。固定门槛为
   `d<=1024` 原版 apron，`1024<d<4096` 过渡，`d>=4096` 完整 Tectonic。
   过渡权重使用确定性的 smoothstep：

   ```text
   a = clamp((d - 1024) / (4096 - 1024), 0, 1)
   w = a*a*(3 - 2*a)
   density = lerp(vanilla_density_544, tectonic_density_544, w)
   ```

   vanilla 密度在 Y=320..479 固定为空气；这样升高建筑上限不会把原版地形抬高。
3. 在 `d<=1024` 使用边界条件图将新生成的表面高度、流体和 biome cell 锚定到
   C 的实际边缘，而不是假定 C 一定是当前原版 seed 的结果。边界条件图必须在
   V/C 定稿后离线生成并锁哈希；运行时不能读取或改写冻结块来“猜”边界。
4. biome 不能通过修改 `minecraft:*` 全局对象来过渡。使用独立的远端 biome
   namespace 或坐标感知 `BiomeSource`；在保护区和 apron 中只返回原版 biome，
   在远端才返回完整 Tectonic 参数。
5. carver、ore、feature 和 structure 都走 `PlacementGate`：
   - 目标写入位置在 F 内：拒绝写入；
   - 结构包围盒可能触碰 F：延后/拒绝该 start；
   - 1024..4096：按同一 `w` 做确定性密度/强度衰减；
   - >=4096：使用完整 Mechanomania/Tectonic 集合。
6. `WriteFence` 必须在任何 `WorldGenRegion`/feature/structure 的跨 chunk 写入点
   再检查一次，避免新块的树、流体、结构或 carver 越过冻结边界。仅在
   `ChunkGenerator` 里选噪声不足以满足此门禁。

### 为什么不能把现有独立维度 JSON 直接改名覆盖主世界

当前隔离资源已证明 `mechanomania_frontier:frontier` 使用 544 高度和
`mechanomania_frontier:tectonic` 噪声闭包；当前主世界仍使用
`minecraft:overworld` 384 高度闭包。将前者直接写到
`minecraft:overworld` 会绕过冻结掩码、边界 atlas、placement fence 和客户端
codec，属于必拒绝的整世界 worldgen 替换。

## 发布门禁

在以下项目全部变为 `PASS` 前，不能把“主世界远端完整 Tectonic”标成完成，也不
能对公测世界执行相应 worldgen OTA：

- BOTH-side 模组源码、构建产物、codec 与 mixin 审计归档；
- 最终停服 C 的冻结掩码及边界条件 atlas，含源 ZIP/SHA 与生成脚本；
- 两次独立重启均成功解析 544-height composite generator；
- 保护区 V 槽位、区外 C 槽位、entities MCA 的字节级 CAS 验证；
- 过渡带高度、流体、biome、carver、结构和跨边界写入审计；
- 4096 以外 Tectonic 的 biome/feature/ore/structure 完整性审计；
- 两个客户端连接、单人世界、死亡、重登、任务、配方、BE 和回滚测试；
- 失败注入后 journal/CAS 回滚测试。

未通过时的唯一安全状态是：主世界使用高度 overlay + 原版 384 噪声，远端完整
Tectonic 只在 `mechanomania_frontier:frontier` 中提供。

## 可复制验证命令

```powershell
python -B outputs/tools/validate_worldgen_height_overlay.py `
  --overlay outputs/worldgen-height-544-overlay-20260815 `
  --report outputs/worldgen-height-overlay-validation-20260815.json

python -B -m unittest discover -s outputs/tools `
  -p 'test_validate_worldgen_height_overlay.py' -v
```

前一条必须输出 `static_status=PASS` 且
`production_release_status=BLOCKED`；后一条当前应为 10/10 通过。另一次 D 盘稀疏
装配演练同时验证了：有效路径为 544、错误路径已删除、主世界噪声仍为 384、隔离
frontier 噪声仍为 544；演练目录已在报告生成后删除，只保留 JSON 证据。

