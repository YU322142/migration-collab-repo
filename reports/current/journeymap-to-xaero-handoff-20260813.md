# JourneyMap → Xaero 静态迁移交接（2026-08-13）

状态：`STATIC_VALIDATION_PASSED`。本任务未启动 Minecraft/Java，未修改 Prism 实例、现有 release、生产服务端或网络配置。

## 成品与工具

- D 盘转换根：`<AUDIT_ROOT>\journeymap-xaero-conversion-20260813`
- 主安装候选：上述目录的 `staging\`
- 机器可读报告：`conversion-report.json`
- 人工报告：`conversion-report.md`
- 完整清单：`SHA256SUMS.txt`
- 转换器：`outputs\tools\convert_journeymap_to_xaero.py`
- 测试：`outputs\tools\test_convert_journeymap_to_xaero.py`

最终 SHA-256：

- `SHA256SUMS.txt`：`6D064E5D0F704CC91AFCD0FFE761B6656694A85CCC99B662A4BAA6E3FC906129`
- `conversion-report.json`：以 D 盘成品当前文件为准（报告内含转换指纹与全部输入哈希）。
- 转换器：`FD7139D233278E11E634E0BA17A2DEFBE34B71791143FB05CD5078B08ABDD3E9`
- 测试：`DC2D557AC66CC416AA703505F684AC54314662477978D08363D49DFCA0E36276`

## 端口边界

- `play.example.invalid:12341` 仅作为一次性转换/审计身份，用来确认 Xaero 的缓存目录算法。
- 生产服务器保持 `play.example.invalid:25566`，没有被转换器写入或修改。
- Xaero 26.1.0/1.41.2 的当前多人缓存根会剥离端口，因此两者都映射到 `Multiplayer_play.example.invalid`。这不等于更改生产端口。
- 转换器现在要求 `--port` 与 `--production-port` 不同；相同即 fail closed。

## 迁移结果

- 原 ZIP 与 D 盘解压树：3571 个文件，大小与 CRC32 全量一致；源 ZIP SHA-256 为 `7e2db146c0b44b4dfe5f1c2f5732791d55aa3ccfb039b027dcac2cacc268bba7`。
- JourneyMap day PNG：531 张；Xaero World Map v4 region ZIP：531 个；531/531 静态解析、ZIP CRC、结构、状态 ID 与源哈希绑定均通过。
- 维度分布：主世界 453、下界 27、末地 51。
- Waypoint：源 50 个、输出 50 条；主世界 45、下界 2、末地 3；三份原生 `mw$default.txt` 均为 14 字段，错误字段数 0。
- 输出 staging 共 539 个文件，其中 JourneyMap 模组/配置文件为 0，临时文件为 0。
- `SHA256SUMS.txt` 共 553 条，逐条重算不匹配数为 0。
- 使用 20 个工作线程完成；连续两次 `--resume` 的 `SHA256SUMS.txt` 哈希完全相同，确定性复验通过。
- 单元/集成测试：13/13 通过。

## 已锁定的 Xaero 格式规则

- 目标：Xaero Minimap 26.1.0、Xaero World Map 1.41.2，且 JAR 版本、关键类、关键格式标记、类哈希与内嵌 `vanilla_states.dat` 均被静态校验。
- World Map：`xaero/world-map/Multiplayer_play.example.invalid/{null,DIM-1,DIM1}/mw$default/<rx>_<rz>.zip`。
- Minimap waypoint：`xaero/minimap/Multiplayer_play.example.invalid/{dim%0,dim%-1,dim%1}/mw$default.txt`。
- World Map 与 Minimap 都显式选择 `mw$default`，并仅在该服务器专属缓存配置中忽略未知 `levelId`，避免首次连接看不到导入数据。
- Waypoint 冒号按 Xaero 26.1.0 的 `§§` 规则转义；死亡组映射为 `OLD_DEATH`。
- `vanilla_states.dat` 的 32 位键为低 12 位块 ID + 高 20 位旧状态索引。1681 条记录归并为 1656 个唯一键；25 次同键覆盖全部 NBT 完全相同，冲突数为 0。转换器复刻 Xaero `OldFormatSupport.putState` 的“文件后项覆盖”语义并输出独立审计清单。
- 恢复安全：输出 sentinel、每个 region ZIP 注释和最终报告都绑定转换指纹 `81d2a55279ab700e419b1f61ed4b6802f0b7f6ab3a732a26e500cacf465259dc`；输入内容或端口边界变化时 `--resume` 会拒绝复用旧区域。

## 不可逆/近似部分与保留策略

- JourneyMap day 栅格没有原始方块身份。65,953,792 个非透明像素、417,912 种 RGB 被确定性量化到可由 Xaero 1.41.2 旧格式解析的 334 色状态调色板；完整 RGB→状态 LUT 保存在 `manifests\color-lut.bin.gz`。
- 加权平均颜色距离 27.606，RMSE 30.552，P95 47.021，最大 119.624；精确调色板命中率 0.0883%。这是主要不可逆视觉误差。
- 高度统一为 Y=64、biome 为 plains；下界使用满光。透明整块保持 void，非空块内透明像素写 air；源中无部分 alpha 像素。
- night、topo、biome、高度切片以及 JMD/JMM 不伪装成 Xaero 原生数据。2829 个非 day PNG 和其他参考层由源 ZIP、D 盘解压根及 `source-inventory.json` / `reference-layers.json` 保留。
- Waypoint 坐标、名称、维度、启用状态和分组得到迁移；颜色压缩为 Xaero 16 色。GUID、原色、图标、opacity 与完整组设置保存在 `waypoints\waypoints-audit.json`。

## 安装注意

只在客户端完全停止且已备份现有 `xaero\` 目录后，复制 `staging\` 内容到目标客户端 `.minecraft\`。不要同时安装 `alternatives\legacy-waypoint-import\`；它只是回退用的一次性旧格式导入方案。

Mechanomania 清单没有选择 JourneyMap，但包内仍有过时的 `overrides/config/journeymap-server.toml`。最终组装时应明确排除该文件。此静态转换成品本身不含 JourneyMap。
