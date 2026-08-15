# 1.21.11 riding-stat compatibility

## Root cause

Minecraft 1.21.11 registers `minecraft:happy_ghast_one_cm` and
`minecraft:nautilus_one_cm` in the custom-stat registry with the distance
formatter. Vanilla 1.21.1 knows neither ID. Loading migrated player stat JSON
therefore logged `Invalid statistic` and discarded the affected in-memory
counter for that load.

The earlier `equivalence.1` JAR restored Happy Ghast entity behavior but did
not restore this registry surface. Entity compatibility and registry
compatibility must be audited separately; a successful entity smoke is not
evidence that player statistics are lossless.

## Preserved semantics

The 1.21.11 `ServerPlayer.checkRidingStatistics` implementation computes:

```text
Math.round((float) sqrt(dx*dx + dy*dy + dz*dz) * 100.0F)
```

It awards that value to `happy_ghast_one_cm` for a Happy Ghast vehicle and to
`nautilus_one_cm` for any Abstract Nautilus vehicle. The latter includes both
`minecraft:nautilus` and `minecraft:zombie_nautilus`.

This module registers both custom-stat IDs during NeoForge's custom-stat
`RegisterEvent`, initializes both with `StatFormatter.DISTANCE`, and injects at
the tail of the 1.21.1 riding-stat method. Vehicle recognition uses only the
entity registry ID, so the logic has no class linkage to the Nautilus module.

## Regression gates

Run `gradlew.bat clean check jar`. `check` executes a dependency-free test of
the exact float rounding, movement gate, and all three vehicle-ID mappings.
A release build must also satisfy all of the following:

1. Two independent `clean check jar` runs produce the same SHA-256.
2. A fresh target server startup emits no `Invalid statistic` lines while all
   migrated player stat files remain byte-for-byte unchanged on disk.
3. A controlled ride test increments the Happy Ghast, Nautilus, and Zombie
   Nautilus counters by the same deltas observed on 1.21.11.
4. The JAR is installed on both server and client because the mod is side BOTH.

Never validate this by editing or starting the production source backup. Use a
fresh candidate copy and the established atomic candidate-bundle replacement
workflow.
