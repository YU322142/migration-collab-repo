# 各项目独立编译指南

本文件把公开快照中的每个源码、补丁和数据项目拆成独立的构建入口。每一节只操作一个项目目录；没有“全仓库一键编译”步骤，也不会把运行中的服务器、世界、玩家数据或第三方 JAR 带入构建。

## 通用前提

- Java 模组工程统一使用 JDK 21；运行时以项目自己的 `gradle.properties` 为准。
- 优先使用项目目录内的 `gradlew.bat`。没有 wrapper 的工程使用已安装的 Gradle 8.x，并在提交前记录实际版本。
- `<AUDIT_ROOT>`、`<TRANS_ROOT>`、`<INSTANCE_ROOT>` 是脱敏占位符，必须替换为拥有者本机的外部制品路径；不要把这些 JAR 提交到 Git。
- Gradle 依赖下载失败时先保留失败日志，不要把 `build/`、`.gradle/` 或缓存目录加入仓库。

## `projects/patches/`

### `immersive-paintings-mineastr-compat`

- 类型：NeoForge 兼容补丁，源码位于 `source/common` 与 `source/neoforge`。
- 构建：进入 `source/neoforge`，使用与上游多模块工程一致的 Gradle 设置执行 `gradle clean check build`；如果只验证桥接逻辑，执行 `python ..\\tools\\verify_immersive_paintings_mineastr_overlay.py --help` 并按 `README.md` 提供的输入运行。
- 验证：`source/neoforge` 的 JUnit；随后运行 `tools/verify_immersive_paintings_mineastr_overlay.py`。
- 产物：`source/neoforge/build/libs/` 中的补丁 JAR；未提供合法上游基线时只做源码编译，不生成可发布 overlay。

### `tlm-patchouli-spawn-box-balance`

- 类型：Patchouli/KubeJS 资源覆盖，没有独立 Java 构建。
- 构建：`python build_tlm_patchouli_balance_overlay.py --help`，按参数提供已授权的原始 TLM JAR 后运行；不具备原始 JAR 时只保留 `overlay/` 和审计报告。
- 验证：`python verify_tlm_patchouli_balance_fix.py --help`，使用同一输入完成双侧差异检查。
- 产物：脚本参数指定的 overlay/JAR，默认不会写入项目目录。

### `worldedit-7.3.8-direction-property-fix`

- 类型：离线 Java 字节码补丁，非 Gradle 项目。
- 构建：在 PowerShell 执行 `./build_worldedit_738_direction_fix.ps1 -OriginalJar <原始WorldEdit> -ServerJar <server映射> -GuavaJar <guava> -FailureAccessJar <failureaccess>`。
- 验证：`./test_worldedit_738_direction_fix.ps1 -OriginalJar <原始WorldEdit> -FixedJar <生成JAR> -RuntimeRoot <运行时根目录>`。
- 产物：脚本目录下的方向属性修补 JAR；所有输入都必须来自外部审计制品。

### `xiyuslogin-auto-session-ota`

- 类型：配置级 OTA 补丁，不编译 Java。
- 构建/预览：`./tools/deploy_xiyuslogin_auto_session.ps1 -ServerRoot <停服副本> -RequireDesiredState`（无 `-Apply` 时仅预览）。
- 验证：`./tools/test_xiyuslogin_auto_session.ps1 -SourceServerRoot <只读源> -TestRoot <外部测试目录>`；需要真实应用时再由运维执行 `-Apply -ConfirmServerStopped`。
- 产物：receipt、rollback 与 post-verify 报告，必须放在仓库外。

### `yuushya-2.3.0-patchouli-safety`

- 类型：Patchouli 资源覆盖脚本。
- 构建：`./build_yuushya_230_patchouli_fix.ps1 -OutputJar <外部输出JAR> -OriginalJar <原始Yuushya JAR>`。
- 验证：`python test_yuushya_230_patchouli_fix.py`，脚本中的默认占位路径需替换为实际审计目录。
- 产物：参数指定的安全补丁 JAR；原始 JAR 不随仓库分发。

## `projects/ports/`

### `barched`

- 类型：Fabric/NeoForge 多模块工程（`common`、`fabric`、`neoforge`）。
- 构建：`cd projects/ports/barched; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`；产物分别位于各子项目 `build/libs/`。

### `cei-2.4.2-with-2.5.1-backport`

- 类型：NeoForge Java 模组。
- 构建：`cd projects/ports/cei-2.4.2-with-2.5.1-backport; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`；产物在 `build/libs/`。

### `content-backport-cat-serializer-fix`

- 类型：Java/ASM 确定性修补器，无 wrapper。
- 编译：`cd projects/ports/content-backport-cat-serializer-fix; gradle clean test`。
- 完整验证：`gradle clean check -PinputJar=<外部backport-1.5.jar>`；`check` 会生成并验证固定 JAR，产物在 `build/libs/`。

### `create-nerfad-1.21.1-neoforge`

- 类型：数据/资源型 NeoForge 模组快照，无 Gradle 工程。
- 构建：先准备 `build/libs`，再执行 `jar --create --file build/libs/create-nerfad-1.21.1.jar -C . META-INF -C . data -C . fabric.mod.json -C . pack.mcmeta -C . icon.png`。
- 验证：检查 JAR 内 `META-INF/neoforge.mods.toml`、`fabric.mod.json` 和 `data/create_nerfad/` 均存在；不要把 `todo-after-fly-update.txt` 当作运行时资源。

### `end-client-harness`

- 类型：客户端测试 harness。
- 构建：`cd projects/ports/end-client-harness; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`；测试资源仅用于 harness。

### `froglight-patch-1.21.1-equivalence`

- 类型：NeoForge 等价移植。
- 构建：`cd projects/ports/froglight-patch-1.21.1-equivalence; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`；产物在 `build/libs/`。

### `happy-ghast-1.21.1-equivalence`

- 类型：NeoForge 等价移植，需外部 Backport 1.5 输入。
- 构建：`cd projects/ports/happy-ghast-1.21.1-equivalence; ./gradlew.bat clean build -Pbackport_jar=<外部backport-1.5.jar>`。
- 验证：`./gradlew.bat check -Pbackport_jar=<外部backport-1.5.jar>`；`compatTest` 会作为 `check` 的依赖运行。

### `hotbath-trigger-registry-fix`

- 类型：NeoForge 注册/触发修补。
- 构建：`cd projects/ports/hotbath-trigger-registry-fix; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`。

### `kaleidoscope-cookery-1.21.1-neoforge`

- 类型：NeoForge 内容移植。
- 构建：`cd projects/ports/kaleidoscope-cookery-1.21.1-neoforge; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`。

### `kaleidoscope-end-1.21.1-equivalence`

- 类型：NeoForge 末地等价层。
- 构建：`cd projects/ports/kaleidoscope-end-1.21.1-equivalence; ./gradlew.bat clean build`；如启用可选输入，按 `gradle.properties` 提供外部 `official_end_jar` 与 `cookery_jar`。
- 验证：`./gradlew.bat check`。

### `kaleidoscope-nether-1.21.1-equivalence`

- 类型：NeoForge 下界等价层。
- 构建：`cd projects/ports/kaleidoscope-nether-1.21.1-equivalence; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`。

### `kaleidoscope-tavern-1.21.1`

- 类型：NeoForge 酒馆内容移植。
- 构建：`cd projects/ports/kaleidoscope-tavern-1.21.1; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`。

### `mcmodsync-1.9.2-pinned-source`

- 类型：手工 Java 构建的旧版同步器源码。
- 构建：`cd projects/ports/mcmodsync-1.9.2-pinned-source; ./build.ps1`。
- 验证：脚本内置编译、测试、JAR 元数据和源代码归档检查；产物在项目 `build/`，公开版本入口以 GitHub release 为准。

### `mcsync-2.0.0`

- 类型：手工 Java 构建的 MCSync 2.0 源码。
- 构建：`cd projects/ports/mcsync-2.0.0; ./build.ps1`。
- 验证：脚本内置单元测试、协议/schema 检查和可重复 JAR 校验；产物在项目 `build/`。

### `mishanguc-1.21.1-equivalence`

- 类型：NeoForge 方块/粒子等价移植。
- 构建：`cd projects/ports/mishanguc-1.21.1-equivalence; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`。

### `nautilus-alias-adapter`

- 类型：NeoForge 别名适配器，需外部 `i_want_my_nautilus` JAR。
- 构建：`cd projects/ports/nautilus-alias-adapter; ./gradlew.bat clean build -Pi_want_jar=<外部JAR>`。
- 验证：`./gradlew.bat check -Pi_want_jar=<外部JAR>`。

### `nautilus-equivalence`

- 类型：NeoForge Nautilus 等价移植。
- 构建：`cd projects/ports/nautilus-equivalence; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`。

### `nautilus-spears-tracked-source`

- 类型：上游跟踪资料，不是可独立构建的工程。
- 流程：先按 README 确认上游许可证和目标版本，再在上游仓库完成构建；本目录只保存来源说明，不生成或分发上游 JAR。

### `potted-farms-1.21.1-equivalence-full`

- 类型：数据包/函数快照。
- 构建：`cd projects/ports/potted-farms-1.21.1-equivalence-full; New-Item -ItemType Directory -Force build | Out-Null; Compress-Archive -Path unpacked\\* -DestinationPath build\\potted-farms-1.21.1-equivalence.zip -Force`。
- 验证：检查 `unpacked/data/minecraft/tags/function/load.json` 和 `unpacked/data/potted_farms/function/`；审计 JSON 仅作证据。

### `respawn-pitch-compat`

- 类型：NeoForge 客户端兼容模组。
- 构建：`cd projects/ports/respawn-pitch-compat; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`。

### `toms-storage-neoforge-1.21.1-perf-port`

- 类型：Fabric/NeoForge 双平台 fork；只独立构建 NeoForge 目录即可得到本项目发布 JAR。
- 构建：`cd projects/ports/toms-storage-neoforge-1.21.1-perf-port/NeoForge; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`；产物在 `NeoForge/build/libs/`。Fabric 目录按其自身 wrapper/README 单独处理。

### `trueuuid-login-proxy-fix`

- 类型：多版本、多加载器 NeoForge/Fabric 工程。
- 构建：`cd projects/ports/trueuuid-login-proxy-fix; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`，再按 `scripts/tests/` 运行 `python -m unittest discover scripts/tests`；每个 `release/targets.json` 目标都是独立产物。

### `xiyuslogin-migration`

- 类型：NeoForge 登录/数据迁移模组。
- 构建：`cd projects/ports/xiyuslogin-migration; ./gradlew.bat clean build`。
- 验证：`./gradlew.bat check`；迁移 fixture 测试不得连接生产服务器。

## `projects/upstream-reference/`

### `kaleidoscope-cookery-upstream`

- 类型：只读上游参考工程。
- 构建：`cd projects/upstream-reference/kaleidoscope-cookery-upstream; ./gradlew.bat clean build`。
- 用途：只用于等价性比较，不作为本站发布包。

### `kaleidoscope-tavern-upstream`

- 类型：只读上游参考工程。
- 构建：`cd projects/upstream-reference/kaleidoscope-tavern-upstream; ./gradlew.bat clean build`。
- 用途：只用于等价性比较，不作为本站发布包。

## `projects/outputs/`

### `projects/outputs`（兼容资料别名）

- 类型：旧版 MCModSync 文档与配置示例的兼容资料目录，不含源码工程。
- 流程：无需编译；如需更新内容，应同步修改 `projects/ports/mcmodsync-1.9.2-pinned-source` 中的源码/文档，再重新生成该目录的脱敏副本。
- 验证：运行仓库级安全检查，确认示例 URL 仍为占位地址，且没有真实服务器、令牌或本机路径。

## `outputs/projects/`

以下工程没有 wrapper，均使用已安装的 Gradle 8.x；若 `gradle.properties` 列出外部 JAR，必须通过 `-P属性=路径` 提供。

### `cctweaked-startup-shutdown-guard-neoforge`

`cd outputs/projects/cctweaked-startup-shutdown-guard-neoforge; gradle clean build -Pcomputercraft_jar=<外部CC:Tweaked JAR>`；验证用 `gradle check -Pcomputercraft_jar=<外部JAR>`。

### `chest-colorizer-neoforge-1.21.1`

`cd outputs/projects/chest-colorizer-neoforge-1.21.1; gradle clean check jar`；需要严格上游等价性时追加 `-PverifyReferenceAssets=true` 并提供 `source_reference_jar`、`old_reference_jar`。公开稳定版本的独立仓库仍是 `YU322142/Chest-Colorizer-NeoForge`。

### `create-carriage-orientation-guard-neoforge`

`gradle clean build -Pcreate_jar=<外部Create JAR> -Psource_reference_jar=<外部参考JAR>`；验证用 `gradle check`。

### `create-chute-unload-guard-neoforge`

`gradle clean build -Pcreate_jar=<外部Create JAR> -Psource_reference_jar=<外部参考JAR>`；验证用 `gradle check`。

### `create-dynamic-blocking-neoforge`

`gradle clean build -Pcreate_jar=<外部Create JAR> -Psource_reference_jar=<外部参考JAR>`；验证用 `gradle check`。

### `create-saveddata-probe`

`gradle clean build -Pcreate_jar=<外部Create JAR>`；这是诊断工程，构建不等于可安装玩法模组。

### `deferred-content-protection-neoforge`

`gradle clean build`；验证用 `gradle check`，并在隔离实例运行内容边界回归。

### `hardcore-revival-death-message-fix-neoforge`

`gradle clean build`；验证用 `gradle check`，再运行仓库根 `python outputs/tools/test_hardcore_revival_death_message_fix.py`。

### `heightmap-384-to-544-compat-neoforge`

`gradle clean build -Pruntime_minecraft_jar=<外部Minecraft server映射> -Pruntime_neoforge_jar=<外部NeoForge universal JAR>`；验证用 `gradle check`。

### `kaleidoscope-cookery-scarecrow-compat`

`gradle clean build -Pcookery_jar=<外部Cookery JAR> -Psource_reference_jar=<外部参考JAR>`；验证用 `gradle check`。

### `kaleidoscope-nether-backport`

`gradle clean build`；验证用 `gradle check`。

### `mishanguc-pale-oak-equivalence`

`gradle clean build`；验证用 `gradle check`。

### `poi-migration-diagnostic`

`gradle clean build`；该工程只输出诊断类，不应放入生产 `mods/`。

### `potted-farms-1.21.1-equivalence`

该目录是数据快照，没有 Gradle 构建；按 `projects/ports/potted-farms-1.21.1-equivalence-full` 的 ZIP 流程打包，并以本目录的审计结果做差异检查。

### `recipe-set-diagnostic`

`gradle clean build`；仅用于配方集合诊断，不作为玩法模组安装。

### `resource-error-overlay-1.21.1`

`cd outputs/projects/resource-error-overlay-1.21.1; ./build.ps1`；脚本直接创建资源 JAR 并输出 SHA-256。无需下载上游 JAR。

### `waypoint-fire-equivalence`

`gradle clean build`；验证用 `gradle check`，再在隔离客户端做视觉回归。

## 发布前逐项目门禁

1. 在该项目目录单独执行上面的构建与验证命令。
2. 只把源码、脚本、测试、文档和许可证提交到公开仓库；把产物哈希登记到 `artifacts/EXTERNAL-ARTIFACTS.*`。
3. 对含第三方基线的工程确认许可证与再分发权限；没有权限时只公开补丁源码和构建流程。
4. 通过 `python tools/repository/check_repository.py`、`python tools/repository/stage_manifest_files.py --verify-only` 和 `git diff --check` 后再提交。
