# Project status and acquisition matrix

Snapshot date: 2026-09-06.

This page classifies migration adaptations, maintained forks, patches, and
tools. It is not a list of every upstream mod in the pack. The classification
uses the current 1.21.1 pack catalog, the current server gameplay chain, and
published releases:

- **Used in the current pack**: still used by the current server, client pack,
  or release workflow.
- **Used historically**: used only by an older pack, loader, migration stage,
  reproduction, or review; not required by the current server.
- **Direct-download release**: the repository has a verifiable JAR or plugin
  asset in a release, and the page should link to that asset directly.
- **Build/assemble locally**: the repository provides source, datapack,
  overlay, patch, or script material; follow its README and license and supply
  any authorized upstream files before building.

## Used in the current pack

### Direct-download releases

| Project | Purpose | Available asset |
| --- | --- | --- |
| MineAstr NeoForge | Server/client chat, image, and cross-language integration | `YU322142/MineAstr` `v0.6.30` JAR |
| MineAstr AstrBot plugin | Lets AstrBot receive, translate, and relay server messages | `YU322142/MineAstr` `astrbot-v0.6.30` ZIP |
| Immersive Paintings × MineAstr | Sends framed images through the MineAstr image/translation path | `YU322142/ImmersivePaintings` `0.7.15+1.21.1` JAR |
| Tom's Simple Storage stability fork | Fixes large storage networks, restart recovery, capacity, and recipe transfer | `YU322142/Toms-Storage` `neoforge-1.21.1-2.3.0-perf5.2` JAR |
| Chest Colorizer NeoForge | Adds client-side chest/barrel colors while preserving the vanilla default barrel | `YU322142/Chest-Colorizer-NeoForge` `v1.6.1-equivalence.3` JAR |
| CC:Tweaked Startup/Shutdown Guard | Protects computer cold-start and shutdown state | `YU322142/CCTweaked-Startup-Shutdown-Guard` `v1.0.0-equivalence.1` JAR |
| Create Chute Unload Guard | Restores chute-unload boundaries and prevents conversion item loss | `YU322142/Create-Chute-Unload-Guard` `v1.0.0-equivalence.1` JAR |
| Deferred Content Protection | Safely loads deferred content when a complete implementation is unavailable | `YU322142/Deferred-Content-Protection` `v1.0.0-first-release.1` JAR |
| Hardcore Revival Death Message Fix | Suppresses premature rescue-window death text while retaining the final death message | `YU322142/Hardcore-Revival-Death-Message-Fix` `v1.0.0-neoforge.1.21.1` JAR |
| Heightmap 384→544 Compat | Converts legacy heightmaps for the expanded build height | `YU322142/Heightmap-384-to-544-Compat` `v1.0.0-neoforge.1.21.1` JAR |
| Kaleidoscope Cookery Scarecrow Compat | Migrates legacy scarecrow entity NBT and equipment slots | `YU322142/Kaleidoscope-Cookery-Scarecrow-Compat` `v1.0.0-candidate13.1` JAR |
| Kaleidoscope Nether Backport | Backports required Nether content to NeoForge 1.21.1 | `YU322142/Kaleidoscope-Nether-Backport` `v1.1.9-equivalence.3` JAR |
| Mishang UC Pale Oak Equivalence | Restores Pale Oak building capabilities on 1.21.1 | `YU322142/MishangUC-Pale-Oak-Equivalence` `v1.6.3-equivalence.1` JAR |
| Potted Farms 1.21.1 Equivalence | Provides datapack equivalence for potted-farm durability rules | `YU322142/Potted-Farms-1.21.1-Equivalence` `v1.1.1-equivalence.3` JAR |
| Migration Resource Error Overlay | Repairs migration-pack resource gaps as an overlay | `YU322142/Migration-Resource-Error-Overlay` `v1.2.0-candidate13` JAR |
| Waypoint and Fire Rule Equivalence | Backports waypoint and fire rules for client/server consistency | `YU322142/Waypoint-Fire-Equivalence` `v0.1.1` JAR |

### Build/assemble locally

| Project | Purpose | Form |
| --- | --- | --- |
| Create Carriage Orientation Guard | Keeps carriage orientation decisions consistent with the migrated server | NeoForge source |
| Create Carriage Orientation Guard | Keeps carriage orientation decisions consistent with the migrated server | NeoForge source (current p0.2; no public JAR yet) |
| Nautilus Equivalence | Provides a 1.21.1 equivalence implementation for Nautilus and Zombie Nautilus | Internal source/build; no public JAR because it contains upstream backport material |
| WorldEdit Direction Property Fix | Fixes WorldEdit direction properties with a reproducible verification flow | Patch/scripts |
| Yuushya 2.3.0 Patchouli Safety | Provides the Yuushya Patchouli safety overlay | Overlay/scripts |

## Used historically

### Direct-download releases

| Project | Purpose | Notes |
| --- | --- | --- |
| MCSync / MCModSync | Legacy client file synchronization and OTA | `YU322142/MCSync` is archived; `v2.0.3`, `v1.9.6`, and earlier releases are historical only |
| Create Enchantment Industry | Enchantment-industry gameplay from the Fabric 1.21.11 era | Legacy pre-release JAR, for reproduction only |
| Create: Dragons Plus | Dragon-content expansion from the Fabric 1.21.11 era | Legacy pre-release JAR, for reproduction only |
| Create Dynamic Blocking | Backports the dynamic-blocking semantics used during migration | `YU322142/Create-Dynamic-Blocking` `v1.0.0-equivalence.1` JAR, for reproduction only |
| Create SavedData Probe | Inspects Create SavedData migration state | `YU322142/Create-SavedData-Probe` `v1.0.0` JAR, for audit only |
| POI Migration Diagnostic | Checks point-of-interest state after world migration | `YU322142/POI-Migration-Diagnostic` `v0.1.0` JAR, for audit only |
| Recipe Set Diagnostic | Reports recipe sets to verify gameplay migration completeness | `YU322142/Recipe-Set-Diagnostic` `v1.0.0` JAR, for audit only |

### Build/assemble locally

| Project | Purpose | Form |
| --- | --- | --- |
| TLM Patchouli Spawn Box Balance | Adjusts quest-book spawn-box balance | Overlay/scripts |
| XiyusLogin Auto-Session OTA | Provides preview, backup, and rollback flow for login-config OTA | PowerShell scripts |
| Kaleidoscope Tavern: Refabricated | Tavern-content port from the Fabric 1.21.11 era | Source |
| Legacy MCModSync material | Keeps 1.9.x compatibility notes and examples | Documentation/configuration, not a standalone mod |

## Usage rules

1. For current projects with releases, use the direct asset shown by the page;
   do not treat a source archive as a JAR.
2. For current projects that provide only source, data, or overlays, build each
   project independently according to its README. Do not repackage third-party
   JARs from a running pack.
3. Historical projects exist for legacy reproduction or review; installing a
   historical release does not replace the current pack.
4. There is one public MCSync repository: `YU322142/MCSync`. It is archived;
   no second same-name repository is being created.
5. Collaboration repositories, diagnostics, and migration scripts are not
   player-required mods; they support development, verification, and operations.
