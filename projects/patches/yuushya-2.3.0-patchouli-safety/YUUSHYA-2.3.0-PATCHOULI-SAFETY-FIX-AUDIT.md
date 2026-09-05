# Yuushya 2.3.0 Patchouli 指南书安全补丁审计

日期：2026-08-14  
范围：`yuushya-1.21.0-neoforge-2.3.0.jar` 里 `yuushya:yuushya_guidebook` 的 `assets/` 与 `data/` 双份指南资源。  
边界：未启动 Minecraft；未修改 Attempt9、生产目录、世界、配置、端口、注册表或 Java 类。

## 结论

Attempt9 客户端已经进入世界并收到服务端同步数据，随后 Patchouli 编译 Yuushya 指南书时遇到已不在 Yuushya 2.3.0 实际物品注册表中的旧建模物品。`yuushya:get_showblock_item` 位于 `spotlight.item`，因此不是普通图标警告，而是导致整本 `yuushya:yuushya_guidebook` 编译失败并退化为空内容的直接原因。

本补丁仅替换无效的 `icon` / `spotlight.item` 显示引用：旧建模工具显示为 `minecraft:barrier`，旧百科显示为 `minecraft:book`。指南正文、标题、分类、页序、所有配方引用和玩法代码均保持原样。这样既解除当前编译失败，也不伪造物品、配方或世界数据。

服务端与客户端必须使用同一个补丁 JAR，且各自只保留一个 Yuushya JAR。虽然故障发生在客户端渲染线程，BOTH-side 配对能避免后续清单漂移。

## 注册表审计依据

对照来源：

- `data/yuushya/register/items.json` 的数据驱动物品注册；
- `data/yuushya/register/block_*.json` 与 `texture.json` 的方块及方块物品注册；
- `YuushyaRegistries.registerAll()` 字节码中的三个硬编码物品：`form_trans_item`、`blockstate_update_item`、`pilatory`；
- Attempt9 客户端运行时 Patchouli 的 `Unknown item` 日志。

指南中仍有效、保持不变的显示引用：

- `yuushya:facility_blueprint`
- `yuushya:extra_shapes_blueprint`
- `yuushya:a_pink_blindwall`
- `yuushya:oriental_lantern`

无效显示引用的完整映射：

| 原引用 | 补丁显示引用 | 双份字段数 |
|---|---|---:|
| `yuushya:pos_trans_item` | `minecraft:barrier` | 10 |
| `yuushya:get_showblock_item` | `minecraft:barrier` | 4 |
| `yuushya:rot_trans_item` | `minecraft:barrier` | 2 |
| `yuushya:scale_trans_item` | `minecraft:barrier` | 2 |
| `yuushya:slot_trans_item` | `minecraft:barrier` | 4 |
| `yuushya:get_blockstate_item` | `minecraft:barrier` | 2 |
| `yuushya:micro_pos_trans_item` | `minecraft:barrier` | 2 |
| `yuushya:get_lit_item` | `minecraft:barrier` | 2 |
| `yuushya:the_encyclopedia` | `minecraft:book` | 4 |

总计修改 32 个显示字段，分布在 14 个 `assets/` / `data/` 镜像 JSON 条目中。

## 配方引用全量审计

指南引用的 23 个 Yuushya 配方中，JAR 当前提供 6 个：

- `yuushya:block_blueprint`
- `yuushya:extra_shapes_blueprint`
- `yuushya:facility_blueprint`
- `yuushya:form_trans_item`
- `yuushya:furniture_blueprint`
- `yuushya:sign_blueprint`

JAR 当前未提供 17 个：

- `yuushya:dailylife_stuff_blueprint`
- `yuushya:deco_blueprint`
- `yuushya:everlasting_wood`
- `yuushya:floating_bloom`
- `yuushya:get_blockstate_item`
- `yuushya:get_lit_item`
- `yuushya:get_showblock_item`
- `yuushya:micro_pos_trans_item`
- `yuushya:move_transformdata_item`
- `yuushya:pos_trans_item`
- `yuushya:rot_trans_item`
- `yuushya:scale_trans_item`
- `yuushya:shimmering_pearl`
- `yuushya:slot_trans_item`
- `yuushya:sparking_flame`
- `yuushya:sprouting_dirt`
- `yuushya:the_encyclopedia`

这些配方引用被刻意保留。Patchouli 对缺失配方只记录非致命警告；删除或重定向它们会让将来通过 OTA 安装 Yuushya 建模扩展后，原指南无法自动重新关联内容，也可能把错误配方展示给玩家。补丁因此只修复会让整本书编译为空的 ItemStack 字段，并将配方缺口完整记录为后续 OTA 项。

## 构建产物

原始 JAR：

- 路径：`<AUDIT_ROOT>\mechanomania-matched-client-attempt9-20260814\mods\yuushya-1.21.0-neoforge-2.3.0.jar`
- 大小：28,197,448 bytes
- SHA-256：`C410C51E1ECDD9D3FF55EB34B84D71DA761A8990EC0993A766C9BA40E8C360E8`

补丁 JAR（发布候选）：

- 路径：`<AUDIT_ROOT>\yuushya-230-patchouli-fix-artifacts-20260814\yuushya-1.21.0-neoforge-2.3.0-patchouli-safe.1.jar`
- 大小：28,197,402 bytes
- SHA-256：`31DFFD39D1FED94F2088405AF3B8DC862E363BA389015780355571ECCA4A813D`

第二次独立构建：

- 路径：`<AUDIT_ROOT>\yuushya-230-patchouli-fix-artifacts-20260814\yuushya-1.21.0-neoforge-2.3.0-patchouli-safe.2.jar`
- 大小：28,197,402 bytes
- SHA-256：`31DFFD39D1FED94F2088405AF3B8DC862E363BA389015780355571ECCA4A813D`

两次构建逐字节一致。

## 静态验证

验证脚本：

- `<AUDIT_ROOT>\yuushya-230-patchouli-fix-artifacts-20260814\test_yuushya_230_patchouli_fix.py`
- SHA-256：`B418939BD4E1F5CF2A81A5B16E25C2A8829280931E9882C143F97E8C8F37FEEF`

执行结果：

```text
PASS: Yuushya 2.3.0 Patchouli safety patch
original_sha256=C410C51E1ECDD9D3FF55EB34B84D71DA761A8990EC0993A766C9BA40E8C360E8
patched_sha256=31DFFD39D1FED94F2088405AF3B8DC862E363BA389015780355571ECCA4A813D
zip_entries=54695
changed_entries=14
mapped_stack_fields=32
valid_recipe_refs=6
missing_recipe_refs_preserved=17
```

验证覆盖：

- 两次构建逐字节相同；
- ZIP 无重复条目，前后均为 54,695 个条目；
- 未新增或删除任何 JAR 条目；
- 解压内容仅 14 个指南 JSON 条目发生变化；
- 除 `icon` / `item` 的上述 32 个精确映射外，所有正文、结构、配方引用及其余文件逐字节不变；
- `assets/` 与 `data/` 指南副本逐字节镜像；
- 补丁后指南中不存在上述 9 个失效 ItemStack 引用；
- 所有 JSON 均可解析；
- 构建脚本重新构建得到相同 SHA-256。

可复现构建脚本：

- `<AUDIT_ROOT>\yuushya-230-patchouli-fix-artifacts-20260814\build_yuushya_230_patchouli_fix.ps1`

补丁源文件位于同目录的 `patch-root\`，仅含 14 个需要覆盖的指南 JSON。

## 下一步运行门

在一个全新的、从未启动过 Java 的 disposable server/client 候选中：

1. 同时移除服务端和客户端原始 `yuushya-1.21.0-neoforge-2.3.0.jar`；
2. 同时放入 `.1.jar` 补丁产物，禁止原版与补丁版并存；
3. 保持 MCModSync 全局不启用，服务端不得安装 MCModSync；
4. 重新运行前台连接门；
5. 验收日志中不再出现 `Error loading and compiling book yuushya:yuushya_guidebook, using empty contents`，并确认指南不再为空。

此静态补丁本身不宣称运行门 PASS；需要新的 disposable Attempt 才能给出运行结论。
