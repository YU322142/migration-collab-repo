# Candidate14-r3 MCModSync local template (UNPUBLISHED)

This directory is deliberately not deployable. It contains no real URL, no
`MCModSync-Config.jar`, no formal `mods-v4.txt`, and no formal legacy
`mods.txt`. Do not rename or upload the draft TSV files.

To enable OTA later:

1. Freeze a controlled immutable HTTPS origin for Minecraft 1.21.1 / NeoForge.
2. Replace the placeholder in `modsync.properties.template` in an isolated
   publication workspace, then generate `MCModSync-Config.jar` with the locked
   MCModSync 1.9.1 publisher.
3. Generate a complete 56-row v4 catalog: 54 Candidate14-r3 client JARs,
   MCModSync 1.9.1, and the generated Config.jar. Keep every row `required` in
   the first catalog. Derive the catalog-version from this release's
   authoritative READY lock (`candidate14-r3-20260812-66778b3f91842d0a` for this snapshot),
   never from a previous release.
4. Treat the 54-file count as this release snapshot only. Future
   catalog versions must derive their complete add/upgrade/remove set from their
   own READY/manifests and immutable hashes; never assume this count is permanent.
5. Authenticate every versioned catalog. The current design requires per-object
   SHA-256/MD5 plus an independently pinned catalog SHA-256. No signing key is
   present in this template; if signing is introduced later, verify it as an
   additional activation gate and never claim an unsigned catalog is signed.
6. Verify every remote object from an external network. Upload the catalog
   last, then run a two-launch Prism canary before broad release.

MCModSync is client-only. Never place it or Config.jar on the dedicated server.
The resource-pack and server-list sync switches remain false.
