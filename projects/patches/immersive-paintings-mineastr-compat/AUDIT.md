# Overlay audit

Date: 2026-08-16 (Asia/Shanghai)

## Evidence

- Two clean Java 21 NeoForge builds completed with tests and JAR tasks.
- Build A SHA-256: `0BFCB1285080C93E343EFBBB9942352B46474F4DBAF9A40CEC5E2CA3DA859D63`
- Build B SHA-256: `D7A67BF5616C7D37CBB612743E7BABBAB828F868FC1AA8605B2ED10D93E676EB`
- Compiled builds have identical entry content; their differing whole-file
  hashes are ZIP timestamp metadata only.
- Final overlay SHA-256:
  `13BE228AACDDBADEF680EE3FB989CCCF3029689DE2ECB09F1B2429189CE21E69`
- Final JAR: 761 unique entries, CRC PASS, no duplicate entries.
- Exactly seven class entries are overlaid. All other base entries are
  byte-identical, including the existing
  `ImmersivePaintingEntity.class` SHA-256
  `2682379343974C4B2538F24476E706682829AF7760C82DA6D84A39C9735C208A`,
  which carries the migration's `VRotation` save/load fix.
- MineAstr 0.6.27 six-argument display API and the custom `ProjectileUtil`
  target ray were checked against the locked MineAstr API. The bridge fails
  closed when the six-argument API is unavailable.

## Dynamic status

This is a detached candidate. No active client, server, Prism instance, world,
or MCModSync state was modified. Dynamic validation remains pending and must be
performed in a disposable clone. Replace the existing `migration.1` JAR in
place; do not leave both same-mod JARs installed.
