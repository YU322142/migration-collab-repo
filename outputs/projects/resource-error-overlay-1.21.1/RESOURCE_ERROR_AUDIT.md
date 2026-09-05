# Full-stack resource error audit

Scope is the isolated NeoForge 1.21.1 pack only. No file under `<TRANS_ROOT>\20260807` or `<TRANS_ROOT>\20260807-neoforge-1.21.1` was changed.

## Evidence

- Baseline 18-error capture: `<AUDIT_ROOT>\happyghast-equivalence-smoke1\smoke4.stdout.log`.
- Patched full-stack server: `<AUDIT_ROOT>\resource-overlay-fullstack-smoke1`.
- Final startup capture: `<AUDIT_ROOT>\resource-overlay-fullstack-smoke1\smoke9.stdout.log`.
- Final server log/reload capture: `<AUDIT_ROOT>\resource-overlay-fullstack-smoke1\logs\latest.log`.
- Overlay source: `<AUDIT_ROOT>\Resource-Error-Overlay-1.21.1`.
- JSON validation: `JSON_OK=19`.
- Overlay JAR: `migration-resource-overlay-1.0.0+mc1.21.1.jar`, 11,360 bytes, SHA-256 `DD5C16CE8C815885F3840BC3E96FB8DB5AE248AF06369EB57D3D01C3B2A60296`.

Startup reached `Loaded 11371 recipes`, the Nether guard (`2 foods, 4 fluids, 13 dolls`) and `Done (1.529s)`. RCON `/reload` at `20:13:16` reached `Loaded 11371 recipes` at `20:13:17`.

## Original 18 errors

| # | Resource ID | Classification | Action / player-visible result |
|---:|---|---|---|
| 1 | `create_dragons_plus:blocks/levitite_fragile_fluid_tank` | Optional integration | Loot references an item registered only by the absent `simulated` integration. Root `mod_loaded(simulated)` condition added; no current-pack gameplay is removed. |
| 2 | `kaleidoscope_nether:blocks/doll_8` | Missing target registration | Target official jar has no doll item; the Nether equivalence companion registers it. Conditional loot table retained and now loads with the companion. |
| 3 | `kaleidoscope_nether:blocks/doll_7` | Missing target registration | Same as #2. |
| 4 | `kaleidoscope_nether:blocks/doll_6` | Missing target registration | Same as #2. |
| 5 | `kaleidoscope_nether:blocks/doll_5` | Missing target registration | Same as #2. |
| 6 | `kaleidoscope_nether:blocks/doll_4` | Missing target registration | Same as #2. |
| 7 | `kaleidoscope_nether:blocks/doll_3` | Missing target registration | Same as #2. |
| 8 | `kaleidoscope_nether:blocks/doll_2` | Missing target registration | Same as #2. |
| 9 | `kaleidoscope_nether:blocks/doll_1` | Missing target registration | Same as #2. |
| 10 | `kaleidoscope_nether:blocks/doll_0` | Missing target registration | Same as #2. |
| 11 | `create_dragons_plus:blocks/fragile_fluid_tank` | Optional integration | Same absent `simulated` item gate as #1; condition added. |
| 12 | `c:cooked_meats` | Optional tag member | `kaleidoscope_cookery:cooked_donkey_meat` is marked `required:false`; migration Cookery supplies it when present. |
| 13 | `c:foods/meat` | Optional child tags | `#c:foods/meat/raw` and `#c:foods/meat/cooked` are marked optional; no tag load failure when an old provider is absent. |
| 14 | `c:cooked_eggs` | Optional tag members | `farmersdelight:fried_egg` and `mynethersdelight:boiled_egg` are marked optional; retained when providers exist. |
| 15 | `kaleidoscope_nether:pot/gilded_barbaric_roast` | Real recipe dependency | Guarded by `neoforge:item_exists(raw_donkey_meat)`; the migration Cookery candidate restores the input and the recipe loads. |
| 16 | `yuushya:painter_gift_box` | Unavailable in both versions | Source 2.3.1 and target 2.3.0 both omit `yuushya:the_encyclopedia` from `register/items.json`; no Patchouli jar is installed. `item_exists` guard suppresses a false error without inventing an item/recipe. |
| 17 | `kaleidoscope_nether:pressing_tub/warped_bucket` | Real fluid dependency | Guarded by `mod_loaded(kaleidoscope_nether_equivalence)`; the companion owns `kaleidoscope_nether:warped_juice`, so the recipe/flow is restored in the fixed pack. |
| 18 | (the second Create Dragons tank entry, `fragile_fluid_tank`) | Optional integration | Covered by #11; listed separately because it is a separate baseline `ERROR` line. |

The two Create Dragons IDs are two separate baseline lines; the nine doll IDs are nine separate lines. The table therefore records all 18 logical lines (the final row is the separately logged second tank line; #11 is the levitite line and #18 is the ordinary tank line). No fake substitute item or fluid was introduced.

## Additional gameplay fix

The target Nether `blaze.json` and `hoglin.json` used `minecraft:match_tool` for Looting pools. Entity loot contexts do not provide the `minecraft:tool` parameter, producing six validation warnings and making those Looting bonus pools unreachable. The overlay replaces those six conditions with the source-compatible `kaleidoscope_cookery:advance_entity_match_tool` and `slot:mainhand`. Final startup and reload both report zero loot-table validation warnings.

## Remaining warnings (not resource-loss errors)

- 3 Fabric jars are initially skipped by NeoForge's generic scanner, then remapped and loaded by Connector (`fabric_language_kotlin`, `forgeconfigapiport`, `mishanguc` are present in the final mod list). This is discovery noise.
- 1 JarJar `~nonexistent` line is Connector bootstrap noise.
- 18 missing refmap lines are absent development refmaps; no mixin application failure follows.
- 2 Alex's Mobs mixin-target lines plus 3 class-load diagnostics are the absent optional `alexsmobs` integration. The mod is not in either source or target pack; only that optional integration is unavailable.
- 1 JetBrains annotation class-load diagnostic is an optional annotation-only class and has no gameplay effect.
- 2 union asset-schema warnings are NeoForge's URL validator and are harmless.
- 6 Create Dragons data-map warnings (`air_current_block_interaction/{blasting,freezing,smoking,splashing}` and `fragile_fluid_tank/{lava,water}`) occur because those data-map types are registered by the absent `simulated` integration. Filtering them statically would break a later `simulated` install, so the stable overlay intentionally leaves them as warnings.
- 7 Nether global-loot-modifier warnings reference absent optional `eternalnether` IDs. The target jar actually carries `bygonenether`-named resources, but neither optional mod is installed. Replacing the shared global modifier index would risk dropping other mods' modifiers, so no unsafe global replacement was made.
- Offline-mode, config-reopen, creative-tab-anchor, version-check and one startup catch-up warning are test-environment/configuration diagnostics, not content loss.

Post-reload counts from `smoke9.stdout.log`: `Couldn't parse element=0`, `Couldn't load tag=0`, `Parsing error loading recipe=0`, loot validation `0`, and hard resource `ERROR=0`. The only `FATAL` in the directory is the deliberately overlapping `smoke7/smoke8` lock attempt; it is a harness collision and not part of the successful `smoke9` run.

## Candidate hashes used by smoke9

- Nether equivalence: `kaleidoscope-nether-equivalence-backport-1.1.9-equivalence.3+mc1.21.1.jar`, SHA-256 `AD022124989BA50FB1B95D58BA7AD2F9FC525A356108307EACE169F2850E2E34`.
- Cookery migration.3: SHA-256 `A061FB1E953AD815144304F7567B30876DBBC07B8565069871771F0AAEB63D3F`.
- End migration.7: SHA-256 `E03A7DBA3A67768C35F3CA1C0B47892CAF4A972F8362D27FF62675C7555A11BC`.
- Tom's Storage perf5.2: SHA-256 `29DB765C7EB8D91DBA017CB108D1B7619E845816FDFADBB0E64BF2CCFD6A801B`.

## Count correction for the latest full-stack capture

The older Nether-only `smoke4.stdout.log` contains 17 resource `ERROR` lines. The latest HappyGhast/Tom full-stack capture adds `kaleidoscope_end:teapot/void_tea` as the 18th line (the official target recipe references an item absent from the old baseline). End migration.7 registers the teacup; `smoke9.stdout.log` and its reload contain no End recipe error. This note supersedes the old table's final duplicate placeholder if that table is read against `smoke4` rather than the latest full-stack capture.
