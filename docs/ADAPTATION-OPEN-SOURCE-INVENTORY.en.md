# Mod adaptation and open-source inventory

Snapshot date: 2026-09-06. This is the collaboration entry point for the
server migration work: what was adapted, where the source lives, and what is
public versus still requiring licensing or redaction review. Use
`MODULE-FILE-INDEX.md` for file-level entry points and the catalog/refactor map
for abstract ownership boundaries.

## Latest first: Chest Colorizer

The final barrel-stability project is published separately:

- Local source: `outputs/projects/chest-colorizer-neoforge-1.21.1/`
- Public repository: `YU322142/Chest-Colorizer-NeoForge`
- Release: `v1.6.1-equivalence.3`
- Artifact: `chest-colorizer-1.6.1-equivalence.3+mc1.21.1-neoforge.jar`
- SHA-256: `EC8D9D3AAE816C5E0FAF46DFF284C63530E2460B4801D4F6E1EDF7120D8180A2`
- Entry points: `README.md`, `DEVELOPMENT.md`, `build.gradle`, and
  `src/main/java/net/immortaldevs/colorizer/`

This version keeps uncolored/default barrels in the original
`minecraft:barrel` state, applies the custom state only to explicitly colored
barrels, and makes Sodium and vanilla section rendering mutually exclusive. It
is client-only and does not belong on the server.

## Standalone public maintenance projects

| Project | Local project files | Public status |
| --- | --- | --- |
| MCSync (historical) | `projects/ports/mcsync-2.0.0/`; full working tree under the publication workspace | Public at `YU322142/MCSync`, development stopped and repository archived; `v2.0.3` is historical only |
| MineAstr NeoForge | Publication workspace `MineAstr` | Public at `YU322142/MineAstr`, current public version `v0.6.30` |
| MineAstr AstrBot plugin | Publication workspace `MineAstr-astrbot-plugin` | Public `astrbot-plugin` branch in `YU322142/MineAstr`, current public version `astrbot-v0.6.30` |
| Immersive Paintings × MineAstr | `projects/patches/immersive-paintings-mineastr-compat/` | Public at `YU322142/ImmersivePaintings`, current public version `0.7.15+1.21.1` |
| Tom's Storage port | `projects/ports/toms-storage-neoforge-1.21.1-perf-port/` | Public at `YU322142/Toms-Storage`, NeoForge version `neoforge-1.21.1-2.3.0-perf5.2`, subject to upstream terms |
| Chest Colorizer | `outputs/projects/chest-colorizer-neoforge-1.21.1/` | New public repository and release published |

### Newly published standalone repositories

All projects below were copied from clean source snapshots. Build caches,
JAR/ZIP artifacts, world data, and credentials were excluded.

| Project | GitHub repository | Publication boundary |
| --- | --- | --- |
| CC:Tweaked Startup/Shutdown Guard | `YU322142/CCTweaked-Startup-Shutdown-Guard` | Standalone NeoForge source, MIT |
| Create Carriage Orientation Guard | `YU322142/Create-Carriage-Orientation-Guard` | Standalone compatibility source, MIT; no Create JAR |
| Create Chute Unload Guard | `YU322142/Create-Chute-Unload-Guard` | Standalone compatibility source, MIT; no Create JAR |
| Create Dynamic Blocking | `YU322142/Create-Dynamic-Blocking` | Standalone compatibility source, MIT; no Create JAR |
| Create SavedData Probe | `YU322142/Create-SavedData-Probe` | Diagnostic source, MIT; no world data |
| Deferred Content Protection | `YU322142/Deferred-Content-Protection` | Standalone NeoForge source, MIT |
| Hardcore Revival Death Message Fix | `YU322142/Hardcore-Revival-Death-Message-Fix` | Standalone compatibility source, MIT; no upstream JAR |
| Heightmap 384→544 Compat | `YU322142/Heightmap-384-to-544-Compat` | Standalone compatibility source, MIT; no chunks/world |
| Kaleidoscope Cookery Scarecrow Compat | `YU322142/Kaleidoscope-Cookery-Scarecrow-Compat` | Standalone compatibility source, MIT; no upstream JAR |
| Kaleidoscope Nether Backport | `YU322142/Kaleidoscope-Nether-Backport` | Authored equivalence source/data, MIT; obey upstream terms |
| Mishang UC Pale Oak Equivalence | `YU322142/MishangUC-Pale-Oak-Equivalence` | Authored compatibility source, LGPL-3.0-or-later; no upstream JAR |
| POI Migration Diagnostic | `YU322142/POI-Migration-Diagnostic` | Diagnostic source, MIT; no POI/world snapshot |
| Potted Farms 1.21.1 Equivalence | `YU322142/Potted-Farms-1.21.1-Equivalence` | Authored datapack snapshot; no save or third-party artifact |
| Recipe Set Diagnostic | `YU322142/Recipe-Set-Diagnostic` | Diagnostic source, MIT; no save mutation |
| Migration Resource Error Overlay | `YU322142/Migration-Resource-Error-Overlay` | Authored resource fix source/data; no upstream JAR |
| Waypoint and Fire Rule Equivalence | `YU322142/Waypoint-Fire-Equivalence` | Standalone compatibility source, MIT; no server data |
| TLM Patchouli Spawn Box Balance | `YU322142/TLM-Patchouli-Spawn-Box-Balance` | Overlay/build/verification scripts only; no TLM JAR |
| WorldEdit Direction Property Fix | `YU322142/WorldEdit-Direction-Property-Fix` | Patch/build/verification scripts only; no WorldEdit JAR |
| XiyusLogin Auto-Session OTA | `YU322142/XiyusLogin-Auto-Session-OTA` | OTA scripts/docs only; no auth DB, credentials, or save |
| Yuushya 2.3.0 Patchouli Safety | `YU322142/Yuushya-2.3.0-Patchouli-Safety` | Overlay/build/verification scripts only; no Yuushya JAR |

## Complete adaptation project roots

These directories are source, compatibility layers, or verification projects;
they are not live server copies.

### `projects/ports/` — long-lived ports and equivalence lines

`barched`, `cei-2.4.2-with-2.5.1-backport`,
`content-backport-cat-serializer-fix`, `create-nerfad-1.21.1-neoforge`,
`end-client-harness`, `froglight-patch-1.21.1-equivalence`,
`happy-ghast-1.21.1-equivalence`, `hotbath-trigger-registry-fix`,
`kaleidoscope-cookery-1.21.1-neoforge`,
`kaleidoscope-end-1.21.1-equivalence`,
`kaleidoscope-nether-1.21.1-equivalence`, `kaleidoscope-tavern-1.21.1`,
`mcmodsync-1.9.2-pinned-source`, `mcsync-2.0.0`,
`mishanguc-1.21.1-equivalence`, `nautilus-alias-adapter`,
`nautilus-equivalence`, `nautilus-spears-tracked-source`,
`potted-farms-1.21.1-equivalence-full`, `respawn-pitch-compat`,
`toms-storage-neoforge-1.21.1-perf-port`, `trueuuid-login-proxy-fix`, and
`xiyuslogin-migration`.

### `projects/patches/` — focused compatibility patches

`immersive-paintings-mineastr-compat`, `tlm-patchouli-spawn-box-balance`,
`worldedit-7.3.8-direction-property-fix`, `xiyuslogin-auto-session-ota`, and
`yuushya-2.3.0-patchouli-safety`.

### `outputs/projects/` — maintained NeoForge mods and diagnostics

`cctweaked-startup-shutdown-guard-neoforge`,
`chest-colorizer-neoforge-1.21.1`,
`create-carriage-orientation-guard-neoforge`,
`create-chute-unload-guard-neoforge`, `create-dynamic-blocking-neoforge`,
`create-saveddata-probe`, `deferred-content-protection-neoforge`,
`hardcore-revival-death-message-fix-neoforge`,
`heightmap-384-to-544-compat-neoforge`,
`kaleidoscope-cookery-scarecrow-compat`, `kaleidoscope-nether-backport`,
`mishanguc-pale-oak-equivalence`, `poi-migration-diagnostic`,
`potted-farms-1.21.1-equivalence`, `recipe-set-diagnostic`,
`resource-error-overlay-1.21.1`, and `waypoint-fire-equivalence`.

### `pack/` and `outputs/tools/` — rules, scripts, and migration tooling

- Server rules/KubeJS: `pack/server-kubejs/`, `pack/server-config/`
- Client resources/KubeJS: `pack/client-kubejs/`, `pack/client-config/`
- Maid custom resources: `pack/common-tlm-custom-pack/`
- Terrain/height overlays: `pack/terrain-preservation-frontier-datapack/`,
  `pack/worldgen-height-544-overlay/`
- World, block-entity, storage, terrain, and player-data tooling:
  `outputs/tools/`
- Repository checks, manifests, redaction, and collaboration tooling:
  `tools/repository/`

## Publication boundary

### Safe to publish

- Code we wrote or are explicitly allowed to maintain.
- KubeJS/datapack/config templates, build scripts, tests, and synthetic audit
  fixtures.
- Architecture notes, module indexes, changelogs, and compatible license text.
- The maintained MineAstr, ImmersivePaintings, Tom's Storage, and Chest Colorizer
  repositories/releases, plus archived historical repositories such as MCSync;
  archived projects are reference-only and are not current client solutions.
- The standalone compatibility mods, diagnostics, and patch repositories listed
  above; projects without a binary release publish source only and are built
  locally under the applicable upstream terms.

### Do not publish directly

- Live worlds, chunks, entities, POI, SavedData, inventories, or auth databases.
- Real server addresses, RCON/API/TrueUUID credentials, tokens, private keys,
  or account bindings.
- Client instance directories, private caches, logs, and crash dumps.
- Mod JARs, modpack archives, resource packs, shaders, or model/texture assets
  whose upstream terms do not allow redistribution.
- One-off runtime snapshots; describe them only through a redacted index under
  `artifacts/`.

## Finding material that is not public

1. Start with `artifacts/EXTERNAL-ARTIFACTS.md`; use its purpose and SHA-256 to
   locate the external artifact on the owner's machine.
2. Use `docs/SOURCE-MAP.md` and `docs/MODULE-FILE-INDEX.md` to navigate source.
3. If a project has only a patch and no upstream source, confirm its license
   before copying or publishing any upstream code.
4. For live data, obtain a one-time redacted snapshot from the server owner;
   commit only the converter and a result summary.

## Pre-publication check

```text
python tools/repository/sanitize_snapshot.py
python tools/repository/check_repository.py
git diff --check
```

Public snapshots use stable placeholders such as `<WORKSPACE>`, `<AUDIT_ROOT>`,
`<HANDOFF_ROOT>`, `<INSTANCE_ROOT>`, and `<TRANS_ROOT>`. Any file that still
contains a real path, credential, identity, or unconfirmed third-party asset
stays local and must be called out in the handoff notes.
