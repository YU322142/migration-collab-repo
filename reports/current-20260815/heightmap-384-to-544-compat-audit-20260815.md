# Heightmap 384→544 compatibility audit — 2026-08-15

Status: **PASS — ready for dynamic verification in the stopped D test clone**.

The source project is [heightmap-384-to-544-compat-neoforge](<WORKSPACE>/outputs/projects/heightmap-384-to-544-compat-neoforge). It targets Minecraft 1.21.1 with NeoForge 21.1.241 and declares `side="BOTH"`.

The Mixin is deliberately placed at `ChunkAccess#setHeightmap(Heightmap.Types,long[])`, whose exact 1.21.1 runtime call boundary was verified against the reference server JAR. It only transforms an array when all of the following hold:

- the chunk height is exactly 544;
- the input has exactly 37 longs (the old 9-bit, non-spanning layout);
- all 256 values are in the old valid range 0..384;
- every unused padding bit is zero.

The converter unpacks each 9-bit value and repacks it into 43 longs using the 10-bit non-spanning layout. A current 43-long array is returned unchanged. Other dimension heights, unexpected lengths, null input, dirty padding, or out-of-range values are returned unchanged with a bounded diagnostic, allowing vanilla to recompute rather than inventing heights. The mod does not touch registries/worldgen, mark chunks dirty, force saves, or write world files.

Verification is complete for codec round trips, every value 0..384 at storage-word boundaries, zero padding, idempotence, unrelated heights, malformed inputs, exact runtime bytecode, compiled Mixin annotations, BOTH-side metadata, and Gradle `check`.

Two independent `clean check jar` builds were run with Gradle 8.8, `--no-build-cache`, a D-drive Gradle user home, and a 1 GiB Gradle JVM cap. Both JARs are byte-identical:

`AD26B1F429F0E39FCD19D6EFD151DF93A62F3B0F7262312C7BA1D8340E13EFBF`

Build logs and JAR copies are under `<AUDIT_ROOT>\heightmap-384-to-544-compat-20260815\build-1` and `build-2`.

The verified JAR has been installed only in the stopped test clone:

`<AUDIT_ROOT>\protected-terrain-ota-test-server-20260815\mechanomania-matched-runtime-attempt13-20260814\mods\heightmap-384-to-544-compat-1.0.0+neoforge.1.21.1.jar`

There was no same-name preimage. The original public ZIP, production server, and client were not modified. Dynamic boot/legacy-chunk verification remains the next gate; do not treat this artifact alone as production OTA approval.
