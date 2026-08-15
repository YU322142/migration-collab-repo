# WorldEdit 7.3.8 NeoForge direction-property compatibility fix

Audit date: 2026-08-14 (Asia/Shanghai)

## Finding

Attempt6's server log reports:

```text
java.lang.ClassCastException: class java.lang.String cannot be cast to
class com.sk89q.worldedit.util.Direction
 at com.sk89q.worldedit.neoforge.internal.NeoForgeTransmogrifier
    .transmogToMinecraftProperties(NeoForgeTransmogrifier.java:101)
```

The error is deterministic and independent of the migrated world. Minecraft 1.21.1's `Property.equals/hashCode` considers a generic `EnumProperty<Direction>` and a `DirectionProperty` with the same name and value set equivalent. WorldEdit 7.3.8's `PROPERTY_CACHE` only recognizes the latter as directional. If a generic direction property is cached first, a later `DirectionProperty` obtains the cached WorldEdit `EnumProperty<String>`. During the reverse conversion, WorldEdit casts that string to `com.sk89q.worldedit.util.Direction` and fails.

The Attempt6 mod set contains 12 generic `EnumProperty<Direction>` fields (including Aeroworks, the content backport, Copycats, Frequency, KaleidoTavern, Railways, SimpleTomb, and TradeWorks), so removing one mod would not be a durable fix.

## Fix

`NeoForgeTransmogrifier` now treats any Minecraft `EnumProperty` whose `getValueClass()` is `net.minecraft.core.Direction` as directional in all three relevant paths:

1. Minecraft property → WorldEdit property cache.
2. Minecraft block-state values → WorldEdit values.
3. WorldEdit block-state values → Minecraft values.

This is the narrow compatibility logic used by the official WorldEdit 7.3.x line for newer NeoForge mappings, backported without changing gameplay resources or mod metadata. No broad exception suppression or fallback coercion is used.

## Artifact

Use the same JAR on both the dedicated server and the paired client:

`D:\Trans\migration-audit-work\worldedit-738-direction-property-fix-artifacts-20260814\worldedit-mod-7.3.8-direction-property-fix.1.jar`

| Field | Value |
|---|---|
| Size | 6,264,309 bytes |
| SHA-256 | `8EB5E39AA914EB1B09307B6C004478BD1263655FCCA880580673481EBFEF9283` |
| Internal WorldEdit version | 7.3.8 |
| Original Attempt6 SHA-256 | `5E7752C97876D87411E3760BCC573CC431F43C453722E6959FA7FE54DB1B01CA` |

The artifact is a replacement for `worldedit-mod-7.3.8.jar`; keep the filename expected by the mod loader if installing manually. Do not place both the original and fixed JAR in the same `mods` directory.

## Scope/diff audit

- 2,588 JAR entries before and after.
- No duplicate entries.
- Exactly two content entries differ: `NeoForgeTransmogrifier.class` and its anonymous cache-loader class `$1.class`.
- All gameplay resources, mixins, metadata, translations, and bundled libraries are byte-identical.
- No server/client launch was performed by this subtask; Attempt6 was not modified.

## Reproducibility

Build script:

`D:\Trans\migration-audit-work\worldedit-738-direction-property-fix-artifacts-20260814\build_worldedit_738_direction_fix.ps1`

The script compiles with Java 21, patches two class entries, validates the JAR, and builds twice with a fixed ZIP timestamp. Both independent builds produced:

`8EB5E39AA914EB1B09307B6C004478BD1263655FCCA880580673481EBFEF9283`

Source hash:

`A457E1A08890C515F8942A554FD940B3A293B935262401F9C91879CF55401F79`

## Offline regression test

Test script:

`D:\Trans\migration-audit-work\worldedit-738-direction-property-fix-artifacts-20260814\test_worldedit_738_direction_fix.ps1`

The test creates equivalent generic/dedicated Minecraft direction properties without bootstrapping a game, then loads the original and fixed JAR in separate JVMs.

- Original: reproduces `EnumProperty<String>` for both cache lookups (`fixed=false`).
- Fixed: returns `DirectionalProperty` for both lookups (`fixed=true`).
- Ordinary enum, boolean, and integer property mappings remain unchanged.
- Java/Minecraft launch result: not launched; this is a classpath-only regression probe.

## Installation handoff

Apply the fixed artifact identically to the next fresh paired server/client runtime, update the exact hash lock in the startup gate, and leave MCModSync disabled as requested. Do not mutate frozen Attempt6 directories. After the replacement is installed, the parent startup/join gate should specifically assert that the previous `String -> Direction` stack trace is absent and that WorldEdit reaches platform-ready initialization.
