# Attempt6 error classification (WorldEdit excluded)

Evidence: `attempt6-server-errors-by-logger-20260814.txt` (SHA-256 `7C5F3B598FD7E9DA2E6B9956F115800365A1E11C4DE85DA993109AFA7288BD90`). No Minecraft process was started.

| Logger group | Count | Classification | Candidate status |
|---|---:|---|---|
| LootDataType | 298 | Optional Railways/Create Connected assets, Tracks namespace typo, DnT invalid Nova option, orphan Iron test table | 298 statically repaired; DnT replacement is a documented semantic-risk delta |
| BiomeGenerationSettings | 6 | Six malformed loose KubeJS biome JSONs (comma syntax) | Fixed in 7-file loose overlay (six biome files plus Curios) |
| DataMapLoader | 6 | Root-level optional condition uses wrong data-map schema | Fixed per-value `neoforge:conditions` + `neoforge:value` |
| RecipeManager | 4 | Four 1.21 recipe schema/optional dependency issues | Fixed in four JAR entries |
| TagLoader | 4 | Three Tracks namespace typos; one missing optional Kaleidoscope Twilight tag set | Fixed in Tracks and Tavern JAR entries |
| KubeJS | 1 | Duplicate symptom of the Tavern `create:upright_on_belt` missing references | Cleared by the same `required:false` tag repair |
| Curios API | 1 | Loose Touhou Little Maid override requests unregistered `scroll` slot | Removed only `scroll`; other current slots preserved |
| net.minecraft.Util | 1 | BiomeSpy path ends in U+200E | Renamed entry to valid path |
| RuntimeDistCleaner | 15 | Client-only class probes during dedicated-server transform; caught and startup proceeds | Benign/no safe resource patch; retain client code |
| RefmapRemapper | 1 | Connector bootstrap dummy `\~nonexistent` refmap open | Benign/no gameplay patch; accepted baseline |
| WorldEdit | 1 | Explicitly excluded per task; handled by another agent | Not included here |

## Remaining blockers / review items

1. The DnT/Nova candidate removes only the invalid `nova_structures:illagers_bane` function from two book entries. It preserves the book, weight, chest pools, and `nova_structures:loot_modifier`, but an exact replacement enchantment is not proven from the current dependency set.
2. Curios behavior depends on the corrected loose KubeJS file winning the resource-pack merge over the base Touhou Little Maid entry; a later isolated reload/startup gate must verify slot ordering.
3. RuntimeDistCleaner and RefmapRemapper lines are expected noisy diagnostics, not evidence of a data-loss path.
