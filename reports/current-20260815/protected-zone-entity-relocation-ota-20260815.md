# 保护区实体对象级 OTA（2026-08-15）

**状态：`READY_FOR_D_TEST_CLONE_CAS_APPLY_NOT_APPLIED`**

对象级实体 OTA 已经完成规划、离线装配和回滚演练，但没有写入原 ZIP、V 世界、指定的 D 盘 terrain 测试克隆或任何生产世界，也没有启动 Java。

## 结果

- C 的 198 个实体全部保留，发布后仍为 198 个；UUID 没有增加、丢失或重复。
- 126 个原位置已经安全的实体不改坐标。
- 51 个硬碰撞实体和 21 个 REVIEW 实体共 72 个进行了确定性重定位：水生 13、陆生 10、飞行 3、`falling_block` 16、掉落物 30。
- 只有 11 个实体跨区块移动；保护区占用的 entity 槽从 89 个变为 91 个。
- 65 个 `minecraft:item` 的完整 `Item` compound 逐个相等；全部实体除 `Pos` 外的类型化 NBT 载荷哈希完全相等。
- 前后 UUID 清单哈希同为 `502B244B0DDC17E523D7159FBA4C3BAF65239F5553896DED8F605A5A293054BF`。
- 前后载荷清单哈希同为 `53D6BBFBE9AEF2C0F6E4000D3EF275B538C21197331C5634C66F409CAC8F3DB6`。
- 14 个 entity region 文件需要变化；40 个相关 region 文件都有前像与 CAS。保护区外槽位的 raw record 和 timestamp 指纹全部保持 C，差异为 0。

候选位置使用完整总序：`distance_squared,horizontal_squared,abs_dy,y,dx,dz`。因此即使几何距离相同，也会得到唯一、可复现且不与其他保留实体重叠的目标；如果完整搜索仍没有目标，工具会阻断，不会静默删除实体。

## 安全与测试

- detached 包会从自身的 40 个前像和 14 个后像重新解析全部 198 个实体，而不是只相信 plan JSON。
- apply 同时要求 `--allow-world-write` 和 `--stopped-server-ack SERVER_IS_STOPPED`。
- apply 前检查整文件前像 SHA-256、selected/outside 槽指纹；写入使用原子替换，失败会自动回滚。
- 二次 apply 返回 `ALREADY_APPLIED_VERIFIED`；后像被篡改会拒绝；回滚和二次回滚均通过。
- 真实数据与失败注入测试：13/13 PASS。
- 指定 D 盘测试克隆只读前像检查：40/40 PASS，尚未实际 apply。

## 交付路径

- 工具：`outputs/tools/protected_zone_entity_ota.py`
- 测试：`outputs/tools/test_protected_zone_entity_ota.py`
- 完整逐实体 plan：`<AUDIT_ROOT>\protected-entity-ota-20260815\entity-ota-plan.json`
- detached bundle：`<AUDIT_ROOT>\protected-entity-ota-20260815\bundle`
- 测试克隆前像检查：`<AUDIT_ROOT>\protected-entity-ota-20260815\test-clone-preimage-verification.json`

关键校验：

- plan：`060D7E6AD9F1F9A129C0CF34592A780FB2D993BDA8E893D3241626DEE1DEE544`
- bundle manifest：`D5B64C32CE711B04A2D38E1BD6EF0023542939050E96E9B246957CAC0767CB1D`
- bundle `ARTIFACTS.sha256`：`9761DF8EFA009471F959D3A5A40FE2AAC3EFF739BE05314ED0D5A33A886C5BA8`

该包目前只授权用于指定 D 盘测试克隆的验证。生产服应用前必须针对停止后的真实世界重新通过同一套前像 CAS；本报告不把静态检查冒充 NeoForge 在线运行验证。

## 交接命令（仅在停服并确认前像后）

```powershell
$tool = '<WORKSPACE>\outputs\tools\protected_zone_entity_ota.py'
$bundle = '<AUDIT_ROOT>\protected-entity-ota-20260815\bundle'
$world = '<AUDIT_ROOT>\protected-terrain-ota-test-server-20260815\mechanomania-matched-runtime-attempt13-20260814\world'
$backup = '<AUDIT_ROOT>\protected-entity-ota-20260815\apply-backup-20260815'
python $tool verify-target --bundle-root $bundle --world $world --state pre
python $tool apply --bundle-root $bundle --world $world --backup-root $backup --allow-world-write --stopped-server-ack SERVER_IS_STOPPED
python $tool verify-target --bundle-root $bundle --world $world --state post
```

该 bundle 只触碰 `world/entities/`；应与 terrain/biome slot OTA 分开执行并分别保留 receipt。回滚使用 `$backup\apply-receipt.json`，同样要求停服确认。
