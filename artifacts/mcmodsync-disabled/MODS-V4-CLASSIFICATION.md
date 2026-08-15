# Attempt13 MCModSync v4 模组分类

状态：`PASS_STATIC_CATALOG_NOT_ENABLED`。本目录只生成发布候选，未启用 MCModSync、未修改客户端或服务端。

- 活动客户端 JAR：249
- 清单玩法/依赖行：247
- 必须：170
- 推荐：77
- 引导组件排除：2（MCModSync 本体与 Config.jar）
- Manifest：`https://example.invalid/d/%E5%AF%B9%E5%A4%96/%E7%8B%AC%E5%AE%B6%E8%B5%84%E6%BA%90/MC%E6%9C%8D%E5%8A%A1%E5%99%A8/MODS%E8%87%AA%E5%8A%A8%E5%90%8C%E6%AD%A52.0/mods-v4.txt`
- 下载基址：`https://example.invalid/d/%E5%AF%B9%E5%A4%96/%E7%8B%AC%E5%AE%B6%E8%B5%84%E6%BA%90/MC%E6%9C%8D%E5%8A%A1%E5%99%A8/MODS%E8%87%AA%E5%8A%A8%E5%90%8C%E6%AD%A52.0/`

## 分类口径

- `required`：缺少会导致客户端不能启动、依赖不闭合、协议/注册表不匹配、不能入服，或进入迁移存档后触发已知恶性崩溃/数据风险。
- `recommended`：只影响客户端界面、地图、显示、诊断或性能；移除后仍可启动并进入服务器。
- 保守项按 `required` 处理；未来只有通过“删模组启动 + 真入服”负载门禁后才可降为推荐。

## 推荐模组

- `AlwaysEat-neoforge-1.0.0.jar` — Always Eat：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `appleskin-neoforge-mc1.21-3.0.9.jar` — AppleSkin：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `attributefix-neoforge-1.21.1-21.1.2.jar` — AttributeFix：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `BetterAdvancements-NeoForge-1.21.1-0.4.3.21.jar` — Better Advancements：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `biggerbetterendcities-1.21.1-1.0.0.jar` — BiggerBetterEndCities：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `biomespy-neoforge-1.21.1-1.3.3.jar` — BiomeSpy：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `c2me-neoforge-mc1.21.1-0.4.0-alpha.0.113.jar` — Concurrent Chunk Management Engine：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `cctweaked-startup-shutdown-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar` — CC Tweaked Startup and Shutdown Guard：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `chest-colorizer-1.6.1-equivalence.2+mc1.21.1-neoforge.jar` — Chest Colorizer：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `clientsort-neoforge-2.2.2+1.21.1.jar` — ClientSort：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `colorfulhearts-neoforge-1.21.1-10.5.9.jar` — Colorful Hearts：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `colorwheel-neoforge-1.2.9+mc1.21.1.jar` — Colorwheel：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `colorwheel_patcher-neoforge-1.0.5+mc1.21.1.jar` — Colorwheel Patcher：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `configured-neoforge-1.21.1-2.6.3.jar` — Configured：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `ConfiguredDefaults-v21.1.3-1.21.1-NeoForge.jar` — Configured Defaults：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `Controlling-neoforge-1.21.1-19.0.5.jar` — Controlling：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `create-chute-unload-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar` — Create Chute Unload Guard：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `create-nerfad-1.2.3-neoforge+mc1.21.1.jar` — Create: Not Enough Resources For A Dummy：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `createbetterfps-1.21.1-1.1.4.jar` — CreateBetterFps：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `CreateCyberGoggles-1.21.1-8.3.6-NeoForge.jar` — Create: Cyber Goggles：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `CreateFastSchematicCannon-1.4.1-neoforge-1.21.1.jar` — Create: Fast Schematic Cannon：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `disconnect-packet-fix-neoforge-2.0.1.jar` — Disconnect Packet Fix：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `DnT-ancient-city-overhaul-v2 [NeoForge].jar` — Dungeons and Taverns Ancient City Overhaul：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `do_a_barrel_roll-neoforge-3.7.3+1.21.jar` — Do a Barrel Roll：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `efficient_hashing-neoforge-1.0.0+1.21.1-mod.jar` — Efficient Hashing：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `enchdesc-neoforge-1.21.1-21.1.10.jar` — EnchantmentDescriptions：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `Epic Villages 1.3.0 (1.21+).jar` — Epic Structures: Villages：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `fastleafdecay-35.jar` — FastLeafDecay：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `fastrecipesearch-1.21.1-26.2-neoforge.jar` — Fast Recipe Search：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `fasttag-1.21.1-26.1-neoforge.jar` — Fast Tag：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `ferritecore-7.0.3-neoforge.jar` — Ferrite Core：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `flatbedrock-neoforge-87.0.0.jar` — Flat Bedrock：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `flerovium-neoforge-1.21.1-1.1.1-all.jar` — Flerovium：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `fragmentum-neoforge-1.21.1-2.1.1.jar` — Fragmentum：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `fusion-1.2.11b-neoforge-mc1.21.jar` — Fusion：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `ImmediatelyFast-NeoForge-1.6.11+1.21.1.jar` — ImmediatelyFast：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `iris-neoforge-1.8.13-snapshot+mc1.21.1-local.jar` — Iris：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `Jade-1.21.1-NeoForge-15.10.6.jar` — Jade：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `JadeAddons-1.21.1-NeoForge-6.1.0.jar` — Jade Addons：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `jecharacters-1.21-neoforge-4.5.24.jar` — Just Enough Characters：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `jei-1.21.1-neoforge-19.43.0.393.jar` — Just Enough Items：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `JustEnoughProfessions-neoforge-1.21.1-4.0.5.jar` — Just Enough Professions (JEP)：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `krypton_fnp-neoforge-1.21.1-0.2.28.1-1.21.1.jar` — Krypton FNP：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `lithium-neoforge-0.15.4+mc1.21.1.jar` — Lithium：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `lukis-crazy-chambers-1.0.2.jar` — Luki's Crazy Chambers：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `maxhealthfix-neoforge-1.21.1-21.1.4.jar` — MaxHealthFix：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `medieval_buildings_end_edition-1.21.1-1.0.4-neoforge.jar` — Medieval Buildings [The End Edition]：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `mes-1.3.5-1.21.jar` — Moog's End Structures：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `migration-resource-overlay-1.2.0+mc1.21.1-candidate13.jar` — Migration Resource Error Overlay：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `mineastr-neoforge-1.21.1-0.6.26.jar` — MineAstr：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `modernfix-neoforge-5.27.14+mc1.21.1.jar` — ModernFix：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `MouseTweaks-neoforge-mc1.21-2.26.1.jar` — Mouse Tweaks：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `noisium-neoforge-2.3.0+mc1.21-1.21.1.jar` — Noisium：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `obscure_tooltips-neoforge-1.21.1-4.2.2.jar` — Obscure Tooltips：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `packetfixer-3.3.1-1.20.5-1.21.X-merged.jar` — PacketFixer：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `particular-1.21.1-NeoForge-1.5.5.jar` — Particular Reforged：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `potted-farms-1.1.1-equivalence3.jar` — Potted Farms：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `repurposed_structures-7.5.17+1.21.1-neoforge.jar` — Repurposed Structures：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `resourcefulconfig-neoforge-1.21-3.0.11.jar` — Resourcefulconfig：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `respawn-pitch-compat-1.0.0+mc1.21.1.jar` — Respawn Pitch Compatibility：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `Searchables-neoforge-1.21.1-1.0.2.jar` — Searchables：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `serverwarashi-1.0.2.jar` — ServerWarashi：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `SimpleBackups-1.21-4.0.18.jar` — Simple Backups：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `smart_bounds-1.0.0.jar` — Create: Smart Bounds：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `smrb-1.0.0.jar` — SaveMyRecipeBook：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `smsn-neoforge-1.4.1-1.21.1.jar` — Save My Shit Network：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `sodium-neoforge-0.8.12-alpha.2+mc1.21.1.jar` — Sodium：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `spark-1.10.124-neoforge.jar` — spark：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `structure_layout_optimizer-neoforge-1.0.12.jar` — Structure Layout Optimizer：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `vanillin-neoforge-1.21.1-1.1.3-local.jar` — Vanillin：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `voicechat-neoforge-1.21.1-2.6.21.jar` — Simple Voice Chat：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `worldedit-mod-7.3.8-direction-property-fix.1.jar` — WorldEdit：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `wwoo-2.3.4.jar` — William Wythers' Overhauled Overworld：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `xaerominimap-neoforge-1.21.1-26.1.0.jar` — Xaero's Minimap：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `xaeroworldmap-neoforge-1.21.1-1.41.2.jar` — Xaero's World Map：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `xiyuslogin-1.4-migration4.jar` — XiyusLogin：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.
- `zfastnoise-1.0.12+1.21.1+neoforge.jar` — Fast Noise Mod：Client-only, UI/render/performance, server-only, or datapack-only; absence should not block entering the server.

## 引导组件（不进入玩法清单）

- `MCModSync-1.9.2.jar` `094BAC82A226545A37371A997EA9B7A9121E11D42D4CFD733FDB36E55681A8BD`：Publisher bootstrap; excluded from gameplay catalog and not enabled by the catalog.
- `MCModSync-Config.jar` `8FE87B233286EE596D942015197A4EA88EF74F1073D4CDAA17073BC0EAD98226`：Publisher bootstrap; excluded from gameplay catalog and not enabled by the catalog.

## 发布前仍需完成

1. 将本目录中的 247 个清单目标 JAR 按原文件名上传到下载基址。
2. 对远端逐文件做 SHA-256/MD5/重定向/Content-Length 审计。
3. 仅在远端内容完全就绪后，将经审计的 MCModSync 与 Config.jar 放入客户端并做两次金丝雀启动。
4. 服务端永远不安装 MCModSync。
