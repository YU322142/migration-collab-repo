# Chest Colorizer latest project

Canonical source for the server-migration adaptation:

`outputs/projects/chest-colorizer-neoforge-1.21.1/`

This is the `1.6.1-equivalence.3` source line, including the final barrel
stability fix. The independent public repository is
`YU322142/Chest-Colorizer-NeoForge`; the matching release artifact is
`chest-colorizer-1.6.1-equivalence.3+mc1.21.1-neoforge.jar`.

## File-level entry points

- `build.gradle` — NeoForge 1.21.1 build and optional upstream-equivalence gate
- `gradle.properties` — version, loader, and optional reference hashes
- `src/main/java/net/immortaldevs/colorizer/ColorManager.java` — chest/barrel state and materials
- `src/main/java/net/immortaldevs/colorizer/ColorizerConfig.java` — client CSV lifecycle
- `src/main/java/net/immortaldevs/colorizer/ColorizerCsvDocument.java` — lossless CSV model
- `src/main/java/net/immortaldevs/colorizer/mixin/ChestRendererMixin.java` — chest material hook
- `src/main/java/net/immortaldevs/colorizer/mixin/SectionCompilerMixin.java` — vanilla chunk path
- `src/main/java/net/immortaldevs/colorizer/mixin/sodium/LevelSliceMixin.java` — optional Sodium path
- `src/test/java/net/immortaldevs/colorizer/ColorizerParityTest.java` — 45 semantic assertions

## Build result

```text
gradlew.bat clean check jar --no-daemon
```

The clean build passes with 45 parity assertions. The resulting JAR is
150,404 bytes and has SHA-256
`EC8D9D3AAE816C5E0FAF46DFF284C63530E2460B4801D4F6E1EDF7120D8180A2`.

Reference JARs are optional and intentionally excluded from both Git and the
release. Enable the strict comparison only when the references were obtained
lawfully: `-PverifyReferenceAssets=true`.
