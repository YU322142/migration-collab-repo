# Security notes for shared templates

- Patreon or sponsor caches are generated identity data. The Armor of the Ages
  cache files in pack/client-config/ and pack/server-config/ are empty
  templates by design; never fill them with real names or UUIDs before commit.
- UUIDs in fixtures and reports must be synthetic and clearly documented. Use
  the repository checker before staging a snapshot.
- Live client/server directories remain outside this repository. Synchronize
  them only from a user-approved snapshot and never overwrite an active tree.
- Binary JAR files are forbidden except the 21 upstream
  `gradle/wrapper/gradle-wrapper.jar` files required to build imported sources.
- WorldEdit `.archive-unpack` trees are generated caches and must never be committed.
