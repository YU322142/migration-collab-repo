# Attempt6 LootDataType 298 条只读审计

- 审计时间：2026-08-14 14:02（Asia/Shanghai）
- 运行时：<AUDIT_ROOT>\mechanomania-matched-runtime-attempt6-20260814
- 错误日志：<AUDIT_ROOT>\attempt6-server-errors-by-logger-20260814.txt
- 错误日志 SHA-256：7C5F3B598FD7E9DA2E6B9956F115800365A1E11C4DE85DA993109AFA7288BD90
- 解析结果：298/298 条，来源 5 个 JAR；loose datapack 命中 0。
- 范围保证：未启动 Minecraft；未修改 Attempt6、冻结 staging、生产或 Prism。

## 结论

298 条不是世界存档损坏，也不是缺少 loose datapack；全部是当前模组 JAR 自带的数据资源在可选依赖缺席、条件字段过时或命名空间大小写错误时被解析。建议做“数据资源热修复”而不是删除整族内容：当前包清净，未来通过 OTA 加入可选模组时仍能恢复玩法。

| 来源 | 数量 | JAR SHA-256 | 判定 |
|---|---:|---|---|
| create_connected | 16 | 90BDCEAC63CB0EBD5E51351E22136182B996512EDEF937D0635D2857B0A3F24B | 可保留；补 Dye Depot 条件 |
| railways | 276 | B7636C8B1B0352ED1A130DFE67F8BB574E2FC08803ED1CDA4D3EA00505193914 | 可保留；条件字段修复 |
| tracks | 3 | B126B2522A129C13EBEC6491B8602726BAD9A3DF201CF906468BA583796125C8 | 可保留；Tracks→tracks |
| irons_spellbooks | 1 | BA1F1986CA706AE348CB6FCE6E383AB7CC61C375826CCF0E4D3A88ED2F9FCD3D | 孤立测试表；可删/禁用 |
| minecraft | 2 | 890882EC1239FFF1CD5CC5F1DA1FE4BE98A31E748D418220BEE5F2B9F3D8FD91 | 保留池；只处理失效附魔选项 |

## Railways：276 条

- JAR：railways-0.2.1+neoforge-mc1.21.1.jar；SHA-256 B7636C8B1B0352ED1A130DFE67F8BB574E2FC08803ED1CDA4D3EA00505193914。
- 家族计数：{"biomesoplenty":30,"blue_skies":18,"byg":84,"create_dd":12,"hexcasting":3,"natures_spirit":36,"quark":9,"tfc":60,"twilightforest":24}。
- 当前 schema：{"legacy_conditions":210,"none":66}；210 条使用旧顶层 conditions，66 条完全没有加载条件。
- 依赖核对：biomesoplenty、blue_skies、BYG/biomeswevegone、hexcasting、twilightforest、natures_spirit、create_dd、quark、tfc 均未安装。
- 资源内容确实是可选轨道掉落表；不是误删的基础 Railways 轨道。
- 推荐修复：旧字段改为 NeoForge 形式：顶层 conditions → neoforge:conditions；每项 {condition:neoforge:mod_loaded,modid:X} → {type:neoforge:mod_loaded,modid:X}。
- 无条件的 Blue Skies / Create DD / Nature’s Spirit 轨道增加对应 neoforge:mod_loaded 条件。
- BYG 条件使用 neoforge:or 同时接受 byg 与 canonical biomeswevegone，避免未来安装 BWoG 后配方/掉落静默不启用。
- 同族静态检查：276 个兼容 recipe 全部已有 neoforge:conditions；5 个 tag 文件对 276 个可选轨道引用全部 required:false。

## Create Connected：16 条

- JAR：create_connected-1.3.2-mc1.21.1.jar；SHA-256 90BDCEAC63CB0EBD5E51351E22136182B996512EDEF937D0635D2857B0A3F24B。
- 16 个 dye_depot_*_fan_dyeing_catalyst 物品不存在，因为 dye_depot 未安装；这些是 Dye Depot 可选兼容资源。
- 16 个 loot table 没有顶层加载条件，所以在解析物品注册表时直接报错。
- 推荐修复：保留资源，增加顶层 neoforge:conditions：[{type:neoforge:mod_loaded,modid:dye_depot}]。
- 同族静态检查：80 个引用这些 ID 的 recipe 全部已有 NeoForge 条件并明确要求 dye_depot；但 35 个 block-tag 文件没有 required:false，建议同一热修复中把可选条目显式标为 required:false。

## Tracks：3 条

- JAR：tracks-neoforge-1.21.1-1.0.1.jar；SHA-256 B126B2522A129C13EBEC6491B8602726BAD9A3DF201CF906468BA583796125C8。
- 三个 loot table 的物品名及 random_sequence 使用非法大写命名空间 Tracks:；正确命名空间是 tracks:。
- 同一个 JAR 还有 13 处 Tracks:（6 个 JSON）：3 个 mineable/safe_nbt block-tag 文件因此产生 Attempt6 的 3 条 TagLoader ERROR；这是同一根因，必须一起修。
- 推荐修复：6 个 JSON 全部只做 ASCII 大小写替换 Tracks:→tracks:；不删方块/配方。

## Minecraft / Nova：2 条

- JAR：DnT-ancient-city-overhaul-v2 [NeoForge].jar；SHA-256 890882EC1239FFF1CD5CC5F1DA1FE4BE98A31E748D418220BEE5F2B9F3D8FD91。
- illager_mansion/library_chest 与 secret_room 的 enchant_randomly.options 指向不存在的 nova_structures:illagers_bane；当前 JAR 自带 3 个 Nova loot table 和 1 个 item modifier，但没有该 enchantment。
- 推荐修复：保留两个 chest loot pool，只移除/条件化这一个失效附魔函数；不要整表删除。确切替代附魔尚未从当前包证实，故语义上标为 blocker。

## Iron’s Spells：1 条

- JAR：irons_spellbooks-1.21.1-3.15.6.jar；SHA-256 BA1F1986CA706AE348CB6FCE6E383AB7CC61C375826CCF0E4D3A88ED2F9FCD3D。
- 资源位于 data/irons_spellbooks/loot_table/test/ring_gen_break_me.json，内部没有引用；spell_filter:[none] 触发解析失败。
- 推荐修复：删除该孤立测试资源，或改为永不加载；不影响生产玩法。

## 发布前顺序

1. 先修 Tracks 的大小写（同时修 3 个 tag），这是已确认的 TagLoader ERROR。
2. 修 Railways 276 个可选 loot 条件；修 Create Connected 16 个 Dye Depot loot 条件及 35 个可选 tag 条目。
3. 删除/禁用 Iron’s Spells 测试表。
4. 对 Nova 两表做单独语义审核后再发布；若只求启动无 ERROR，可先移除失效附魔函数并保留书本掉落。
5. 服务器/客户端重新生成完全相同的 JAR，做一次全量 reload/startup gate；不要在当前 Attempt6 runtime 上复用。

## 证据索引

- 完整 298 条逐条记录、资源 entry SHA、日志行号、依赖状态及静态同族检查：见同目录 loot298-audit.json。
- Attempt6 TagLoader 相关行：见 JSON 的 log_corroboration.tracks_tagloader_error_lines。
- 当前 Attempt6 运行时没有 matching loose datapack 覆盖，见 JSON 的 loose_datapacks。

