# 地形 OTA 协作交接（当前检查点）

日期：2026-08-15  
权威详版：`outputs/MASTER-TERRAIN-BIOME-OTA-RUNBOOK-20260815.md`  
机器状态：`outputs/terrain-biome-ota-current-state-20260815.json`

## 一句话状态

保护区原版参考世界、terrain/POI 槽位 OTA、198 个实体保载荷迁移、544 建筑高度、Heightmap 兼容和 D 盘动态语义后验均已通过；
用户已确认 `attempt13-2.zip` 就是最新服务端文件；正式应用只等待远端停服与两个事务包的 prestate/CAS 校验。匹配即可直接应用，不再等待 C2。

## 永远不要变的输入

- 当前公测服 C：`<DOWNLOAD_ROOT>\mechanomania-matched-runtime-attempt13-2.zip`
- C SHA-256：`ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92`
- 最新 C 锁定清单：`outputs/protected-terrain-ota-latest-c-lock-20260815.json`
- 最新 C 离线候选：`<AUDIT_ROOT>\mechanomania-latest-c-extracted-20260815\mechanomania-matched-runtime-attempt13-20260814`
- 候选清单：`outputs/mechanomania-latest-c-ota-candidate-manifest-20260815.json`
- 候选清单 SHA：`27CC7D61016F2974490751A4AC45110DD089643E7A4D13B33A4D02E9680ACDD7`
- 旧完整归档 R：`<DOWNLOAD_ROOT>\mechanomania-matched-runtime-attempt13-20260814-ota-final-20260815.zip`
- R SHA-256：`92C719AF5A64C775992784326DC73563F0E3AEF6C6A757C9E1E22809497818B4`
- 保护区：中心 `(10192,-1574)`，半径 `1536`，严格离散相交 `29,305` chunks / `40` regions
- 核心：半径 `1000`，`12,500` chunks
- seed：`-794095451117350581`
- 目标：MC 1.21.1、DataVersion 3955、min_y=-64、height=544、自然 noise height=384、最高建筑 Y=479

原始 C/R ZIP 均禁止原地修改或删除。所有验证只在 D 盘副本进行。

## 已冻结且可复用

### V 原版参考世界

`<AUDIT_ROOT>\vanilla-reference-v-20260815\strict-reference-world\vanilla-reference-v`

- 29,305/29,305，40 regions，19/19 PASS
- final report SHA：`5507B0D06A0CDD3D9E4D362477A840D8EE4C20656265886F7AAA2C91B60BA05E`
- strict manifest SHA：`4BD4883295C8E0EFDF584A81AEB4FE19DAAA0EA0AE0B4B3BC3455E9768B2FCB1`

### terrain/POI OTA

`<AUDIT_ROOT>\protected-terrain-ota-20260815`

- bundle：`bundle\`
- plan SHA：`483DD2073E7C31691CF15E1BA507556288FF37A11523D3383F6BE34C09C8096E`
- build report SHA：`02EFC30B640FF1C54EF44D0AEC993825BF41803838AD62A07DC5694F3F4911FD`
- verify report SHA：`8ED6E0765090C74A7926301D11CDBC32FB2AC7284A4789594F03B00630E48676`
- 只替换选中 chunk slot；圈外记录/时间戳保持 C；POI 取 V；不把 V 整个 region 盲拷贝到 C。

### 544 建筑高度 overlay

`outputs/worldgen-height-544-overlay-20260815`

- 唯一有效部署文件：`kubejs/data/minecraft/dimension_type/overworld.json`
- SHA：`7DDDEBFD2936BFEAAC9FC00B792838EEF99B6E5D98FD29DA38530D4E35046E1C`
- 错误旧路径仅在 preimage SHA=`F037D47507D099F2BC74D1D6093E3D580EE8E62312AD15F41B46DF4EA801A817` 时删除。

## D 盘第一轮动态验证

测试根：

`<AUDIT_ROOT>\protected-terrain-ota-test-server-20260815\mechanomania-matched-runtime-attempt13-20260814`

- terrain/POI：preverify/apply/postverify PASS
- 2026-08-15 19:36:21：`Done (6.814s)!`
- Y479：可放置；Y480：正确拒绝
- MineAstr 0.6.27：已连接且同步绑定
- 2026-08-15 19:38:13：干净停止
- 两个 P0 已装入并完成干净动态复测；当前克隆保持停服，后续仅用于只读证据或显式的新测试。

## 已完成的两个 P0

### P0-A：实体保留迁移

报告：`outputs/protected-zone-entity-collision-poi-gate-20260815.json`  
SHA：`2AD47BEB843B3BC0C148F3CBA334C2E1484009099985228982DF86CDEC281131`

- 总数 198：126 PASS、21 REVIEW、51 硬碰撞
- 15 个冲突掉落物携带 27 件物品
- 用户策略：当前服务器状态优先，全部保留；禁止静默删除
- 必须：确定性最近安全点、按类型判断空气/支撑/水体、对象级 CAS、载荷不变、圈外 slot 原字节不变、可回滚。

### P0-B：Heightmap 384→544

- 旧区块：9-bit、37 longs、256 values、非跨 long
- 新高度：10-bit、43 longs、256 values、非跨 long
- 注入点：MC 1.21.1 `Heightmap#setRawData(ChunkAccess, Heightmap.Types, long[])`
- 仅 `chunk.getHeight()==544 && incoming.length==37` 时语义等价重打包；其他输入保持 vanilla。
- 证据：`outputs/HEIGHTMAP-RUNTIME-CONTRACT-EVIDENCE-20260815.md`

## 完成 P0 后的固定顺序

1. 两个产物各自双构建/哈希一致、测试全 PASS。
2. 仅向 D 测试根装入实体 OTA 和 BOTH-side Heightmap JAR；不改 C ZIP。
3. preverify 所有 C/V/plan/JAR 哈希。
4. 启动测试服，强制加载代表性旧区块与保护区实体槽。
5. Heightmap `expected 43, got 37` 新增警告必须为 0。
6. 198 个 UUID 全在；物品载荷总量/逐对象哈希不变；碰撞/支撑/水体门禁全 PASS。
7. save-all、干净停服、第二次启动，重复 4–6。
8. 回滚副本，验证 preimage 字节恢复；再重新 apply 验证幂等。
9. 更新主手册和机器状态；只有全部通过才生成面向另一台服务器的停服 OTA 包。

## 仍未完成的远端地形

同一主世界“旧区块外平滑过渡到完整 Tectonic”仍是 `BLOCKED_FAIL_CLOSED`。需要 BOTH-side 距离感知生成模组、
最终 C 冻结 mask、boundary atlas 和跨边界写入门禁。在此之前，`mechanomania_frontier:frontier` 仅作为安全独立维度 fallback。

MCModSync：服务端永不安装；测试客户端禁用；最终客户端只有在清单锁定最终版本、保证不降级后才恢复。

## 2026-08-15 动态复测结果

单实例干净启动证据：`outputs/protected-terrain-dynamic-clean-run-20260815.json`。

- D 测试克隆达到 `Done (4.589s)`，并经控制台干净停服。
- 37→43 heightmap 兼容已在运行时加载；`expected: 43, got: 37` 新警告为 0。
- 保护区中心 chunk `(637,-99)` 与边界探针 `(699,-99)` 已加载后解除强制加载。
- MineAstr 0.6.27 已连接并完成绑定同步；MCModSync 未加载。
- 实体 OTA 40/40 文件后验 PASS。
- 地形动态稳定语义后验 PASS：29,305/29,305 选中区块与动态稳定 V 一致；Heightmap 差异 0；圈外 1,764 个 C 记录差异 0。旧字节回滚在启动保存后按设计 fail-closed，拒绝前写入 0。生产尚未写入；远端停服前像与锁定 C 的两个事务 CAS 匹配即可应用，不匹配则零写入中止并重建。
