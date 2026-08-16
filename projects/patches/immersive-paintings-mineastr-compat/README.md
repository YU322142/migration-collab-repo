# Immersive Paintings → MineAstr image-translation compatibility

## Scope

This patch ports the MineAstr painting-image translation integration to the
NeoForge 1.21.1 Immersive Paintings 0.7.8 migration build. It preserves the
existing migration-specific JAR as the authoritative base and overlays only
the client compatibility classes listed in `overlay-manifest.json`.

The compatibility layer is optional and reflection-based: the mod still loads
when MineAstr is absent. It supports MineAstr 0.6.27's image request API and
six-argument floating entity display API. It also uses a custom client ray so
it works with `paintingsHaveCollision=false`.

## Reproduction

1. Check out Immersive Paintings at commit
   `3337fb1bde2368d8903a5768d38b5095c5618ef7` (0.7.8+1.21.1).
2. Copy the corresponding files under `source/` into that checkout (the
   directory mirrors the upstream `common/` and `neoforge/` source layout).
3. Run the NeoForge test and JAR tasks with Java 21:

   ```text
   gradlew.bat :neoforge:clean :neoforge:test :neoforge:jar --no-daemon --no-build-cache --rerun-tasks
   ```

4. Use `tools/build_immersive_paintings_mineastr_overlay.py` to overlay the
   compiled whitelist classes onto the migration JAR. Never replace the base
   JAR wholesale: that would discard migration-specific resources and the
   existing Rotation/VRotation fix.
5. Run `tools/verify_immersive_paintings_mineastr_overlay.py` before staging.

## Locked inputs

- Base migration JAR SHA-256:
  `AF4D838434302FF65F676D3A4BE8682666E0CCF95392FCFFFBE33E00D79D8D86`
- MineAstr 0.6.27 NeoForge JAR SHA-256:
  `0C449AEE1BCB2A05F11C5A662C9F245FA9246514388CAE8E086C296D6643B574`
- Clean build content was identical across two builds; ZIP timestamps may
  differ before the deterministic overlay step.

## Runtime boundaries

- Replace the matched Immersive Paintings JAR on both client and server only
  during a stopped-server maintenance window; do not touch worlds or region
  files.
- MineAstr 0.6.27 should remain paired on both sides.
- Translation JPEGs and text cache stay client-local under
  `immersive_paintings_cache/translations-v1`; they are not server OTA data.
- MCModSync is intentionally not part of this patch and remains globally
  disabled.
- No live Minecraft launch is claimed by this source patch; dynamic validation
  must use a disposable clone.
