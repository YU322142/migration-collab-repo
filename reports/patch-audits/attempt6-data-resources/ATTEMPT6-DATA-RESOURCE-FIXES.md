# Attempt6 data/resource repair candidate (2026-08-14)

Scope: read-only audit-derived candidate. Minecraft was not started and the Attempt6 runtime, frozen staging, production, and Prism were not modified.

## Applied candidate changes

- Six malformed KubeJS biome JSONs: comma-only syntax repairs.
- KubeJS Touhou Little Maid Curios override: remove unregistered `scroll` slot.
- Create Additional Logistics data map: move `numismatics` condition to each value.
- Create Compressed/Create Deco recipes: 1.21 schema fixes.
- Package Couriers recipe: fail-closed `create_factory_logistics` condition.
- Railways: 276 optional loot tables gated with NeoForge conditions; legacy conditions converted; BYG accepts `byg` or `biomeswevegone`.
- Create Connected: 16 Dye Depot loot tables gated with `dye_depot`. Existing 35 related tag files were audited; their optional entries are already `required:false`, so no unnecessary tag rewrite was made.
- Tracks: lowercase `Tracks:` in all six affected JSON entries (3 loot + 3 tags).
- Create Gears & Tavern: mark 14 absent Kaleidoscope Twilight tag entries `required:false`.
- BiomeSpy: rename malformed U+200E-suffixed resource path.
- DnT/Nova: remove only the invalid `nova_structures:illagers_bane` enchant function from two mansion chest entries; book loot and Nova modifier remain. Exact replacement enchantment remains a semantic review blocker.
- Iron's Spells: remove orphan `test/ring_gen_break_me.json` only after reference scan.

See `manifest.json` for source/output hashes and every changed entry. Candidate JARs are under `jars/`; loose overlay files are under `overlay/`.
