# 保护区地形/群系槽位级 OTA 工具（2026-08-15）

## 结论

`outputs/tools/protected_zone_terrain_ota.py` 已实现为 fail-closed 工具。它不会把 V 的整份 region
覆盖到 C；它以 chunk slot 为单位重建 MCA：

- 圆心固定为 `x=10192, z=-1574`；
- 半径固定为 `1536`；
- 使用“16×16 区块闭合整数格中至少一个方块坐标落在圆内或圆上”的严格离散规则；
- 锁定结果为 `29,305` 个区块、`40` 个 region；
- `region` 的选中槽位来自 V；圈外槽位的原始压缩记录和 timestamp 来自 C；
- `poi` 不与 terrain 暗中混用，规划时必须显式选择 `preserve-current` 或
  `donor-selected`；
- `entities` 只做逐文件字节哈希守卫，禁止进入 payload，apply/rollback 均不写 entities MCA；
- 零字节 MCA 被当作合法空占位处理；terrain donor 缺少任一选中槽位会整体拒绝；
- external `.mcc`、损坏/重叠 sector、未知压缩类型、路径越界、输入漂移均拒绝。

当前并未生成 V，因此没有构建或应用正式 OTA，也没有修改任何世界。

## 默认安全模式

只读命令：

- `inspect`
- `plan`
- `verify-bundle`
- `verify-target`

`build` 只在旁路目录生成 detached bundle，不编辑世界。只有 `apply` 与 `rollback` 会写世界，并且
二者都要求同时提供：

```text
--allow-world-write --stopped-server-ack SERVER_IS_STOPPED
```

apply 之前会校验所有 40 个保护区 region、40 个 POI 候选文件和 40 个 entities 候选文件是否仍与
计划绑定的 C 完全一致。任一文件存在性、长度或 SHA-256 不一致，都会在创建 backup 和写入世界前
拒绝。也就是说，远端公测服如果继续产生了新变化，必须先取得新的停服快照并重新 plan，不能强行套用
旧 C 的 bundle。

## 推荐流程

以下示例中的 V 必须是最终验收通过的原版参考世界根目录；所有大型产物和 preimage 均放 D 盘。

```powershell
python outputs/tools/protected_zone_terrain_ota.py plan `
  --current "<DOWNLOAD_ROOT>\mechanomania-matched-runtime-attempt13-2.zip" `
  --donor "<AUDIT_ROOT>\vanilla-protected-V\world" `
  --poi-policy donor-selected `
  --output "<AUDIT_ROOT>\protected-terrain-ota\plan.json"

python outputs/tools/protected_zone_terrain_ota.py build `
  --plan "<AUDIT_ROOT>\protected-terrain-ota\plan.json" `
  --bundle-root "<AUDIT_ROOT>\protected-terrain-ota\bundle"

python outputs/tools/protected_zone_terrain_ota.py verify-bundle `
  --bundle-root "<AUDIT_ROOT>\protected-terrain-ota\bundle"

python outputs/tools/protected_zone_terrain_ota.py verify-target `
  --bundle-root "<AUDIT_ROOT>\protected-terrain-ota\bundle" `
  --world "D:\stopped-server-copy\world" --state pre
```

只有 pre 验证 PASS、服务端已停服并且 preimage 目录为空时，才进入 apply：

```powershell
python outputs/tools/protected_zone_terrain_ota.py apply `
  --bundle-root "<AUDIT_ROOT>\protected-terrain-ota\bundle" `
  --world "D:\stopped-server-copy\world" `
  --backup-root "<AUDIT_ROOT>\protected-terrain-ota\preimage" `
  --allow-world-write --stopped-server-ack SERVER_IS_STOPPED
```

回滚也先做 postimage CAS；任何启动后写入或人为篡改都会导致回滚拒绝，防止把混合状态静默覆盖：

```powershell
python outputs/tools/protected_zone_terrain_ota.py rollback `
  --apply-receipt "<AUDIT_ROOT>\protected-terrain-ota\preimage\apply-receipt.json" `
  --allow-world-write --stopped-server-ack SERVER_IS_STOPPED
```

## 当前 C 的只读实盘结果

输入：`<DOWNLOAD_ROOT>\mechanomania-matched-runtime-attempt13-2.zip`

- ZIP 字节数：`7,936,970,883`
- ZIP SHA-256：`ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92`
- 自动识别世界根：`mechanomania-matched-runtime-attempt13-20260814/world`
- terrain 候选文件存在：`28/40`；选中槽位已占用：`12,370`
- POI 候选文件存在：`23/40`；选中槽位已占用：`9`
- entities 候选文件存在：`15/40`；选中槽位已占用：`89`
- 检查状态：`PASS_READ_ONLY`
- 报告：`<AUDIT_ROOT>\protected-terrain-ota-tool-20260815\current-C-protected-inspection.json`
- 报告 SHA-256：`A65FC19BBEC804281C2A28F61AF82381503C5A44242CEB595B0CF33AF10A6854`

## 测试证据

命令：

```powershell
python -m unittest -v outputs/tools/test_protected_zone_terrain_ota.py
```

结果：`13/13 PASS`。覆盖：

- 离散圆边界和 `29,305/40` 锁；
- 负坐标 region/slot；
- 选中槽位取 V、圈外原始记录和 timestamp 保持 C；
- 零字节 current MCA；
- 零字节/缺槽 terrain donor 拒绝；
- POI 独立删除语义；
- external `.mcc` 拒绝；
- detached plan/build 不产生 entities payload；
- apply 写入门禁；
- preimage CAS 漂移拒绝；
- apply + 精确 rollback；
- postimage 被篡改时 rollback 在写入前拒绝；
- entities 零字节文件在 apply/rollback 前后保持完全一致。

固定文件哈希：

- `protected_zone_terrain_ota.py`：`2716F2B4A345EC0FE32C7AFCCB5649741ADC1627C204013457B4C4CDA02A2D8C`
- `test_protected_zone_terrain_ota.py`：`E4BDD90EC490AAE9612479D95406C38203ACEF354875591469E269C550954AD6`

