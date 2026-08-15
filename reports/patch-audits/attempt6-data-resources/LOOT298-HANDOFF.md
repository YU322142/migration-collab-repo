# Loot 298 审计交接

已完成只读审计，未启动 Minecraft，未修改 Attempt6/frozen/生产。

产物：
- D:\\Trans\\migration-audit-work\\loot298-audit-20260814\\loot298-audit.json
- D:\\Trans\\migration-audit-work\\loot298-audit-20260814\\LOOT298-AUDIT.md

精确统计：Railways 276（BYG 84/TFC 60/Nature's Spirit 36/Biomes O' Plenty 30/Twilight Forest 24/Blue Skies 18/Create DD 12/Quark 9/Hexcasting 3）；Create Connected 16；Tracks 3；Minecraft/Nova 2；Iron's Spells 1。全部来自 5 个 JAR，loose datapack 命中 0。

关键结论：
- Railways：210 条旧顶层 conditions，66 条无条件；可保留，补/转换 NeoForge conditions。Recipes 276 条已有新条件，5 个 tags 的 276 条可选引用均 required:false。BYG 未来条件应兼容 byg 与 canonical biomeswevegone。
- Create Connected：16 个 Dye Depot loot 缺条件；保留并加 mod_loaded(dye_depot)。80 个 recipes 已正确 gated；35 个 block tags 缺 required:false，建议同步显式可选。
- Tracks：3 个 loot + 3 个 block tags 同一根因：Tracks: 大写命名空间，应统一为 tracks:；Attempt6 已有 3 条 TagLoader ERROR。
- DnT/Nova：2 个 illager mansion loot 仅 nova_structures:illagers_bane 附魔选项失效；保留 chest pools，移除/条件化该函数；替代附魔未知，属语义 blocker。
- Iron's Spells：test/ring_gen_break_me.json 孤立测试表，可删除/false-gate，不影响玩法。

建议修复顺序见 MD；JSON 含 298 条逐条记录、日志行号、entry SHA、源 JAR SHA、依赖状态和同族静态审计。

审计产物 SHA-256：loot298-audit.json = 2F20CBE230B0E052489C6456809E80C69A9AA4359828140543C0512D71C4F140；LOOT298-AUDIT.md = 8AEBC49CE03C354CC2D9733B4CAFF152CD05A58364A3471D25AA407582A5A6D6。
