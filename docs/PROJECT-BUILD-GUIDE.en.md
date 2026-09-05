# Independent build guide for every project

This document gives each source, patch, and data project its own build entry. Every section operates on one project directory only; there is no all-repository build step. Runtime servers, worlds, player data, and third-party JARs stay outside Git.

## Common prerequisites

- Java projects use JDK 21 unless the project’s own `gradle.properties` says otherwise.
- Prefer a project-local `gradlew.bat`. Projects without a wrapper use an installed Gradle 8.x, whose version should be recorded in the build evidence.
- `<AUDIT_ROOT>`, `<TRANS_ROOT>`, and `<INSTANCE_ROOT>` are redacted placeholders. Replace them only with external, authorized artifact paths; never commit those JARs.
- Keep `build/`, `.gradle/`, and dependency caches out of the repository.

## `projects/patches/`

### `immersive-paintings-mineastr-compat`

- Type: NeoForge compatibility patch under `source/common` and `source/neoforge`.
- Build: enter `source/neoforge` and run `gradle clean check build` with the same multi-loader Gradle setup as the upstream source; for source-only verification use the verifier in `tools/verify_immersive_paintings_mineastr_overlay.py`.
- Verify: run the module’s JUnit tests, then `python ..\\tools\\verify_immersive_paintings_mineastr_overlay.py` with an authorized baseline.
- Output: `source/neoforge/build/libs/`; without a lawful baseline, compile only and do not publish an overlay.

### `tlm-patchouli-spawn-box-balance`

- Type: Patchouli/KubeJS resource overlay; no Java build.
- Build: run `python build_tlm_patchouli_balance_overlay.py --help`, then provide the authorized original TLM JAR.
- Verify: run `python verify_tlm_patchouli_balance_fix.py --help` with the same input.
- Output: the overlay/JAR path selected by the script; by default nothing is written as a release artifact in the project tree.

### `worldedit-7.3.8-direction-property-fix`

- Type: offline Java bytecode patch, not a Gradle project.
- Build: in PowerShell run `./build_worldedit_738_direction_fix.ps1 -OriginalJar <original WorldEdit> -ServerJar <server mappings> -GuavaJar <guava> -FailureAccessJar <failureaccess>`.
- Verify: `./test_worldedit_738_direction_fix.ps1 -OriginalJar <original WorldEdit> -FixedJar <generated JAR> -RuntimeRoot <runtime root>`.
- Output: the patch JAR emitted by the script; all inputs must come from external audit artifacts.

### `xiyuslogin-auto-session-ota`

- Type: configuration-level OTA patch; no Java compilation.
- Preview: `./tools/deploy_xiyuslogin_auto_session.ps1 -ServerRoot <stopped copy> -RequireDesiredState` (without `-Apply`).
- Verify: `./tools/test_xiyuslogin_auto_session.ps1 -SourceServerRoot <read-only source> -TestRoot <external test directory>`.
- Output: receipt, rollback, and post-verify reports outside the repository.

### `yuushya-2.3.0-patchouli-safety`

- Type: Patchouli resource overlay script.
- Build: `./build_yuushya_230_patchouli_fix.ps1 -OutputJar <external output JAR> -OriginalJar <original Yuushya JAR>`.
- Verify: `python test_yuushya_230_patchouli_fix.py` after replacing the redacted audit paths.
- Output: the requested patch JAR; the original JAR is never redistributed.

## `projects/ports/`

### `barched`

Multi-loader project (`common`, `fabric`, `neoforge`). Build independently with `cd projects/ports/barched; ./gradlew.bat clean build`, then run `./gradlew.bat check`. Outputs are in each subproject’s `build/libs/`.

### `cei-2.4.2-with-2.5.1-backport`

Run `cd projects/ports/cei-2.4.2-with-2.5.1-backport; ./gradlew.bat clean build`, then `./gradlew.bat check`. Output is `build/libs/`.

### `content-backport-cat-serializer-fix`

Run `gradle clean test` for compilation/tests. For the deterministic patch and verifier run `gradle clean check -PinputJar=<external backport-1.5 JAR>`. The generated JAR is under `build/libs/`.

### `create-nerfad-1.21.1-neoforge`

This is a data/resource NeoForge snapshot. Create `build/libs`, then run `jar --create --file build/libs/create-nerfad-1.21.1.jar -C . META-INF -C . data -C . fabric.mod.json -C . pack.mcmeta -C . icon.png`. Verify the two metadata files and `data/create_nerfad/` are present.

### `end-client-harness`

Run `cd projects/ports/end-client-harness; ./gradlew.bat clean build`, then `./gradlew.bat check`.

### `froglight-patch-1.21.1-equivalence`

Run `cd projects/ports/froglight-patch-1.21.1-equivalence; ./gradlew.bat clean build`, then `./gradlew.bat check`.

### `happy-ghast-1.21.1-equivalence`

Provide the external Backport 1.5 JAR and run `cd projects/ports/happy-ghast-1.21.1-equivalence; ./gradlew.bat clean build -Pbackport_jar=<external backport-1.5 JAR>`. Verify with `./gradlew.bat check -Pbackport_jar=<external backport-1.5 JAR>`.

### `hotbath-trigger-registry-fix`

Run `cd projects/ports/hotbath-trigger-registry-fix; ./gradlew.bat clean build`, then `./gradlew.bat check`.

### `kaleidoscope-cookery-1.21.1-neoforge`

Run `cd projects/ports/kaleidoscope-cookery-1.21.1-neoforge; ./gradlew.bat clean build`, then `./gradlew.bat check`.

### `kaleidoscope-end-1.21.1-equivalence`

Run `cd projects/ports/kaleidoscope-end-1.21.1-equivalence; ./gradlew.bat clean build`; if optional inputs are enabled, supply `official_end_jar` and `cookery_jar` from external artifacts. Verify with `./gradlew.bat check`.

### `kaleidoscope-nether-1.21.1-equivalence`

Run `cd projects/ports/kaleidoscope-nether-1.21.1-equivalence; ./gradlew.bat clean build`, then `./gradlew.bat check`.

### `kaleidoscope-tavern-1.21.1`

Run `cd projects/ports/kaleidoscope-tavern-1.21.1; ./gradlew.bat clean build`, then `./gradlew.bat check`.

### `mcmodsync-1.9.2-pinned-source`

Run `cd projects/ports/mcmodsync-1.9.2-pinned-source; ./build.ps1`. The script compiles, tests, checks JAR metadata, and creates the source archive under `build/`.

### `mcsync-2.0.0`

Run `cd projects/ports/mcsync-2.0.0; ./build.ps1`. The script runs unit tests, protocol/schema checks, and reproducible-JAR verification under `build/`.

### `mishanguc-1.21.1-equivalence`

Run `cd projects/ports/mishanguc-1.21.1-equivalence; ./gradlew.bat clean build`, then `./gradlew.bat check`.

### `nautilus-alias-adapter`

Provide the external `i_want_my_nautilus` JAR and run `cd projects/ports/nautilus-alias-adapter; ./gradlew.bat clean build -Pi_want_jar=<external JAR>`. Verify with `./gradlew.bat check -Pi_want_jar=<external JAR>`.

### `nautilus-equivalence`

Run `cd projects/ports/nautilus-equivalence; ./gradlew.bat clean build`, then `./gradlew.bat check`.

### `nautilus-spears-tracked-source`

This is an upstream-tracking note, not a self-contained build. Confirm the upstream license and target version, then build in the upstream repository. No upstream JAR is produced or redistributed here.

### `potted-farms-1.21.1-equivalence-full`

This is a data-pack snapshot. Run `cd projects/ports/potted-farms-1.21.1-equivalence-full; New-Item -ItemType Directory -Force build | Out-Null; Compress-Archive -Path unpacked\\* -DestinationPath build\\potted-farms-1.21.1-equivalence.zip -Force`. Verify the load tag and function tree.

### `respawn-pitch-compat`

Run `cd projects/ports/respawn-pitch-compat; ./gradlew.bat clean build`, then `./gradlew.bat check`.

### `toms-storage-neoforge-1.21.1-perf-port`

Build the NeoForge side independently with `cd projects/ports/toms-storage-neoforge-1.21.1-perf-port/NeoForge; ./gradlew.bat clean build`, then `./gradlew.bat check`. Output is `NeoForge/build/libs/`; the Fabric side follows its own wrapper/README.

### `trueuuid-login-proxy-fix`

Run `cd projects/ports/trueuuid-login-proxy-fix; ./gradlew.bat clean build`, then `./gradlew.bat check` and `python -m unittest discover scripts/tests`. Each `release/targets.json` target remains a separate artifact.

### `xiyuslogin-migration`

Run `cd projects/ports/xiyuslogin-migration; ./gradlew.bat clean build`, then `./gradlew.bat check`. Fixture tests must never connect to production.

## `projects/upstream-reference/`

### `kaleidoscope-cookery-upstream`

Run `cd projects/upstream-reference/kaleidoscope-cookery-upstream; ./gradlew.bat clean build`. This is comparison-only and is not a site release package.

### `kaleidoscope-tavern-upstream`

Run `cd projects/upstream-reference/kaleidoscope-tavern-upstream; ./gradlew.bat clean build`. This is comparison-only and is not a site release package.

## `projects/outputs/`

### `projects/outputs` (compatibility material alias)

- Type: compatibility copies of legacy MCModSync documentation and configuration examples; there is no source project to compile.
- Process: no compilation is required. Update the canonical source/docs under `projects/ports/mcmodsync-1.9.2-pinned-source`, then regenerate the redacted copy if needed.
- Verify: run the repository safety checks and confirm that example URLs remain placeholders and contain no real server, token, or workstation path.

## `outputs/projects/`

These projects have no wrapper and use an installed Gradle 8.x. If `gradle.properties` names an external JAR, provide it with `-Pproperty=path`.

### `cctweaked-startup-shutdown-guard-neoforge`

`cd outputs/projects/cctweaked-startup-shutdown-guard-neoforge; gradle clean build -Pcomputercraft_jar=<external CC:Tweaked JAR>`; verify with `gradle check -Pcomputercraft_jar=<external JAR>`.

### `chest-colorizer-neoforge-1.21.1`

`cd outputs/projects/chest-colorizer-neoforge-1.21.1; gradle clean check jar`; strict equivalence is opt-in with `-PverifyReferenceAssets=true` and the two external reference properties. The independent public repository is `YU322142/Chest-Colorizer-NeoForge`.

### `create-carriage-orientation-guard-neoforge`

`gradle clean build -Pcreate_jar=<external Create JAR> -Psource_reference_jar=<external reference JAR>`; verify with `gradle check`.

### `create-chute-unload-guard-neoforge`

`gradle clean build -Pcreate_jar=<external Create JAR> -Psource_reference_jar=<external reference JAR>`; verify with `gradle check`.

### `create-dynamic-blocking-neoforge`

`gradle clean build -Pcreate_jar=<external Create JAR> -Psource_reference_jar=<external reference JAR>`; verify with `gradle check`.

### `create-saveddata-probe`

`gradle clean build -Pcreate_jar=<external Create JAR>`. This is diagnostic-only and is not a production gameplay mod.

### `deferred-content-protection-neoforge`

`gradle clean build`, then `gradle check` and run content-boundary regression in an isolated instance.

### `hardcore-revival-death-message-fix-neoforge`

`gradle clean build`, then `gradle check` and `python outputs/tools/test_hardcore_revival_death_message_fix.py` from the repository root.

### `heightmap-384-to-544-compat-neoforge`

`gradle clean build -Pruntime_minecraft_jar=<external Minecraft server mapping> -Pruntime_neoforge_jar=<external NeoForge universal JAR>`; verify with `gradle check`.

### `kaleidoscope-cookery-scarecrow-compat`

`gradle clean build -Pcookery_jar=<external Cookery JAR> -Psource_reference_jar=<external reference JAR>`; verify with `gradle check`.

### `kaleidoscope-nether-backport`

`gradle clean build`, then `gradle check`.

### `mishanguc-pale-oak-equivalence`

`gradle clean build`, then `gradle check`.

### `poi-migration-diagnostic`

`gradle clean build`. This emits diagnostic classes only and must not be installed in production `mods/`.

### `potted-farms-1.21.1-equivalence`

This directory is a data snapshot without Gradle. Use the ZIP flow from `projects/ports/potted-farms-1.21.1-equivalence-full` and compare against this directory’s audit evidence.

### `recipe-set-diagnostic`

`gradle clean build`; this is diagnostics-only, not a gameplay mod.

### `resource-error-overlay-1.21.1`

`cd outputs/projects/resource-error-overlay-1.21.1; ./build.ps1`; the script creates the resource JAR and prints its SHA-256. No upstream JAR is required.

### `waypoint-fire-equivalence`

`gradle clean build`, then `gradle check` and perform a visual regression in an isolated client.

## Per-project release gate

1. Run the build and verification commands for that project only.
2. Commit source, scripts, tests, documentation, and licenses; register artifact hashes in `artifacts/EXTERNAL-ARTIFACTS.*`.
3. Confirm license and redistribution rights for every third-party baseline; without permission, publish only the patch source and build process.
4. Run `python tools/repository/check_repository.py`, `python tools/repository/stage_manifest_files.py --verify-only`, and `git diff --check` before committing.
