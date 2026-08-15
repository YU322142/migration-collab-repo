# AGENTS.md

## LANGUAGE POLICY

- 默认使用简体中文回答。
- 除非我明确要求英文，否则不要切换英文叙述。
- 代码、命令、报错、API 名称保持原文，不要强行翻译。
- 提问澄清时也使用中文。

## Project facts that matter

- Forge mod for Minecraft `1.20.1` / Forge `47.3.0`; use Java 17. Gradle wrapper is pinned in
  `gradle/wrapper/gradle-wrapper.properties`, so prefer `./gradlew` in CI/Unix docs and `.\gradlew.bat` on Windows.
- Mod id is `kaleidoscope_tavern`; Java package root is `src/main/java/com/github/ysbbbbbb/kaleidoscopetavern/`.
- Main mod entrypoint is `KaleidoscopeTavern.java`. It registers the DeferredRegisters from `init/*` on the mod event
  bus and exposes `KaleidoscopeTavern.modLoc(...)` for resource ids.

## Commands

- Full local verification: `.\gradlew.bat build` (`./gradlew build` in GitHub Actions).
- List available Forge/Gradle tasks: `.\gradlew.bat tasks --all`.
- Launch local runs: `.\gradlew.bat runClient`, `.\gradlew.bat runClient2`, `.\gradlew.bat runServer`,
  `.\gradlew.bat runGameTestServer`.
- Regenerate data/assets: `.\gradlew.bat runData`; this writes to `src/generated/resources/` using `src/main/resources/`
  as existing inputs.
- IDE run configs exist as Gradle tasks: `.\gradlew.bat genIntellijRuns`, `.\gradlew.bat genEclipseRuns`,
  `.\gradlew.bat genVSCodeRuns`.
- There is no `src/test` tree currently; `test` exists as a Gradle task but no repo-specific single-test workflow is
  evidenced.

## Generated resources and data

- `src/generated/resources` is part of `sourceSets.main.resources`; `.cache/**` is excluded. Do not treat generated
  resources as disposable unless rerunning `runData` and reviewing the diff.
- Datagen is wired in `datagen/DataGenerators.java` via `GatherDataEvent`. Providers cover block/item models,
  blockstates, recipes, loot tables, drink-effect data, particles, sounds, and tags.
- `processResources` expands Gradle properties into `META-INF/mods.toml` and `pack.mcmeta`; edit placeholders with the
  Gradle properties in mind.

## Code organization quirks

- Registry declarations live under `init/`: blocks/block entities in `ModBlocks`, items in `ModItems`,
  entities/effects/sounds/particles/tree decorators/creative tabs in their matching `Mod*` files.
- Some registries use non-DeferredRegister patterns: `ModFluids` handles fluids/fluid types through `RegisterEvent`, and
  `ModRecipes` initializes custom `RecipeType.simple(...)` values through `RegisterEvent`.
- Use the right Forge bus: `bus = MOD` for lifecycle, registration, and datagen; default Forge bus for runtime gameplay
  events such as datapack reload listeners.
- Common setup side effects are centralized in `init/register/CommonRegistry.java` and use
  `FMLCommonSetupEvent.enqueueWork(...)` for network, composter, tap, and dispenser registrations.
- Network messages are registered in `network/NetworkHandler.java` on a `SimpleChannel` named
  `kaleidoscope_tavern:network`; keep message ids explicit and monotonically updated.

## Client and compat entrypoints

- Client-only setup/events live under `client/` and should be guarded with `Dist.CLIENT` where loaded by event
  subscribers.
- Recipe-viewer integrations have explicit plugin entrypoints: JEI `compat/jei/ModJeiPlugin.java`, REI
  `compat/rei/ModREIClientPlugin.java`, EMI `compat/emi/ModEmiPlugin.java`.

## Workflow gotchas

- `run/` is ignored local runtime state. It may contain KubeJS scripts/logs and per-run game directories; do not commit
  or rely on it as source.
- CI release workflow `.github/workflows/gradle-publish-1.20.1.yml` builds on pushes to `main` touching `src/main/**`
  and publishes `build/libs/*.jar` as a prerelease.
- `.gitattributes` forces `*.json` to CRLF; avoid normalizing JSON line endings casually.
