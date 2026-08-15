package io.github.mcmodsync;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

public final class AllTests {
    private int passed;

    public static void main(String[] arguments) throws Exception {
        new AllTests().run();
    }

    private void run() throws Exception {
        testManifestGenerationAndParsing();
        testFabricModIdAndV1Compatibility();
        testNeoForgeMetadataAndUniversalBootstrap();
        testV4ManifestBilingualMetadataAndDualHash();
        testV3ManifestBackwardCompatibility();
        testPublisherContinuesPreviousCatalog();
        testManagedClientConfigBootstrapAndCatalog();
        testRemoteCatalogMaintainsClientConfig();
        testFileSizeLimitDefaultsToUnlimitedAndStaysLocal();
        testLegacyUpgradeManifestFor16And17();
        testCatalogTypeCheckboxesAreMutuallyExclusive();
        testDisplayLanguageDetection();
        testRestartRequiredPromptLocalizationAndPolicy();
        testOperationalLogsFollowEnglishLanguage();
        testDesktopRecommendedSelectionAndCatalogUpdate();
        testDeselectedRecommendedModIsBackedUp();
        testNoRecommendedModsSelectedAllowsEmptyModsDirectory();
        testMobileRecommendedDownloadsOncePerCatalogVersion();
        testPublisherManifestIncludesSyncTool();
        testSelfDowngradeIsRefused();
        testResourcePackManifestGenerationAndParsing();
        testServerListManifestGenerationAndParsing();
        testManifestRejectsUnsafeInput();
        testPathEncoding();
        testRequiredManifestRetriesTransientFailuresOverHttp11();
        testDetectedGameDirectoryWinsOverAmbiguousCommandLine();
        testUnquotedGameDirectoryWithSpacesCanBeParsed();
        testInstanceGuard();
        testRecentHelperRuntimeCopyIsNotDeleted();
        testFailedHelperHandshakeTerminatesChild();
        testRedirectDownloadStrictSyncAndBackup();
        testParallelModDownloadFallsBackToSingleThread();
        testMissingLocalManifestAsksAboutEveryUnknownMod();
        testResourcePackMd5SyncAndClientPreservation();
        testBakaXLDualDirectoryResourcePackSync();
        testServerListOwnershipLedgerAndOrderProtection();
        testBakaXLDualDirectoryServerListMerge();
        testVersionFilenameChangeIsAutomaticReplacement();
        testBakaXLDualDirectorySync();
        testPortableFabricModeUpdatesAndRequiresRestart();
        testMobileInProcessUpdateDisablesOldModsThenRestarts();
        testMobileDefaultManifestUsesPhoneList();
        testMobileAutoQuarantinesExtrasNotInManifest();
        testKeepingServerRemovedConvertsItToClientMod();
        testApplyFailureRollsBackOriginalFiles();
        testOfflineAlwaysBlocks();
        testResourcePackAndServerListManifestFailuresBlock();
        testClientModIsPreservedWhenOfflineBlocks();
        testInvalidServerManagedModBlocksWhenOffline();
        testZalithMobileEnvironmentDetection();
        testSupportedMobileLauncherAllowList();
        testUnsupportedAndroidLauncherUsesDesktopLogic();
        testHeadlessProgressIsLoggedAndWritten();
        System.out.println("All tests passed: " + passed);
    }

    private void testManifestGenerationAndParsing() throws Exception {
        Path root = Files.createTempDirectory("modsync-manifest-");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            byte[] first = "alpha".getBytes(StandardCharsets.UTF_8);
            byte[] second = "beta".getBytes(StandardCharsets.UTF_8);
            Files.write(mods.resolve("B-mod.jar"), second);
            Files.write(mods.resolve("a-mod.jar"), first);
            Files.writeString(mods.resolve("ignored.txt"), "not a mod");

            ModManifest generated = ModManifest.scan(mods);
            String text = generated.serialize();
            ModManifest parsed = ModManifest.parse(text);

            check(text.contains("# minecraft=1.21.1,1.21.11\n"),
                    "生成的 Mod 清单应声明两个已验证目标版本");
            check(parsed.entries().size() == 2, "应只扫描两个 JAR");
            check(parsed.entries().get(0).fileName().equals("a-mod.jar"), "应按文件名稳定排序");
            check(parsed.entries().get(0).md5().equals(Hashing.md5(first)), "第一个 MD5 应正确");
            check(parsed.entries().get(0).sha256().equals(Hashing.sha256(first)), "第一个 SHA256 应正确");
            check(parsed.entries().get(1).md5().equals(Hashing.md5(second)), "第二个 MD5 应正确");
            pass("manifest generation and parsing");
        } finally {
            deleteTree(root);
        }
    }

    private void testManifestRejectsUnsafeInput() {
        expectFailure(() -> ModManifest.parse(ModManifest.MAGIC + "\n00000000000000000000000000000000\t-\t../evil.jar\n"));
        expectFailure(() -> ModManifest.parse(ModManifest.MAGIC + "\n"));
        expectFailure(() -> ModManifest.parse("<html>not a manifest</html>"));
        pass("unsafe manifests rejected");
    }

    private void testFabricModIdAndV1Compatibility() throws Exception {
        Path root = Files.createTempDirectory("modsync-metadata-");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path jar = mods.resolve("demo-1.0.jar");
            writeFabricJar(jar, "demo_mod", "1.0");
            ModManifest generated = ModManifest.scan(mods);
            check(generated.entries().get(0).modId().equals("demo_mod"), "应从 fabric.mod.json 读取顶层 Mod ID");
            check(generated.serialize().startsWith(ModManifest.MAGIC_V4), "新清单应使用 v4 格式");
            ModManifest.parse(generated.serialize()).ensureUniqueModIds();

            String v1 = ModManifest.MAGIC_V1 + "\n" + Hashing.md5(jar) + "\tdemo-1.0.jar\n";
            ModManifest old = ModManifest.parse(v1);
            check(old.entries().get(0).modId().isEmpty(), "v1 清单应兼容并回退到文件名识别");

            writeFabricJar(mods.resolve("duplicate.jar"), "demo_mod", "duplicate");
            ModManifest duplicates = ModManifest.scan(mods);
            expectFailure(duplicates::ensureUniqueModIds);
            pass("Fabric mod id extraction and v1 compatibility");
        } finally {
            deleteTree(root);
        }
    }

    private void testV4ManifestBilingualMetadataAndDualHash() throws Exception {
        Path root = Files.createTempDirectory("modsync-v4-manifest-");
        try {
            byte[] requiredBytes = "required".getBytes(StandardCharsets.UTF_8);
            byte[] recommendedBytes = "recommended".getBytes(StandardCharsets.UTF_8);
            ManifestEntry required = new ManifestEntry(
                    Hashing.sha256(requiredBytes),
                    Hashing.md5(requiredBytes),
                    "required_mod",
                    "required.jar",
                    ModKind.REQUIRED,
                    Set.of(),
                    "Required Mod",
                    "1.0",
                    "必须加载",
                    "Must load");
            ManifestEntry recommended = new ManifestEntry(
                    Hashing.sha256(recommendedBytes),
                    Hashing.md5(recommendedBytes),
                    "recommended_mod",
                    "recommended.jar",
                    ModKind.RECOMMENDED,
                    Set.of(ClientPlatform.MOBILE, ClientPlatform.MAC),
                    "Recommended Mod",
                    "2.0",
                    "可选图形增强",
                    "Optional graphics");
            ModManifest parsed = ModManifest.parse(
                    ModManifest.fromEntries("catalog-42", List.of(required, recommended)).serialize());
            check(parsed.serialize().startsWith(ModManifest.MAGIC_V4), "新清单应序列化为 v4");
            check(parsed.catalogVersion().equals("catalog-42"), "v4 应保留推荐清单版本");
            check(parsed.entries().get(1).recommended(), "v4 应保留推荐分类");
            check(parsed.entries().get(1).incompatiblePlatforms().contains(ClientPlatform.MOBILE),
                    "v4 应保留不兼容平台");
            check(parsed.entries().get(1).displayName().equals("Recommended Mod"), "v4 应保留显示名称");
            check(parsed.entries().get(1).descriptionZh().equals("可选图形增强"), "v4 应保留中文描述");
            check(parsed.entries().get(1).descriptionEn().equals("Optional graphics"), "v4 应保留英文描述");
            check(parsed.entries().get(1).localizedDescription(DisplayLanguage.ZH_CN).equals("可选图形增强"),
                    "中文界面应使用中文描述");
            check(parsed.entries().get(1).localizedDescription(DisplayLanguage.EN_US).equals("Optional graphics"),
                    "英文界面应使用英文描述");

            Path requiredFile = root.resolve("required.jar");
            Files.write(requiredFile, requiredBytes);
            check(ModManifest.fileMatches(required, requiredFile), "MD5/SHA256 都正确时应匹配");
            Files.writeString(requiredFile, "tampered", StandardCharsets.UTF_8);
            check(!ModManifest.fileMatches(required, requiredFile), "任一哈希不符时应拒绝");
            pass("v4 bilingual manifest metadata and dual hash");
        } finally {
            deleteTree(root);
        }
    }

    private void testV3ManifestBackwardCompatibility() {
        byte[] bytes = "legacy-v3".getBytes(StandardCharsets.UTF_8);
        String v3 = ModManifest.MAGIC_V3 + "\n"
                + "# catalog-version=legacy-3\n"
                + Hashing.sha256(bytes) + "\t" + Hashing.md5(bytes)
                + "\tlegacy_mod\tlegacy.jar\trecommended\tmobile\tLegacy Mod\t1.0\tLegacy description\n";
        ModManifest parsed = ModManifest.parse(v3);
        check(parsed.entries().get(0).recommended(), "v3 推荐分类应继续可读");
        check(parsed.entries().get(0).descriptionEn().equals("Legacy description"),
                "v3 单描述应迁移到英文描述");
        check(parsed.entries().get(0).localizedDescription(DisplayLanguage.ZH_CN).equals("Legacy description"),
                "中文描述缺失时应回退旧版描述");
        pass("v3 manifest remains backward compatible");
    }

    private void testLegacyUpgradeManifestFor16And17() {
        byte[] updaterBytes = "mcmodsync-1.8".getBytes(StandardCharsets.UTF_8);
        byte[] bootstrapBytes = "managed-config".getBytes(StandardCharsets.UTF_8);
        byte[] optionalBytes = "optional".getBytes(StandardCharsets.UTF_8);
        ManifestEntry updater = new ManifestEntry(
                Hashing.sha256(updaterBytes),
                Hashing.md5(updaterBytes),
                "mcmodsync",
                "MCModSync-1.8.0.jar",
                ModKind.REQUIRED,
                Set.of(),
                "MCModSync",
                "1.8.0",
                "同步器",
                "Synchronizer");
        ManifestEntry bootstrap = new ManifestEntry(
                Hashing.sha256(bootstrapBytes),
                Hashing.md5(bootstrapBytes),
                ManagedClientConfig.BOOTSTRAP_MOD_ID,
                ManagedClientConfig.BOOTSTRAP_FILE_NAME,
                ModKind.REQUIRED,
                Set.of(),
                "MCModSync Config",
                "1",
                "配置引导",
                "Configuration bootstrap");
        ManifestEntry optional = new ManifestEntry(
                Hashing.sha256(optionalBytes),
                Hashing.md5(optionalBytes),
                "optional_mod",
                "optional.jar",
                ModKind.RECOMMENDED,
                Set.of(ClientPlatform.MOBILE),
                "Optional",
                "1.0",
                "可选",
                "Optional");
        String transition = LegacyUpgradeManifest.serialize(
                ModManifest.fromEntries("upgrade-test", List.of(updater, bootstrap, optional)));

        List<String[]> legacy16Entries = parseWithFrozenLegacyV2Rules(transition);
        check(legacy16Entries.size() == 2, "1.6.x v2 入口必须只包含两个升级组件");
        check(legacy16Entries.stream().anyMatch(fields -> fields[1].equals("mcmodsync")
                        && fields[2].equals("MCModSync-1.8.0.jar")),
                "永久升级入口必须让 1.6.x 通过 Mod ID 替换同步器");
        check(legacy16Entries.stream().anyMatch(fields -> fields[1].equals(ManagedClientConfig.BOOTSTRAP_MOD_ID)
                        && fields[2].equals(ManagedClientConfig.BOOTSTRAP_FILE_NAME)),
                "永久升级入口必须下载固定名配置引导 JAR");
        check(legacy16Entries.stream().noneMatch(fields -> fields[1].equals("optional_mod")),
                "完整 Mod 集不得继续发布到旧版升级入口");
        check(transition.contains("# upgrade-components-only=true"),
                "升级专用 v2 入口应包含可审计标记");
        check(transition.contains("# minecraft=1.21.1,1.21.11\n"),
                "升级专用 v2 入口应声明两个已验证目标版本");
        check(!transition.contains(ModManifest.MAGIC_V3) && !transition.contains(ModManifest.MAGIC_V4),
                "永久升级入口不能包含会让旧解析器拒绝的新版 magic");

        ModManifest parsedBy17Rules = ModManifest.parse(transition);
        check(parsedBy17Rules.entries().size() == 2, "1.7 兼容解析应读取永久 v2 升级入口");
        check(parsedBy17Rules.entries().stream().allMatch(entry -> entry.kind() == ModKind.REQUIRED),
                "过渡阶段必须把所有条目视为 required，避免旧客户端漏装依赖");

        ModManifest missingUpdater = ModManifest.fromEntries("missing-updater", List.of(optional));
        expectFailure(() -> LegacyUpgradeManifest.serialize(missingUpdater));
        expectFailure(() -> LegacyUpgradeManifest.serialize(
                ModManifest.fromEntries("missing-bootstrap", List.of(updater, optional))));
        ManifestEntry wronglyNamedBootstrap = new ManifestEntry(
                bootstrap.sha256(), bootstrap.md5(), bootstrap.modId(), "renamed-config.jar",
                ModKind.REQUIRED, Set.of(), bootstrap.displayName(), bootstrap.version(),
                bootstrap.descriptionZh(), bootstrap.descriptionEn());
        expectFailure(() -> LegacyUpgradeManifest.serialize(
                ModManifest.fromEntries("renamed-bootstrap", List.of(updater, wronglyNamedBootstrap))));
        ManifestEntry tooOldUpdater = new ManifestEntry(
                updater.sha256(), updater.md5(), updater.modId(), "MCModSync-1.7.0.jar",
                ModKind.REQUIRED, Set.of(), updater.displayName(), "1.7.0", "同步器", "Synchronizer");
        expectFailure(() -> LegacyUpgradeManifest.serialize(
                ModManifest.fromEntries("old-updater", List.of(tooOldUpdater, bootstrap, optional))));
        pass("permanent v2 gateway contains upgrade components only");
    }

    private void testPublisherContinuesPreviousCatalog() {
        ManifestEntry oldSodium = new ManifestEntry(
                "a".repeat(64),
                "b".repeat(32),
                "sodium",
                "sodium-old.jar",
                ModKind.RECOMMENDED,
                Set.of(ClientPlatform.MOBILE, ClientPlatform.MAC),
                "Sodium 自定义名称",
                "1.0",
                "钠渲染优化",
                "Sodium rendering optimization");
        ManifestEntry removed = new ManifestEntry(
                "c".repeat(64),
                "d".repeat(32),
                "removed_mod",
                "removed.jar",
                ModKind.RECOMMENDED,
                Set.of(),
                "Removed",
                "1.0",
                "已移除",
                "Removed");
        ModManifest previous = ModManifest.fromEntries("published-catalog-7", List.of(oldSodium, removed));

        ManifestEntry currentSodium = new ManifestEntry(
                "1".repeat(64),
                "2".repeat(32),
                "sodium",
                "sodium-new.jar",
                ModKind.REQUIRED,
                Set.of(),
                "Sodium metadata name",
                "2.0",
                "",
                "New metadata description");
        ManifestEntry added = new ManifestEntry(
                "3".repeat(64),
                "4".repeat(32),
                "new_mod",
                "new.jar",
                ModKind.REQUIRED,
                Set.of(),
                "New Mod",
                "1.0",
                "新模组",
                "New mod");
        ModManifest scanned = ModManifest.fromEntries("fresh-scan", List.of(currentSodium, added));

        ModManifest merged = PublisherMain.mergeCatalog(scanned, previous);
        check(merged.catalogVersion().equals("published-catalog-7"), "继续编辑应保留上次清单版本供用户修改");
        check(merged.entries().size() == 2, "继续编辑的条目集合必须以当前 mods 扫描结果为准");
        ManifestEntry sodium = merged.entries().get(0);
        check(sodium.fileName().equals("sodium-new.jar") && sodium.version().equals("2.0"),
                "同 Mod ID 更新时应采用当前文件名和版本");
        check(sodium.sha256().equals("1".repeat(64)) && sodium.md5().equals("2".repeat(32)),
                "继续编辑时必须刷新当前 JAR 的 SHA256 和 MD5");
        check(sodium.kind() == ModKind.RECOMMENDED
                        && sodium.incompatiblePlatforms().equals(Set.of(ClientPlatform.MOBILE, ClientPlatform.MAC)),
                "继续编辑应保留上次的分类和不兼容平台");
        check(sodium.displayName().equals("Sodium 自定义名称")
                        && sodium.descriptionZh().equals("钠渲染优化")
                        && sodium.descriptionEn().equals("Sodium rendering optimization"),
                "继续编辑应保留上次维护的显示名称和双语描述");
        check(merged.entries().get(1).modId().equals("new_mod"), "当前目录中的新增 Mod 应加入清单");
        pass("publisher continues from a previous catalog after scanning mods");
    }

    private void testManagedClientConfigBootstrapAndCatalog() throws Exception {
        Path root = Files.createTempDirectory("modsync-managed-client-config-");
        try {
            Path publisherGame = Files.createDirectories(root.resolve("publisher"));
            Path publisherMods = Files.createDirectories(publisherGame.resolve("mods"));
            Path template = publisherGame.resolve("modsync.properties");
            Files.writeString(template,
                    "manifest=https://files.example.invalid/client/mods-v4.txt\n"
                            + "mobileManifest=https://files.example.invalid/client/mobile-mods-v4.txt\n"
                            + "syncResourcePacks=false\n"
                            + "syncServerList=false\n"
                            + "strict=true\n"
                            + "requireManifest=true\n"
                            + "language=zh_cn\n"
                            + "maxFileBytes=987654321\n",
                    StandardCharsets.UTF_8);
            byte[] templateBytes = Files.readAllBytes(template);
            byte[] templateWithBom = new byte[templateBytes.length + 3];
            templateWithBom[0] = (byte) 0xef;
            templateWithBom[1] = (byte) 0xbb;
            templateWithBom[2] = (byte) 0xbf;
            System.arraycopy(templateBytes, 0, templateWithBom, 3, templateBytes.length);
            Files.write(template, templateWithBom);
            ManagedClientConfig managed = ManagedClientConfig.fromPropertiesFile(template);
            check(!managed.values().containsKey("maxFileBytes") && !managed.values().containsKey("language"),
                    "文件大小限制和语言必须保持本地设置，不能进入服务器受管配置");

            ManifestEntry bootstrap = ManagedClientConfig.writeBootstrapJar(publisherMods, managed);
            check(bootstrap.modId().equals(ManagedClientConfig.BOOTSTRAP_MOD_ID)
                            && bootstrap.kind() == ModKind.REQUIRED,
                    "配置引导 JAR 必须作为必需模组进入升级清单");

            Path client = Files.createDirectories(root.resolve("client"));
            Path clientMods = Files.createDirectories(client.resolve("mods"));
            Files.copy(
                    publisherMods.resolve(ManagedClientConfig.BOOTSTRAP_FILE_NAME),
                    clientMods.resolve(ManagedClientConfig.BOOTSTRAP_FILE_NAME));
            Files.writeString(client.resolve("modsync.properties"),
                    "manifest=https://old.example.invalid/mods.txt\n"
                            + "language=en_us\n"
                            + "maxFileBytes=123456789\n",
                    StandardCharsets.UTF_8);
            check(ManagedClientConfig.installFromBootstrapJar(client, message -> { }),
                    "首次启动应从引导 JAR 自动更新 modsync.properties");
            java.util.Properties installed = new java.util.Properties();
            try (var input = Files.newInputStream(client.resolve("modsync.properties"))) {
                installed.load(input);
            }
            check(installed.getProperty("manifest").endsWith("/mods-v4.txt"),
                    "升级客户端应自动切换到正式 mods-v4.txt");
            check(installed.getProperty("language").equals("en_us")
                            && installed.getProperty("maxFileBytes").equals("123456789"),
                    "更新受管配置时必须保留本地语言和文件大小限制");
            check(!ManagedClientConfig.installFromBootstrapJar(client, message -> { }),
                    "配置一致时不应重复改写 modsync.properties");

            ManifestEntry updater = new ManifestEntry(
                    "1".repeat(64),
                    "2".repeat(32),
                    "mcmodsync",
                    "MCModSync-1.9.0.jar",
                    ModKind.REQUIRED,
                    Set.of(),
                    "MCModSync",
                    "1.9.0",
                    "同步器",
                    "Synchronizer");
            ModManifest catalog = ModManifest.fromEntries("managed-config-1", List.of(updater, bootstrap))
                    .withManagedClientConfig(managed);
            String v4 = catalog.serialize();
            check(v4.contains("# client-config.manifest=https://files.example.invalid/client/mods-v4.txt"),
                    "正式 v4 清单必须携带受管客户端配置");
            check(!v4.contains("maxFileBytes") && !v4.contains("language="),
                    "正式清单不得包含本地文件大小限制或语言");
            check(ModManifest.parse(v4).managedClientConfig().orElseThrow().equals(managed),
                    "v4 清单中的受管配置应可完整解析");
            String legacy = LegacyUpgradeManifest.serialize(catalog);
            check(legacy.startsWith(ModManifest.MAGIC_V2)
                            && legacy.contains("\t" + ManagedClientConfig.BOOTSTRAP_MOD_ID + "\t"
                                    + ManagedClientConfig.BOOTSTRAP_FILE_NAME),
                    "永久 v2 入口必须让 1.6.x 下载配置引导 JAR");
            expectFailure(() -> ManagedClientConfig.fromManifestText(
                    v4 + "# client-config.maxFileBytes=1\n"));
            pass("managed client config bootstraps mods-v4 and preserves local file size limits");
        } finally {
            System.clearProperty("modsync.managedConfigChanged");
            deleteTree(root);
        }
    }

    private void testRemoteCatalogMaintainsClientConfig() throws Exception {
        Path root = Files.createTempDirectory("modsync-remote-client-config-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            byte[] managedBytes = "already installed".getBytes(StandardCharsets.UTF_8);
            Files.write(mods.resolve("managed.jar"), managedBytes);
            URI manifestUri = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/release/mods-v4.txt");
            ManagedClientConfig managed = ManagedClientConfig.fromManifestText(
                    "# client-config.manifest=" + manifestUri + "\n"
                            + "# client-config.syncResourcePacks=false\n"
                            + "# client-config.syncServerList=false\n"
                            + "# client-config.strict=true\n"
                            + "# client-config.requireManifest=true\n")
                    .orElseThrow();
            ManifestEntry entry = new ManifestEntry(
                    Hashing.sha256(managedBytes),
                    Hashing.md5(managedBytes),
                    "",
                    "managed.jar",
                    ModKind.REQUIRED,
                    Set.of(),
                    "Managed",
                    "1.0",
                    "已安装",
                    "Installed");
            byte[] catalog = ModManifest.fromEntries("remote-config-2", List.of(entry))
                    .withManagedClientConfig(managed)
                    .serialize()
                    .getBytes(StandardCharsets.UTF_8);
            server.createContext("/release/mods-v4.txt", exchange -> respond(exchange, 200, catalog, null));
            server.start();

            Files.writeString(root.resolve("modsync.properties"),
                    "manifest=" + manifestUri + "\n"
                            + "syncResourcePacks=false\n"
                            + "syncServerList=false\n"
                            + "strict=false\n"
                            + "requireManifest=true\n"
                            + "language=en_us\n"
                            + "maxFileBytes=456789123\n",
                    StandardCharsets.UTF_8);
            ModSyncConfig config = new ModSyncConfig(
                    manifestUri,
                    URI.create("https://example.invalid/resourcepacks.txt"),
                    URI.create("https://example.invalid/serverlist.txt"),
                    root,
                    root,
                    false,
                    false,
                    false,
                    true,
                    Duration.ofSeconds(2),
                    Duration.ofSeconds(5),
                    1024 * 1024,
                    16 * 1024 * 1024,
                    3);
            SyncProbeResult probe = new ModSyncEngine(config, message -> { }).probeWithoutJarChanges();
            check(probe.status() == SyncProbeResult.Status.CHANGES_REQUIRED,
                    "远程受管配置变化应要求正常重启");
            java.util.Properties updated = new java.util.Properties();
            try (var input = Files.newInputStream(root.resolve("modsync.properties"))) {
                updated.load(input);
            }
            check(updated.getProperty("strict").equals("true"), "v4 清单应持续更新白名单配置");
            check(updated.getProperty("language").equals("en_us")
                            && updated.getProperty("maxFileBytes").equals("456789123"),
                    "远程配置更新不得覆盖语言或文件大小限制");
            pass("remote v4 catalog maintains whitelisted client config only");
        } finally {
            System.clearProperty("modsync.managedConfigChanged");
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testFileSizeLimitDefaultsToUnlimitedAndStaysLocal() throws Exception {
        Path root = Files.createTempDirectory("modsync-unlimited-file-size-");
        try {
            Files.writeString(root.resolve("modsync.properties"),
                    "manifest=https://files.example.invalid/client/mods-v4.txt\n"
                            + "syncResourcePacks=false\n"
                            + "syncServerList=false\n"
                            + "strict=true\n"
                            + "requireManifest=true\n",
                    StandardCharsets.UTF_8);
            ModSyncConfig unlimited = ModSyncConfig.fromEnvironment(null, root);
            check(unlimited.maxFileBytes() == Long.MAX_VALUE,
                    "客户端未配置 maxFileBytes 时不应主动限制单文件大小");

            Files.writeString(root.resolve("modsync.properties"),
                    "maxFileBytes=123456789\n",
                    StandardCharsets.UTF_8,
                    java.nio.file.StandardOpenOption.APPEND);
            ModSyncConfig limited = ModSyncConfig.fromEnvironment(null, root);
            check(limited.maxFileBytes() == 123456789L,
                    "客户端显式设置 maxFileBytes 时仍应使用本地上限");
            pass("file-size limit defaults to unlimited and remains local-only");
        } finally {
            deleteTree(root);
        }
    }

    private static List<String[]> parseWithFrozenLegacyV2Rules(String text) {
        String[] lines = text.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1);
        int magicCount = 0;
        List<String[]> entries = new ArrayList<>();
        for (String line : lines) {
            if (line.strip().equals("# mcmod-sync-v2")) {
                magicCount++;
                continue;
            }
            if (line.isBlank() || line.startsWith("#")) {
                continue;
            }
            String[] fields = line.split("\t", -1);
            check(fields.length == 3, "1.6.x v2 每行必须严格为 MD5、Mod ID、文件名三列");
            check(fields[0].matches("[0-9a-fA-F]{32}"), "1.6.x v2 MD5 必须有效");
            check(fields[1].equals("-") || FabricModMetadata.isValidModId(fields[1]),
                    "1.6.x v2 Mod ID 必须有效");
            check(fields[2].endsWith(".jar") && !fields[2].contains("/") && !fields[2].contains("\\"),
                    "1.6.x v2 文件名必须安全");
            entries.add(fields);
        }
        check(magicCount == 1, "1.6.x v2 清单必须只声明一次 v2 magic");
        check(!entries.isEmpty(), "1.6.x v2 清单不能空");
        return entries;
    }

    private void testCatalogTypeCheckboxesAreMutuallyExclusive() {
        CatalogEditorDialog.CatalogTableModel model = new CatalogEditorDialog.CatalogTableModel();
        model.addRow(new Object[]{
                "demo.jar", true, false, "Demo", "1.0",
                false, false, false, false, "中文", "English"
        });
        model.setValueAt(Boolean.TRUE, 0, CatalogEditorDialog.RECOMMENDED_COLUMN);
        check(!Boolean.TRUE.equals(model.getValueAt(0, CatalogEditorDialog.REQUIRED_COLUMN)),
                "勾选推荐后必须自动取消必须");
        check(Boolean.TRUE.equals(model.getValueAt(0, CatalogEditorDialog.RECOMMENDED_COLUMN)),
                "推荐复选框应保持勾选");
        check(model.isCellEditable(0, CatalogEditorDialog.MOBILE_COLUMN),
                "推荐模组应允许编辑不兼容平台");
        model.setValueAt(Boolean.TRUE, 0, CatalogEditorDialog.MOBILE_COLUMN);
        model.setValueAt(Boolean.FALSE, 0, CatalogEditorDialog.RECOMMENDED_COLUMN);
        check(Boolean.TRUE.equals(model.getValueAt(0, CatalogEditorDialog.REQUIRED_COLUMN)),
                "取消当前类型时应自动切换到另一类型，不能出现两者都不选");
        check(!Boolean.TRUE.equals(model.getValueAt(0, CatalogEditorDialog.RECOMMENDED_COLUMN)),
                "切换为必须后推荐必须取消");
        check(!Boolean.TRUE.equals(model.getValueAt(0, CatalogEditorDialog.MOBILE_COLUMN)),
                "切换为必须后应清除不兼容平台");
        check(!model.isCellEditable(0, CatalogEditorDialog.MOBILE_COLUMN),
                "必须模组不应允许编辑不兼容平台");
        pass("catalog required/recommended checkboxes are mutually exclusive");
    }

    private void testDisplayLanguageDetection() throws Exception {
        Path root = Files.createTempDirectory("modsync-language-");
        Map<String, String> previous = snapshotProperties("modsync.language");
        Locale previousLocale = Locale.getDefault();
        try {
            System.clearProperty("modsync.language");
            Locale.setDefault(Locale.US);
            Files.writeString(root.resolve("options.txt"), "lang:zh_cn\n", StandardCharsets.UTF_8);
            check(DisplayLanguage.detect(root) == DisplayLanguage.EN_US,
                    "auto 应跟随英文系统语言而不是 Minecraft 中文设置");
            Locale.setDefault(Locale.SIMPLIFIED_CHINESE);
            check(DisplayLanguage.detect(root) == DisplayLanguage.ZH_CN,
                    "auto 应跟随中文系统语言");
            Files.writeString(root.resolve("modsync.properties"), "language=zh_cn\n", StandardCharsets.UTF_8);
            check(DisplayLanguage.detect(root) == DisplayLanguage.ZH_CN,
                    "modsync.properties 应覆盖系统语言");
            System.setProperty("modsync.language", "en_us");
            check(DisplayLanguage.detect(root) == DisplayLanguage.EN_US,
                    "系统属性应覆盖配置文件语言");
            pass("Chinese and English display language detection");
        } finally {
            Locale.setDefault(previousLocale);
            restoreProperties(previous);
            deleteTree(root);
        }
    }

    private void testNeoForgeMetadataAndUniversalBootstrap() throws Exception {
        Path root = Files.createTempDirectory("modsync-neoforge-metadata-");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path jar = mods.resolve("neo-demo-2.3.jar");
            writeNeoForgeJar(jar, "neo_demo", "2.3");
            check(ModMetadata.readModId(jar).equals("neo_demo"),
                    "应从 neoforge.mods.toml 读取 Mod ID");
            check(ModMetadata.readVersion(jar).equals("2.3"),
                    "应从 neoforge.mods.toml 读取版本");
            check(ModMetadata.readName(jar).equals("Neo Demo"),
                    "应从 neoforge.mods.toml 读取显示名称");
            check(ModMetadata.readDescription(jar).equals("NeoForge description with spaces"),
                    "应读取并规范化 NeoForge 多行描述");
            ModManifest manifest = ModManifest.scan(mods);
            check(manifest.entries().get(0).modId().equals("neo_demo"),
                    "发布器扫描应识别没有 fabric.mod.json 的 NeoForge JAR");

            Path properties = root.resolve("modsync.properties");
            Files.writeString(properties,
                    "manifest=https://example.invalid/mods-v4.txt\n"
                            + "requireManifest=true\n",
                    StandardCharsets.UTF_8);
            ManagedClientConfig config = ManagedClientConfig.fromPropertiesFile(properties);
            ManagedClientConfig.writeBootstrapJar(mods, config);
            try (java.util.zip.ZipFile zip = new java.util.zip.ZipFile(
                    mods.resolve(ManagedClientConfig.BOOTSTRAP_FILE_NAME).toFile())) {
                check(zip.getEntry("fabric.mod.json") != null,
                        "配置引导 JAR 应保留 Fabric 元数据");
                check(zip.getEntry("META-INF/neoforge.mods.toml") != null,
                        "配置引导 JAR 应同时包含 NeoForge 元数据");
                String bootstrapToml;
                try (java.io.InputStream input = zip.getInputStream(
                        zip.getEntry("META-INF/neoforge.mods.toml"))) {
                    bootstrapToml = new String(input.readAllBytes(), StandardCharsets.UTF_8);
                }
                check(bootstrapToml.contains("modLoader=\"lowcodefml\""),
                        "无 @Mod 类的配置引导 JAR 应使用 NeoForge lowcodefml 加载器");
            }

            net.neoforged.fml.common.Mod annotation =
                    NeoForgeModEntrypoint.class.getAnnotation(net.neoforged.fml.common.Mod.class);
            check(annotation != null && annotation.value().equals("mcmodsync"),
                    "NeoForge 入口应声明 mcmodsync @Mod");
            check(java.util.Arrays.equals(annotation.dist(),
                            new net.neoforged.api.distmarker.Dist[]{
                                    net.neoforged.api.distmarker.Dist.CLIENT}),
                    "NeoForge 入口应限定为客户端");
            net.neoforged.fml.loading.FMLPaths.setGameDir(root);
            check(NeoForgeModEntrypoint.locateGameDirectory().equals(root.toAbsolutePath().normalize()),
                    "NeoForge 入口必须从 FMLPaths.GAMEDIR 获取游戏目录");
            pass("NeoForge TOML metadata, dual bootstrap metadata and @Mod entrypoint");
        } finally {
            deleteTree(root);
        }
    }

    private void testRecentHelperRuntimeCopyIsNotDeleted() throws Exception {
        Path root = Files.createTempDirectory("modsync-helper-cleanup-");
        try {
            Path recent = Files.writeString(root.resolve("recent-helper.jar"), "recent");
            Path stale = Files.writeString(root.resolve("stale-helper.jar"), "stale");
            Files.setLastModifiedTime(stale, FileTime.from(Instant.now().minus(Duration.ofHours(25))));

            PortableUpdateHelper.cleanupOldHelperCopies(root, message -> { });

            check(Files.isRegularFile(recent),
                    "并发启动时不得删除刚生成、尚未被 Java 打开的 helper JAR");
            check(!Files.exists(stale), "超过保留期的旧 helper JAR 应被清理");
            pass("recent helper runtime copies survive concurrent cleanup");
        } finally {
            deleteTree(root);
        }
    }

    private void testRestartRequiredPromptLocalizationAndPolicy() {
        check(UserNotifier.restartRequiredTitle(DisplayLanguage.ZH_CN).contains("需要重新启动"),
                "中文下载完成窗口必须明确提示需要重新启动");
        check(UserNotifier.restartRequiredMessage(DisplayLanguage.ZH_CN).contains("重新启动 Minecraft"),
                "中文下载完成正文必须说明重新启动 Minecraft");
        check(UserNotifier.restartRequiredButton(DisplayLanguage.ZH_CN).contains("返回启动器"),
                "中文确认按钮必须说明返回启动器");

        check(UserNotifier.restartRequiredTitle(DisplayLanguage.EN_US).contains("Restart Required"),
                "英文下载完成窗口标题必须包含 Restart Required");
        check(UserNotifier.restartRequiredMessage(DisplayLanguage.EN_US).contains("restart Minecraft"),
                "英文下载完成正文必须说明 restart Minecraft");
        check(UserNotifier.restartRequiredButton(DisplayLanguage.EN_US).equals("OK, Return to Launcher"),
                "英文确认按钮必须说明返回启动器");

        check(UserNotifier.shouldShowRestartRequired(true, false),
                "桌面 Fabric 便携更新完成后必须显示重新启动提示");
        check(!UserNotifier.shouldShowRestartRequired(false, false),
                "Java Agent 同步完成后不得错误显示重新启动提示");
        check(!UserNotifier.shouldShowRestartRequired(true, true),
                "手机端必须继续跳过 Swing 重新启动提示");
        pass("desktop restart-required prompt is bilingual and mobile-safe");
    }

    private void testFailedHelperHandshakeTerminatesChild() throws Exception {
        Path root = Files.createTempDirectory("modsync-helper-handshake-failure-");
        Path java = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name", "").toLowerCase().contains("windows") ? "java.exe" : "java");
        Path readyFile = Files.writeString(root.resolve("ready.signal"), "-1", StandardCharsets.UTF_8);
        Process child = new ProcessBuilder(
                java.toString(),
                "-cp",
                System.getProperty("java.class.path"),
                SleepingChild.class.getName())
                .redirectErrorStream(true)
                .start();
        try {
            IOException failure = null;
            try {
                PortableUpdateHelper.awaitHelperReadyOrTerminate(
                        child,
                        readyFile,
                        root.resolve("helper.jar"),
                        root.resolve("helper.log"),
                        DisplayLanguage.EN_US);
            } catch (IOException expected) {
                failure = expected;
            }

            check(failure != null && failure.getMessage().contains("PID mismatch"),
                    "错误 PID 的 helper ready 信号必须使握手失败");
            check(child.waitFor(3, TimeUnit.SECONDS) && !child.isAlive(),
                    "helper 握手失败后必须终止已创建的子进程");
            pass("failed helper readiness terminates child process");
        } finally {
            child.destroyForcibly();
            child.waitFor(3, TimeUnit.SECONDS);
            deleteTree(root);
        }
    }

    private void testOperationalLogsFollowEnglishLanguage() throws Exception {
        Path root = Files.createTempDirectory("modsync-english-logs-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        Map<String, String> previous = snapshotProperties("modsync.language", "modsync.gameDir");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path managed = mods.resolve("managed.jar");
            writeFabricJar(managed, "managed", "english-logs");
            String manifest = ModManifest.MAGIC + "\n" + Hashing.md5(managed) + "\tmanaged\tmanaged.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.start();

            System.setProperty("modsync.language", "en_us");
            System.setProperty("modsync.gameDir", root.toString());
            URI manifestUri = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt");
            List<String> messages = new ArrayList<>();
            SyncProbeResult result = ModSyncCoordinator.probe(
                    config(root, manifestUri, true, true), messages::add, SyncObserver.NONE);

            check(result.status() == SyncProbeResult.Status.UP_TO_DATE,
                    "英文日志测试的本地 Mod 应与清单一致");
            check(messages.stream().anyMatch(message -> message.contains("Checking sync target")),
                    "主同步日志应根据英文设置输出英文目标名称");
            check(messages.stream().noneMatch(AllTests::containsHanCharacter),
                    "英文模式下正常同步日志不应残留中文: " + messages);
            pass("operational logs follow English language");
        } finally {
            restoreProperties(previous);
            server.stop(0);
            deleteTree(root);
        }
    }

    private static boolean containsHanCharacter(String value) {
        return value.codePoints().anyMatch(codePoint ->
                Character.UnicodeScript.of(codePoint) == Character.UnicodeScript.HAN);
    }

    private void testDesktopRecommendedSelectionAndCatalogUpdate() throws Exception {
        Path root = Files.createTempDirectory("modsync-desktop-recommended-");
        Map<String, String> previous = snapshotProperties("os.name", "modsync.forceMobile");
        try {
            System.setProperty("os.name", "Windows 11");
            System.clearProperty("modsync.forceMobile");
            RecommendedSelectionStore.resetSessionForTests();
            byte[] requiredBytes = "required".getBytes(StandardCharsets.UTF_8);
            byte[] recommendedBytes = "recommended".getBytes(StandardCharsets.UTF_8);
            ManifestEntry required = testEntry(requiredBytes, "required_mod", "required.jar", ModKind.REQUIRED, Set.of());
            ManifestEntry recommended = testEntry(
                    recommendedBytes, "recommended_mod", "recommended.jar", ModKind.RECOMMENDED, Set.of());
            ManifestEntry incompatible = testEntry(
                    "linux-only".getBytes(StandardCharsets.UTF_8),
                    "linux_only", "linux-only.jar", ModKind.RECOMMENDED, Set.of(ClientPlatform.WINDOWS));
            AtomicInteger prompts = new AtomicInteger();
            SyncObserver observer = new SyncObserver() {
                @Override
                public Set<String> chooseRecommendedMods(RecommendedSelectionRequest request) {
                    prompts.incrementAndGet();
                    check(request.initiallySelected().contains(recommended.selectionKey()),
                            "兼容推荐模组应默认勾选");
                    check(!request.initiallySelected().contains(incompatible.selectionKey()),
                            "不兼容推荐模组不应默认勾选");
                    return Set.of();
                }
            };
            List<String> logs = new ArrayList<>();
            ModManifest first = ModManifest.fromEntries("catalog-1", List.of(required, recommended, incompatible));
            var firstResolution = RecommendedSelectionStore.resolve(
                    first, root, Map.of(), URI.create("https://example.invalid/mods.txt"),
                    RuntimeEnvironment.detect(), observer, logs::add);
            check(firstResolution.effectiveManifest().entries().equals(List.of(required)),
                    "取消全部后只应保留必须模组");
            RecommendedSelectionStore.resolve(
                    first, root, Map.of(), URI.create("https://example.invalid/mods.txt"),
                    RuntimeEnvironment.detect(), observer, logs::add);
            check(prompts.get() == 1, "相同清单版本应直接复用历史选择");

            ModManifest updated = ModManifest.fromEntries("catalog-2", List.of(required, recommended));
            RecommendedSelectionStore.resolve(
                    updated, root, Map.of(), URI.create("https://example.invalid/mods.txt"),
                    RuntimeEnvironment.detect(), observer, logs::add);
            check(prompts.get() == 2, "清单版本更新后应重新选择");
            check(logs.stream().anyMatch(line -> line.contains("catalog-1 -> catalog-2")),
                    "清单版本更新应写入日志");
            pass("desktop recommended selection and catalog update");
        } finally {
            restoreProperties(previous);
            RecommendedSelectionStore.resetSessionForTests();
            deleteTree(root);
        }
    }

    private void testMobileRecommendedDownloadsOncePerCatalogVersion() throws Exception {
        Path root = Files.createTempDirectory("modsync-mobile-recommended-once-");
        Map<String, String> previous = snapshotProperties("modsync.forceMobile", "os.name");
        try {
            System.setProperty("modsync.forceMobile", "true");
            System.setProperty("os.name", "Linux");
            RecommendedSelectionStore.resetSessionForTests();
            byte[] requiredBytes = "required".getBytes(StandardCharsets.UTF_8);
            byte[] recommendedBytes = "recommended".getBytes(StandardCharsets.UTF_8);
            ManifestEntry required = testEntry(requiredBytes, "required_mod", "required.jar", ModKind.REQUIRED, Set.of());
            ManifestEntry recommended = testEntry(
                    recommendedBytes, "recommended_mod", "recommended.jar", ModKind.RECOMMENDED, Set.of());
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path requiredFile = mods.resolve(required.fileName());
            Files.write(requiredFile, requiredBytes);
            Map<String, Path> local = Map.of(required.fileName(), requiredFile);
            List<String> logs = new ArrayList<>();
            ModManifest first = ModManifest.fromEntries("mobile-1", List.of(required, recommended));
            var initial = RecommendedSelectionStore.resolve(
                    first, root, local, URI.create("https://example.invalid/mods.txt"),
                    RuntimeEnvironment.detect(), SyncObserver.NONE, logs::add);
            check(initial.mobileNeedsCompletion(), "手机端首次应安排全部兼容推荐模组");
            check(initial.effectiveManifest().entries().contains(recommended), "首次应包含推荐模组");
            RecommendedSelectionStore.markMobileCompleted(initial);

            var afterDeletion = RecommendedSelectionStore.resolve(
                    first, root, local, URI.create("https://example.invalid/mods.txt"),
                    RuntimeEnvironment.detect(), SyncObserver.NONE, logs::add);
            check(!afterDeletion.effectiveManifest().entries().contains(recommended),
                    "手机端推荐模组被删除后不得二次自动下载");
            check(logs.stream().anyMatch(line -> line.contains("手动下载地址")),
                    "删除推荐模组后应记录手动下载方式");

            ModManifest updated = ModManifest.fromEntries("mobile-2", List.of(required, recommended));
            var nextCatalog = RecommendedSelectionStore.resolve(
                    updated, root, local, URI.create("https://example.invalid/mods.txt"),
                    RuntimeEnvironment.detect(), SyncObserver.NONE, logs::add);
            check(nextCatalog.mobileNeedsCompletion(), "新推荐清单版本应获得一次新的自动处理机会");
            check(logs.stream().anyMatch(line -> line.contains("mobile-1 -> mobile-2")),
                    "手机端推荐清单更新应写入日志");
            pass("mobile recommended downloads once per catalog version");
        } finally {
            restoreProperties(previous);
            RecommendedSelectionStore.resetSessionForTests();
            deleteTree(root);
        }
    }

    private void testDeselectedRecommendedModIsBackedUp() throws Exception {
        Path root = Files.createTempDirectory("modsync-deselected-recommended-");
        Map<String, String> previous = snapshotProperties("os.name", "modsync.forceMobile");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            System.setProperty("os.name", "Windows 11");
            System.clearProperty("modsync.forceMobile");
            RecommendedSelectionStore.resetSessionForTests();
            Path mods = Files.createDirectories(root.resolve("mods"));
            byte[] requiredBytes = "required local".getBytes(StandardCharsets.UTF_8);
            byte[] recommendedBytes = "recommended local".getBytes(StandardCharsets.UTF_8);
            ManifestEntry required = testEntry(requiredBytes, "", "required.jar", ModKind.REQUIRED, Set.of());
            ManifestEntry recommended = testEntry(
                    recommendedBytes, "", "recommended.jar", ModKind.RECOMMENDED, Set.of());
            Files.write(mods.resolve(required.fileName()), requiredBytes);
            Files.write(mods.resolve(recommended.fileName()), recommendedBytes);
            String manifest = ModManifest.fromEntries("desktop-backup-1", List.of(required, recommended)).serialize();
            server.createContext("/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.start();
            URI uri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/mods.txt");
            SyncObserver observer = new SyncObserver() {
                @Override
                public Set<String> chooseRecommendedMods(RecommendedSelectionRequest request) {
                    return Set.of();
                }

                @Override
                public UnknownModDecision decideUnknownClientMod(String fileName) {
                    return UnknownModDecision.KEEP_CLIENT;
                }
            };
            SyncResult result = new ModSyncEngine(config(root, uri, true, true), message -> { }, observer)
                    .synchronize();
            check(result.status() == SyncResult.Status.UPDATED, "取消已安装推荐模组应触发更新事务");
            check(!Files.exists(mods.resolve(recommended.fileName())), "取消的推荐模组应从 mods 移出");
            try (var files = Files.walk(root.resolve(".modsync/backups"))) {
                check(files.anyMatch(path -> path.getFileName().toString().equals(recommended.fileName())),
                        "取消的推荐模组应保存在备份目录");
            }
            pass("deselected recommended mod is backed up");
        } finally {
            server.stop(0);
            restoreProperties(previous);
            RecommendedSelectionStore.resetSessionForTests();
            deleteTree(root);
        }
    }

    private void testNoRecommendedModsSelectedAllowsEmptyModsDirectory() throws Exception {
        Path root = Files.createTempDirectory("modsync-no-recommended-selected-");
        Map<String, String> previous = snapshotProperties("os.name", "modsync.forceMobile");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            System.setProperty("os.name", "Windows 11");
            System.clearProperty("modsync.forceMobile");
            RecommendedSelectionStore.resetSessionForTests();
            Files.createDirectories(root.resolve("mods"));
            ManifestEntry recommended = testEntry(
                    "optional".getBytes(StandardCharsets.UTF_8),
                    "optional_mod", "optional.jar", ModKind.RECOMMENDED, Set.of());
            String manifest = ModManifest.fromEntries("empty-choice-1", List.of(recommended)).serialize();
            server.createContext("/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.start();
            URI uri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/mods.txt");
            SyncObserver observer = new SyncObserver() {
                @Override
                public Set<String> chooseRecommendedMods(RecommendedSelectionRequest request) {
                    return Set.of();
                }
            };
            SyncResult result = new ModSyncEngine(config(root, uri, true, true), message -> { }, observer)
                    .synchronize();
            check(result.status() == SyncResult.Status.UNCHANGED,
                    "不选择任何推荐模组时应允许空 mods 目录继续启动");
            pass("no recommended mods selected allows empty mods directory");
        } finally {
            server.stop(0);
            restoreProperties(previous);
            RecommendedSelectionStore.resetSessionForTests();
            deleteTree(root);
        }
    }

    private static ManifestEntry testEntry(
            byte[] bytes,
            String modId,
            String fileName,
            ModKind kind,
            Set<ClientPlatform> incompatible) {
        return new ManifestEntry(
                Hashing.sha256(bytes),
                Hashing.md5(bytes),
                modId,
                fileName,
                kind,
                incompatible,
                modId,
                "1.0",
                "test mod");
    }

    private void testPublisherManifestIncludesSyncTool() throws Exception {
        Path root = Files.createTempDirectory("modsync-publisher-self-update-");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            writeFabricJar(mods.resolve("MCModSync-1.6.9.jar"), "mcmodsync", "1.6.9");
            writeFabricJar(mods.resolve("managed.jar"), "managed_mod", "managed");

            ModManifest published = ModManifest.scan(mods);
            published.ensureUniqueModIds();
            check(published.entries().size() == 2, "发布清单应包含同步工具本身和普通 Mod");
            check(published.entries().stream().anyMatch(entry -> entry.modId().equals("mcmodsync")),
                    "发布清单必须包含 mcmodsync，才能自更新");
            check(published.entries().stream().anyMatch(entry -> entry.modId().equals("managed_mod")),
                    "发布清单应保留普通 Mod");
            pass("publisher includes sync tool for self update");
        } finally {
            deleteTree(root);
        }
    }

    private void testSelfDowngradeIsRefused() throws Exception {
        Path root = Files.createTempDirectory("modsync-self-downgrade-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path localUpdater = mods.resolve("MCModSync-1.6.9.jar");
            writeFabricJar(localUpdater, "mcmodsync", "1.6.9");
            Path oldSource = root.resolve("MCModSync-1.5.0.jar");
            writeFabricJar(oldSource, "mcmodsync", "1.5.0");
            byte[] oldBytes = Files.readAllBytes(oldSource);
            String manifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(oldBytes) + "\tmcmodsync\tMCModSync-1.5.0.jar\n";
            AtomicInteger oldDownloadRequests = new AtomicInteger();
            server.createContext("/mods/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/mods/MCModSync-1.5.0.jar", exchange -> {
                oldDownloadRequests.incrementAndGet();
                respond(exchange, 200, oldBytes, null);
            });
            server.start();

            URI manifestUri = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/mods/mods.txt");
            ModSyncConfig config = config(root, manifestUri, true, true);
            SyncProbeResult probe = new ModSyncEngine(config, message -> { }).probeWithoutJarChanges();
            check(probe.status() == SyncProbeResult.Status.UP_TO_DATE,
                    "云端同步器版本较旧时不应要求退出并降级");
            SyncResult result = new ModSyncEngine(config, message -> { }).synchronize();
            check(result.status() == SyncResult.Status.UNCHANGED, "较旧同步器应被忽略");
            check(Files.isRegularFile(localUpdater), "本地新版同步器必须保留");
            check(!Files.exists(mods.resolve("MCModSync-1.5.0.jar")), "云端旧版同步器不得安装");
            check(oldDownloadRequests.get() == 0, "不应下载已知版本号更旧的同步器");
            pass("self downgrade is refused");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testResourcePackManifestGenerationAndParsing() throws Exception {
        Path root = Files.createTempDirectory("modsync-resourcepack-manifest-");
        try {
            Path resourcePack = root.resolve("世界指定资源包喵.zip");
            byte[] content = "resource pack v1".getBytes(StandardCharsets.UTF_8);
            Files.write(resourcePack, content);
            ResourcePackManifest generated = ResourcePackManifest.fromFile(resourcePack);
            String text = generated.serialize();
            ResourcePackManifest parsed = ResourcePackManifest.parse(text);
            check(text.contains("# minecraft=1.21.1,1.21.11\n"),
                    "资源包清单应声明两个已验证目标版本");
            check(parsed.entries().size() == 1, "资源包清单应包含一个 ZIP");
            check(parsed.entries().get(0).fileName().equals("世界指定资源包喵.zip"), "资源包中文文件名应保留");
            check(parsed.entries().get(0).md5().equals(Hashing.md5(content)), "资源包清单 MD5 应正确");
            expectFailure(() -> ResourcePackManifest.parse(
                    ResourcePackManifest.MAGIC + "\n00000000000000000000000000000000\t../evil.zip\n"));
            pass("resource pack manifest generation and parsing");
        } finally {
            deleteTree(root);
        }
    }

    private void testServerListManifestGenerationAndParsing() throws Exception {
        Path root = Files.createTempDirectory("modsync-serverlist-manifest-");
        try {
            Path serversDat = root.resolve("servers.dat");
            ServerListNbt.writeSimple(serversDat, List.of(
                    new ServerListNbt.ServerInfo("主服务器", "play.example.test")));
            ServerListManifest generated = ServerListManifest.fromFile(serversDat);
            String text = generated.serialize();
            ServerListManifest parsed = ServerListManifest.parse(text);
            check(text.contains("# minecraft=1.21.1,1.21.11\n"),
                    "服务器列表清单应声明两个已验证目标版本");
            check(parsed.md5().equals(Hashing.md5(serversDat)), "服务器列表清单 MD5 应正确");
            expectFailure(() -> ServerListManifest.parse(
                    ServerListManifest.MAGIC + "\n00000000000000000000000000000000\t../servers.dat\n"));
            pass("server list manifest generation and parsing");
        } finally {
            deleteTree(root);
        }
    }

    private void testPathEncoding() {
        check(
                Rfc3986.encodePathSegment("测试 mod+1.jar").equals("%E6%B5%8B%E8%AF%95%20mod%2B1.jar"),
                "URL 路径段应使用 UTF-8 百分号编码");
        pass("path encoding");
    }

    private void testRequiredManifestRetriesTransientFailuresOverHttp11() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicInteger requests = new AtomicInteger();
        byte[] expected = (ModManifest.MAGIC + "\n").getBytes(StandardCharsets.UTF_8);
        server.createContext("/mods.txt", exchange -> {
            if (requests.incrementAndGet() < 3) {
                respond(exchange, 500, "temporary".getBytes(StandardCharsets.UTF_8), null);
            } else {
                respond(exchange, 200, expected, null);
            }
        });
        server.start();
        try {
            HttpClient client = RequiredManifestFetcher.createClient(Duration.ofSeconds(2));
            check(client.version() == HttpClient.Version.HTTP_1_1,
                    "云盘清单客户端应固定使用 HTTP/1.1，规避重定向链偶发 HTTP/2 EOF");
            AtomicInteger retryMessages = new AtomicInteger();
            byte[] actual = RequiredManifestFetcher.fetch(
                    client,
                    URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/mods.txt"),
                    Duration.ofSeconds(2),
                    1024,
                    "MCModSync/test",
                    "测试清单",
                    message -> retryMessages.incrementAndGet());
            check(Arrays.equals(actual, expected), "瞬时故障后应取得完整清单");
            check(requests.get() == 3 && retryMessages.get() == 2, "清单应在失败后最多重试三次");
            pass("required manifests retry transient failures over HTTP/1.1");
        } finally {
            server.stop(0);
        }
    }

    private void testDetectedGameDirectoryWinsOverAmbiguousCommandLine() throws Exception {
        Path root = Files.createTempDirectory("modsync detected game dir ");
        String previousCommand = System.getProperty("sun.java.command");
        String previousOverride = System.getProperty("modsync.gameDir");
        try {
            Path detected = Files.createDirectories(root.resolve("versions/1.21.11-Fabric 0.19.3"));
            System.clearProperty("modsync.gameDir");
            System.setProperty(
                    "sun.java.command",
                    "net.fabricmc.loader.impl.launch.knot.KnotClient --gameDir "
                            + root.resolve("versions/1.21.11-Fabric") + " 0.19.3 --assetsDir ignored");
            ModSyncConfig config = ModSyncConfig.fromEnvironment(null, detected);
            check(config.gameDirectory().equals(detected.toAbsolutePath().normalize()),
                    "Fabric Loader 检测目录应优先于可能丢失引号的 sun.java.command");
            pass("detected Fabric game directory wins over ambiguous command line");
        } finally {
            restoreProperty("sun.java.command", previousCommand);
            restoreProperty("modsync.gameDir", previousOverride);
            deleteTree(root);
        }
    }

    private void testUnquotedGameDirectoryWithSpacesCanBeParsed() throws Exception {
        Path root = Files.createTempDirectory("modsync command game dir ");
        String previousCommand = System.getProperty("sun.java.command");
        String previousOverride = System.getProperty("modsync.gameDir");
        try {
            Path expected = root.resolve("versions/专用客户端 Fabric 0.19.3").toAbsolutePath().normalize();
            System.clearProperty("modsync.gameDir");
            System.setProperty(
                    "sun.java.command",
                    "net.fabricmc.loader.impl.launch.knot.KnotClient --username test --gameDir "
                            + expected + " --assetsDir ignored");
            ModSyncConfig config = ModSyncConfig.fromEnvironment(null, null);
            check(config.gameDirectory().equals(expected), "无引号且带空格的 --gameDir 应完整解析到下一个参数前");
            pass("unquoted game directory with spaces can be parsed");
        } finally {
            restoreProperty("sun.java.command", previousCommand);
            restoreProperty("modsync.gameDir", previousOverride);
            deleteTree(root);
        }
    }

    private void testInstanceGuard() throws Exception {
        Path root = Files.createTempDirectory("modsync-lock-");
        try (InstanceGuard first = InstanceGuard.acquire(root)) {
            try {
                InstanceGuard.acquire(root);
                throw new AssertionError("第二个实例锁不应成功");
            } catch (InstanceGuard.AlreadyRunningException expected) {
                check(expected.getMessage().contains("正在同步更新"), "重复启动应返回可识别的忙碌状态");
            }
            pass("single-instance guard");
        } finally {
            deleteTree(root);
        }
    }

    private void testRedirectDownloadStrictSyncAndBackup() throws Exception {
        Path root = Files.createTempDirectory("modsync-integration-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            byte[] newMod = "new tested mod bytes".getBytes(StandardCharsets.UTF_8);
            String fileName = "测试 mod.jar";
            String manifest = ModManifest.MAGIC + "\n"
                    + "# minecraft=1.21.11\n"
                    + "# loader=fabric\n"
                    + Hashing.md5(newMod) + "\t-\t" + fileName + "\n";

            server.createContext("/base/mods.txt", exchange -> respond(exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/base/", exchange -> {
                String expected = "/base/%E6%B5%8B%E8%AF%95%20mod.jar";
                if (!exchange.getRequestURI().getRawPath().equals(expected)) {
                    respond(exchange, 400, "bad encoding".getBytes(StandardCharsets.UTF_8), null);
                    return;
                }
                respond(exchange, 302, new byte[0], "/blob/temporary-signed-url");
            });
            server.createContext("/blob/temporary-signed-url", exchange -> respond(exchange, 200, newMod, null));
            server.start();

            Path mods = Files.createDirectories(root.resolve("mods"));
            Files.writeString(mods.resolve(fileName), "old bytes");
            Files.writeString(mods.resolve("extra.jar"), "extra local mod");
            Files.writeString(mods.resolve("client-only.jar"), "user client mod");
            Path state = Files.createDirectories(root.resolve(".modsync"));
            String previousServerManifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5("old bytes".getBytes(StandardCharsets.UTF_8)) + "\t-\t" + fileName + "\n"
                    + Hashing.md5("extra local mod".getBytes(StandardCharsets.UTF_8)) + "\t-\textra.jar\n";
            Files.writeString(state.resolve("server-manifest.txt"), previousServerManifest, StandardCharsets.UTF_8);

            URI manifestUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt");
            ModSyncConfig config = config(root, manifestUri, true, true);
            AtomicBoolean planObserved = new AtomicBoolean(false);
            AtomicBoolean completionObserved = new AtomicBoolean(false);
            AtomicBoolean progressObserved = new AtomicBoolean(false);
            AtomicBoolean verificationPhaseObserved = new AtomicBoolean(false);
            SyncObserver observer = new SyncObserver() {
                @Override
                public RemovalDecision decideServerRemoved(List<String> serverRemoved) {
                    check(serverRemoved.equals(List.of("extra.jar")), "应只把上次由服务器管理的文件识别为服务器移除");
                    return RemovalDecision.BACKUP;
                }

                @Override
                public UnknownModDecision decideUnknownClientMod(String fileName) {
                    check(fileName.equals("client-only.jar"), "首次未知文件应为测试客户端 Mod");
                    return UnknownModDecision.KEEP_CLIENT;
                }

                @Override
                public void beforeDownload(
                        List<String> downloads,
                        List<String> replacedOldVersions,
                        List<String> rejectedUnknownMods,
                        List<String> quarantined,
                        List<String> retainedServerRemoved,
                        List<String> retainedClientMods) {
                    check(downloads.equals(List.of(fileName)), "下载提示应列出目标 Mod");
                    check(replacedOldVersions.isEmpty(), "无 Mod ID 的测试文件不应识别为改名升级");
                    check(rejectedUnknownMods.isEmpty(), "已有身份记录时不应出现首次未知 Mod");
                    check(quarantined.equals(List.of("extra.jar")), "下载提示应列出被隔离 Mod");
                    check(retainedServerRemoved.isEmpty(), "本次没有选择保留服务器移除 Mod");
                    check(retainedClientMods.equals(List.of("client-only.jar")), "用户客户端 Mod 应列出并保留");
                    planObserved.set(true);
                }

                @Override
                public void phaseChanged(String message) {
                    if (message.contains("校验 MD5")) {
                        verificationPhaseObserved.set(true);
                    }
                }

                @Override
                public void downloadProgress(DownloadProgress progress) {
                    check(progress.fileName().equals(fileName), "进度事件应标明当前文件");
                    check(progress.fileIndex() == 1 && progress.fileCount() == 1, "进度事件应标明文件序号");
                    check(progress.fileDownloadedBytes() >= 0, "进度事件字节数不能为负");
                    if (progress.fileDownloadedBytes() == newMod.length
                            && progress.fileTotalBytes() == newMod.length
                            && progress.totalDownloadedBytes() == newMod.length
                            && progress.totalBytes() == newMod.length
                            && progress.totalPermille() == 1000) {
                        progressObserved.set(true);
                    }
                }

                @Override
                public void afterUpdate(int downloaded, int quarantined, int unchanged) {
                    check(downloaded == 1 && quarantined == 1, "完成提示统计应正确");
                    completionObserved.set(true);
                }
            };
            SyncResult first = new ModSyncEngine(config, message -> { }, observer).synchronize();

            check(first.status() == SyncResult.Status.UPDATED, "第一次应完成更新");
            check(first.downloaded() == 1, "应下载一个文件");
            check(first.quarantined() == 1, "应隔离一个额外文件");
            check(planObserved.get(), "自动下载前应发出非确认型内容提示");
            check(progressObserved.get(), "下载时应发出基于真实字节数的完成进度");
            check(verificationPhaseObserved.get(), "下载后应显示 MD5 校验阶段");
            check(completionObserved.get(), "自动下载后应发出完成提示");
            check(Arrays.equals(Files.readAllBytes(mods.resolve(fileName)), newMod), "应安装下载且校验后的文件");
            check(!Files.exists(mods.resolve("extra.jar")), "额外 Mod 不应留在 mods 目录");
            check(Files.isRegularFile(mods.resolve("client-only.jar")), "用户自行添加的客户端 Mod 必须保留");

            Path backups = root.resolve(".modsync/backups");
            List<String> backupNames;
            try (var paths = Files.walk(backups)) {
                backupNames = paths.filter(Files::isRegularFile)
                        .map(path -> path.getFileName().toString())
                        .toList();
            }
            check(backupNames.contains(fileName), "被替换的旧 Mod 应备份");
            check(backupNames.contains("extra.jar"), "清单外 Mod 应备份");

            SyncResult second = new ModSyncEngine(config, message -> { }).synchronize();
            check(second.status() == SyncResult.Status.UNCHANGED, "第二次应识别为完全一致");
            ModManifest.parse(Files.readString(mods.resolve("mods.txt"), StandardCharsets.UTF_8)).verifySnapshot(mods);
            pass("redirect download, strict sync and backup");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testParallelModDownloadFallsBackToSingleThread() throws Exception {
        Path root = Files.createTempDirectory("modsync-parallel-fallback-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        ExecutorService serverExecutor = Executors.newCachedThreadPool();
        server.setExecutor(serverExecutor);
        CountDownLatch firstParallelRound = new CountDownLatch(2);
        AtomicInteger aGets = new AtomicInteger();
        AtomicInteger bGets = new AtomicInteger();
        AtomicInteger activeGets = new AtomicInteger();
        AtomicInteger maximumActiveGets = new AtomicInteger();
        try {
            byte[] aBytes = "parallel-a".getBytes(StandardCharsets.UTF_8);
            byte[] bBytes = "parallel-b".getBytes(StandardCharsets.UTF_8);
            String manifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(aBytes) + "\t-\ta.jar\n"
                    + Hashing.md5(bBytes) + "\t-\tb.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/base/a.jar", exchange -> {
                if (exchange.getRequestMethod().equalsIgnoreCase("HEAD")) {
                    respond(exchange, 200, aBytes, null);
                    return;
                }
                int request = aGets.incrementAndGet();
                int active = activeGets.incrementAndGet();
                maximumActiveGets.accumulateAndGet(active, Math::max);
                try {
                    if (request == 1) {
                        firstParallelRound.countDown();
                        firstParallelRound.await(3, TimeUnit.SECONDS);
                        respond(exchange, 500, "parallel attempt failed".getBytes(StandardCharsets.UTF_8), null);
                    } else {
                        respond(exchange, 200, aBytes, null);
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    exchange.close();
                } finally {
                    activeGets.decrementAndGet();
                }
            });
            server.createContext("/base/b.jar", exchange -> {
                if (exchange.getRequestMethod().equalsIgnoreCase("HEAD")) {
                    respond(exchange, 200, bBytes, null);
                    return;
                }
                int request = bGets.incrementAndGet();
                int active = activeGets.incrementAndGet();
                maximumActiveGets.accumulateAndGet(active, Math::max);
                try {
                    if (request == 1) {
                        firstParallelRound.countDown();
                        firstParallelRound.await(3, TimeUnit.SECONDS);
                    }
                    respond(exchange, 200, bBytes, null);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    exchange.close();
                } finally {
                    activeGets.decrementAndGet();
                }
            });
            server.start();

            Files.createDirectories(root.resolve("mods"));
            AtomicBoolean fallbackShown = new AtomicBoolean();
            SyncObserver observer = new SyncObserver() {
                @Override
                public void phaseChanged(String message) {
                    if (message.contains("回退单线程")) {
                        fallbackShown.set(true);
                    }
                }
            };
            URI manifestUri = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt");
            SyncResult result = new ModSyncEngine(
                    config(root, manifestUri, true, true), message -> { }, observer).synchronize();

            check(result.status() == SyncResult.Status.UPDATED && result.downloaded() == 2,
                    "并发失败后单线程回退应完成两个 Mod 更新");
            check(maximumActiveGets.get() >= 2, "首轮应确实同时发起至少两个下载");
            check(aGets.get() == 2 && bGets.get() == 2,
                    "并发失败后应清理首轮内容并用单线程完整重下");
            check(fallbackShown.get(), "并发失败时进度窗口应说明正在回退单线程");
            check(Arrays.equals(Files.readAllBytes(root.resolve("mods/a.jar")), aBytes), "a.jar 应正确安装");
            check(Arrays.equals(Files.readAllBytes(root.resolve("mods/b.jar")), bBytes), "b.jar 应正确安装");
            pass("parallel Mod download falls back to single thread");
        } finally {
            server.stop(0);
            serverExecutor.shutdownNow();
            deleteTree(root);
        }
    }

    private void testResourcePackMd5SyncAndClientPreservation() throws Exception {
        Path root = Files.createTempDirectory("modsync-resourcepack-sync-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            String fileName = "世界指定资源包喵.zip";
            byte[] oldPack = "old resource pack".getBytes(StandardCharsets.UTF_8);
            byte[] newPack = "new tested resource pack".getBytes(StandardCharsets.UTF_8);
            String manifest = ResourcePackManifest.MAGIC + "\n"
                    + Hashing.md5(newPack) + "\t" + fileName + "\n";
            server.createContext("/packs/resourcepacks.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/packs/", exchange -> {
                String expected = "/packs/%E4%B8%96%E7%95%8C%E6%8C%87%E5%AE%9A%E8%B5%84%E6%BA%90%E5%8C%85%E5%96%B5.zip";
                if (!exchange.getRequestURI().getRawPath().equals(expected)) {
                    respond(exchange, 400, "bad resource pack encoding".getBytes(StandardCharsets.UTF_8), null);
                    return;
                }
                respond(exchange, 200, newPack, null);
            });
            server.start();

            Path resourcePacks = Files.createDirectories(root.resolve("resourcepacks"));
            Files.write(resourcePacks.resolve(fileName), oldPack);
            Path clientPack = resourcePacks.resolve("玩家自己添加.zip");
            byte[] clientBytes = "client pack".getBytes(StandardCharsets.UTF_8);
            Files.write(clientPack, clientBytes);
            Path state = Files.createDirectories(root.resolve(".modsync"));
            Files.writeString(
                    state.resolve("resourcepack-manifest.txt"),
                    ResourcePackManifest.MAGIC + "\n" + Hashing.md5(oldPack) + "\t" + fileName + "\n",
                    StandardCharsets.UTF_8);

            URI resourceManifest = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/packs/resourcepacks.txt");
            ModSyncConfig config = resourceConfig(root, resourceManifest);
            AtomicBoolean planObserved = new AtomicBoolean(false);
            AtomicBoolean progressObserved = new AtomicBoolean(false);
            SyncObserver observer = new SyncObserver() {
                @Override
                public void beforeResourcePackDownload(
                        List<String> downloads,
                        List<String> backedUpRemoved) {
                    check(downloads.equals(List.of(fileName)), "资源包提示应列出需要替换的 ZIP");
                    check(backedUpRemoved.isEmpty(), "同名 MD5 替换不属于云端移除");
                    planObserved.set(true);
                }

                @Override
                public void downloadProgress(DownloadProgress progress) {
                    if (progress.fileName().equals(fileName)
                            && progress.fileDownloadedBytes() == newPack.length
                            && progress.fileTotalBytes() == newPack.length
                            && progress.totalPermille() == 1000) {
                        progressObserved.set(true);
                    }
                }
            };

            SyncResult first = new ResourcePackSyncEngine(config, message -> { }, observer).synchronize();
            check(first.status() == SyncResult.Status.UPDATED, "资源包 MD5 不同时应完成更新");
            check(Arrays.equals(Files.readAllBytes(resourcePacks.resolve(fileName)), newPack),
                    "资源包应替换为通过 MD5 校验的云端内容");
            check(Arrays.equals(Files.readAllBytes(clientPack), clientBytes), "玩家自行添加的资源包必须保留");
            check(planObserved.get(), "资源包自动下载前应显示内容提示");
            check(progressObserved.get(), "资源包下载应发出真实字节和总进度");

            try (var backups = Files.walk(state.resolve("backups/resourcepacks"))) {
                check(backups.filter(Files::isRegularFile)
                                .anyMatch(path -> path.getFileName().toString().equals(fileName)),
                        "旧资源包应进入可恢复备份");
            }
            SyncResult second = new ResourcePackSyncEngine(config, message -> { }).synchronize();
            check(second.status() == SyncResult.Status.UNCHANGED, "资源包 MD5 一致时不应重复下载");
            pass("resource pack MD5 sync and client pack preservation");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testMissingLocalManifestAsksAboutEveryUnknownMod() throws Exception {
        Path root = Files.createTempDirectory("modsync-first-unknown-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path managed = mods.resolve("managed.jar");
            Path pureClient = mods.resolve("pure-client.jar");
            Path rejected = mods.resolve("unknown-addon.jar");
            writeFabricJar(managed, "managed_mod", "managed");
            writeFabricJar(pureClient, "pure_client", "client");
            writeFabricJar(rejected, "unknown_addon", "unknown");
            String manifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(managed) + "\tmanaged_mod\tmanaged.jar\n";
            server.createContext("/mods/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.start();

            AtomicInteger questions = new AtomicInteger();
            AtomicBoolean planObserved = new AtomicBoolean();
            SyncObserver observer = new SyncObserver() {
                @Override
                public UnknownModDecision decideUnknownClientMod(String fileName) {
                    questions.incrementAndGet();
                    return fileName.equals("pure-client.jar")
                            ? UnknownModDecision.KEEP_CLIENT
                            : UnknownModDecision.BACKUP;
                }

                @Override
                public void beforeDownload(
                        List<String> downloads,
                        List<String> replacedOldVersions,
                        List<String> rejectedUnknownMods,
                        List<String> quarantinedServerRemoved,
                        List<String> retainedServerRemoved,
                        List<String> retainedClientMods) {
                    check(downloads.isEmpty(), "服务器管理 Mod 已一致时无需下载");
                    check(rejectedUnknownMods.equals(List.of("unknown-addon.jar")),
                            "确认不是纯客户端的未知 Mod 应列入备份计划");
                    check(retainedClientMods.equals(List.of("pure-client.jar")),
                            "确认是纯客户端的 Mod 应列入保留计划");
                    planObserved.set(true);
                }
            };
            URI uri = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/mods/mods.txt");
            ModSyncConfig config = config(root, uri, true, true);
            SyncResult first = new ModSyncEngine(config, message -> { }, observer).synchronize();
            check(first.status() == SyncResult.Status.UPDATED, "拒绝的未知 Mod 应移入备份");
            check(questions.get() == 2, "mods.txt 原本不存在时应逐个询问所有云端没有的 Mod");
            check(planObserved.get(), "首次未知 Mod 的处理结果应显示在计划中");
            check(Files.isRegularFile(pureClient), "确认的纯客户端 Mod 必须保留");
            check(!Files.exists(rejected), "确认不是纯客户端的 Mod 不应继续留在 mods");
            String snapshot = Files.readString(mods.resolve("mods.txt"), StandardCharsets.UTF_8);
            check(snapshot.contains("pure-client.jar") && !snapshot.contains("unknown-addon.jar"),
                    "最终 mods.txt 应记录确认后的本地组合");
            try (var backups = Files.walk(root.resolve(".modsync/backups"))) {
                check(backups.filter(Files::isRegularFile)
                                .anyMatch(path -> path.getFileName().toString().equals("unknown-addon.jar")),
                        "拒绝的未知 Mod 应保留可恢复备份");
            }
            SyncResult second = new ModSyncEngine(config, message -> { }, new SyncObserver() {
                @Override
                public UnknownModDecision decideUnknownClientMod(String fileName) {
                    throw new AssertionError("已有 mods.txt 后不应重复询问: " + fileName);
                }
            }).synchronize();
            check(second.status() == SyncResult.Status.UNCHANGED, "已确认身份后再次启动应直接校验");
            pass("missing local manifest asks about every unknown mod");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testBakaXLDualDirectoryResourcePackSync() throws Exception {
        Path root = Files.createTempDirectory("modsync-bakaxl-resourcepacks-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            Path minecraft = root.resolve("bakaxl/.minecraft");
            Path persistent = Files.createDirectories(minecraft.resolve("instances/资源包测试客户端"));
            Path runtime = Files.createDirectories(minecraft.resolve("versions/资源包测试客户端"));
            byte[] packageInfo = "same-bakaxl-package".getBytes(StandardCharsets.UTF_8);
            Files.write(persistent.resolve("package.info"), packageInfo);
            Files.write(runtime.resolve("package.info"), packageInfo);

            byte[] managedMod = "same managed mod".getBytes(StandardCharsets.UTF_8);
            for (Path target : List.of(persistent, runtime)) {
                Path mods = Files.createDirectories(target.resolve("mods"));
                Files.write(mods.resolve("managed.jar"), managedMod);
                Path packs = Files.createDirectories(target.resolve("resourcepacks"));
                Files.write(packs.resolve("玩家保留.zip"), ("client-" + target).getBytes(StandardCharsets.UTF_8));
            }

            String resourceName = "世界指定资源包喵.zip";
            byte[] resourceBytes = "dual target resource pack".getBytes(StandardCharsets.UTF_8);
            String modManifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(managedMod) + "\t-\tmanaged.jar\n";
            String resourceManifest = ResourcePackManifest.MAGIC + "\n"
                    + Hashing.md5(resourceBytes) + "\t" + resourceName + "\n";
            server.createContext("/mods/mods.txt", exchange -> respond(
                    exchange, 200, modManifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/packs/resourcepacks.txt", exchange -> respond(
                    exchange, 200, resourceManifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/packs/", exchange -> respond(exchange, 200, resourceBytes, null));
            server.start();

            URI modUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/mods/mods.txt");
            URI resourceUri = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/packs/resourcepacks.txt");
            ModSyncConfig config = new ModSyncConfig(
                    modUri,
                    resourceUri,
                    modUri,
                    runtime,
                    runtime,
                    true,
                    false,
                    true,
                    true,
                    Duration.ofSeconds(2),
                    Duration.ofSeconds(5),
                    1024 * 1024,
                    16 * 1024 * 1024,
                    3);

            SyncResult first = ModSyncCoordinator.synchronize(config, message -> { }, SyncObserver.NONE);
            check(first.status() == SyncResult.Status.UPDATED, "BakaXL 双目录资源包应完成同步");
            check(first.downloaded() == 2, "持久实例和运行副本应各下载一次资源包");
            for (Path target : List.of(persistent, runtime)) {
                Path installed = target.resolve("resourcepacks").resolve(resourceName);
                check(Arrays.equals(Files.readAllBytes(installed), resourceBytes),
                        "两个 BakaXL 目录都应安装相同 MD5 的资源包");
                check(Files.isRegularFile(target.resolve("resourcepacks/玩家保留.zip")),
                        "两个 BakaXL 目录的玩家资源包都必须保留");
            }

            SyncProbeResult probe = ModSyncCoordinator.probe(config, message -> { });
            check(probe.status() == SyncProbeResult.Status.UP_TO_DATE,
                    "双目录资源包完成后只读启动探测应完全一致");
            pass("BakaXL persistent/runtime resource packs synchronize together");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testBakaXLDualDirectoryServerListMerge() throws Exception {
        Path root = Files.createTempDirectory("modsync-bakaxl-server-list-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            Path minecraft = root.resolve("bakaxl/.minecraft");
            Path persistent = Files.createDirectories(minecraft.resolve("instances/服务器列表测试客户端"));
            Path runtime = Files.createDirectories(minecraft.resolve("versions/服务器列表测试客户端"));
            byte[] packageInfo = "same-server-list-package".getBytes(StandardCharsets.UTF_8);
            Files.write(persistent.resolve("package.info"), packageInfo);
            Files.write(runtime.resolve("package.info"), packageInfo);

            byte[] managedMod = "same managed mod".getBytes(StandardCharsets.UTF_8);
            Path oldCloud = root.resolve("old-cloud.dat");
            Path newCloud = root.resolve("new-cloud.dat");
            ServerListNbt.writeSimple(oldCloud, List.of(
                    new ServerListNbt.ServerInfo("旧名称", "managed.example.test"),
                    new ServerListNbt.ServerInfo("即将移除", "removed.example.test")));
            ServerListNbt.writeSimple(newCloud, List.of(
                    new ServerListNbt.ServerInfo("云端新名称", "managed.example.test"),
                    new ServerListNbt.ServerInfo("云端新增", "new.example.test")));
            byte[] cloudBytes = Files.readAllBytes(newCloud);

            for (Path target : List.of(persistent, runtime)) {
                Path mods = Files.createDirectories(target.resolve("mods"));
                Files.write(mods.resolve("managed.jar"), managedMod);
                ServerListNbt.writeSimple(target.resolve("servers.dat"), List.of(
                        new ServerListNbt.ServerInfo("旧名称", "managed.example.test"),
                        new ServerListNbt.ServerInfo("即将移除", "removed.example.test"),
                        new ServerListNbt.ServerInfo("玩家自己添加", "player-" + target.getParent().getFileName() + ".test")));
                Path state = Files.createDirectories(target.resolve(".modsync"));
                Files.copy(oldCloud, state.resolve("server-list-cloud.dat"));
                ServerListNbt.write(
                        state.resolve("server-list-managed-v1.dat"),
                        serverListManagedDocument(oldCloud));
            }

            String modManifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(managedMod) + "\t-\tmanaged.jar\n";
            String serverManifest = new ServerListManifest(Hashing.md5(newCloud)).serialize();
            server.createContext("/mods/mods.txt", exchange -> respond(
                    exchange, 200, modManifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/servers/serverlist.txt", exchange -> respond(
                    exchange, 200, serverManifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/servers/servers.dat", exchange -> respond(exchange, 200, cloudBytes, null));
            server.start();

            URI modUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/mods/mods.txt");
            URI serverUri = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/servers/serverlist.txt");
            ModSyncConfig config = new ModSyncConfig(
                    modUri,
                    modUri,
                    serverUri,
                    runtime,
                    runtime,
                    false,
                    true,
                    true,
                    true,
                    Duration.ofSeconds(2),
                    Duration.ofSeconds(5),
                    1024 * 1024,
                    16 * 1024 * 1024,
                    3);
            AtomicInteger planCount = new AtomicInteger();
            AtomicBoolean completedProgress = new AtomicBoolean();
            SyncObserver observer = new SyncObserver() {
                @Override
                public void beforeServerListDownload(String fileName) {
                    check(fileName.equals("servers.dat"), "服务器列表提示应指向 servers.dat");
                    planCount.incrementAndGet();
                }

                @Override
                public void downloadProgress(DownloadProgress progress) {
                    if (progress.fileName().equals("servers.dat") && progress.totalPermille() == 1000) {
                        completedProgress.set(true);
                    }
                }
            };

            SyncResult first = ModSyncCoordinator.synchronize(config, message -> { }, observer);
            check(first.status() == SyncResult.Status.UPDATED, "BakaXL 双目录服务器列表应完成同步");
            check(first.downloaded() == 2, "持久实例和运行副本应各下载一次 servers.dat");
            check(planCount.get() == 2, "两个同步目标都应显示自动下载内容提示");
            check(completedProgress.get(), "服务器列表同步应计入总进度并最终达到 100%");
            for (Path target : List.of(persistent, runtime)) {
                List<ServerListNbt.ServerInfo> entries = ServerListNbt.readServerInfo(target.resolve("servers.dat"));
                check(entries.equals(List.of(
                                new ServerListNbt.ServerInfo("云端新名称", "managed.example.test"),
                                new ServerListNbt.ServerInfo(
                                        "玩家自己添加", "player-" + target.getParent().getFileName() + ".test"),
                                new ServerListNbt.ServerInfo("云端新增", "new.example.test"))),
                        "受管服务器应在原位置更新，移除项不应扰动玩家顺序，云端新增项应追加到末尾");
                check(Files.isRegularFile(target.resolve(".modsync/server-list-managed-v1.dat")),
                        "同步后应持久化服务器列表所有权台账");
                try (var backups = Files.walk(target.resolve(".modsync/backups/server-list"))) {
                    check(backups.filter(Files::isRegularFile)
                                    .anyMatch(path -> path.getFileName().toString().equals("servers.dat")),
                            "原服务器列表应保留可恢复备份");
                }
            }
            SyncProbeResult probe = ModSyncCoordinator.probe(config, message -> { });
            check(probe.status() == SyncProbeResult.Status.UP_TO_DATE,
                    "双目录服务器列表完成后只读启动探测应完全一致");

            ServerListNbt.writeSimple(runtime.resolve("servers.dat"), List.of(
                    new ServerListNbt.ServerInfo("玩家后来添加", "late-player.test")));
            SyncProbeResult locallyEdited = ModSyncCoordinator.probe(config, message -> { });
            check(locallyEdited.status() == SyncProbeResult.Status.CHANGES_REQUIRED,
                    "玩家删改云端管理条目后应重新合并，而非只看云端缓存 MD5");
            SyncResult repaired = ModSyncCoordinator.synchronize(config, message -> { }, SyncObserver.NONE);
            check(repaired.status() == SyncResult.Status.UPDATED && repaired.downloaded() == 1,
                    "只应修复发生本地删改的 BakaXL 目标");
            List<ServerListNbt.ServerInfo> repairedEntries =
                    ServerListNbt.readServerInfo(runtime.resolve("servers.dat"));
            check(repairedEntries.stream().anyMatch(entry -> entry.address().equals("managed.example.test")),
                    "云端管理条目应恢复");
            check(repairedEntries.stream().anyMatch(entry -> entry.address().equals("late-player.test")),
                    "修复云端条目时仍应保留玩家后来添加的服务器");
            check(repairedEntries.equals(List.of(
                            new ServerListNbt.ServerInfo("玩家后来添加", "late-player.test"),
                            new ServerListNbt.ServerInfo("云端新名称", "managed.example.test"),
                            new ServerListNbt.ServerInfo("云端新增", "new.example.test"))),
                    "恢复缺失受管条目时应保留玩家条目位置，并把恢复项追加到末尾");
            pass("BakaXL server list three-way merge preserves player entries");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testOfflineAlwaysBlocks() throws Exception {
        Path root = Files.createTempDirectory("modsync-offline-");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Files.writeString(mods.resolve("local.jar"), "keep me");
            ModSyncConfig config = config(root, URI.create("http://127.0.0.1:1/mods.txt"), true, false);
            try {
                new ModSyncEngine(config, message -> { }).synchronize();
                throw new AssertionError("云端 Mod 清单故障时不得放行");
            } catch (IOException expected) {
                check(expected.getMessage().contains("已阻止启动"), "断网时应明确阻止启动");
            }
            check(Files.exists(mods.resolve("local.jar")), "断网时不能改动本地 Mod");
            check(Files.isRegularFile(mods.resolve("mods.txt")), "本地清单缺失时应自动生成");
            ModManifest.parse(Files.readString(mods.resolve("mods.txt"), StandardCharsets.UTF_8)).verifySnapshot(mods);
            pass("offline always blocks");
        } finally {
            deleteTree(root);
        }
    }

    private void testResourcePackAndServerListManifestFailuresBlock() throws Exception {
        Path root = Files.createTempDirectory("modsync-secondary-manifests-offline-");
        try {
            URI unreachable = URI.create("http://127.0.0.1:1/manifest.txt");
            ModSyncConfig config = new ModSyncConfig(
                    unreachable,
                    unreachable,
                    unreachable,
                    root,
                    root,
                    true,
                    true,
                    true,
                    false,
                    Duration.ofSeconds(1),
                    Duration.ofSeconds(2),
                    1024 * 1024,
                    16 * 1024 * 1024,
                    3);
            try {
                new ResourcePackSyncEngine(config, message -> { }).synchronize();
                throw new AssertionError("云端资源包清单故障时不得放行");
            } catch (IOException expected) {
                check(expected.getMessage().contains("资源包清单"), "应明确报告资源包清单故障");
            }
            try {
                new ServerListSyncEngine(config, message -> { }).synchronize();
                throw new AssertionError("云端服务器列表清单故障时不得放行");
            } catch (IOException expected) {
                check(expected.getMessage().contains("服务器列表清单"), "应明确报告服务器列表清单故障");
            }
            pass("resource pack and server list manifest failures always block");
        } finally {
            deleteTree(root);
        }
    }

    private void testVersionFilenameChangeIsAutomaticReplacement() throws Exception {
        Path root = Files.createTempDirectory("modsync-version-rename-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path oldJar = mods.resolve("demo-1.0.jar");
            writeFabricJar(oldJar, "demo_mod", "1.0");
            Path clientJar = mods.resolve("client-helper.jar");
            writeFabricJar(clientJar, "client_helper", "client");

            Path newJarSource = root.resolve("demo-2.0-source.jar");
            writeFabricJar(newJarSource, "demo_mod", "2.0");
            byte[] newJar = Files.readAllBytes(newJarSource);
            String currentManifest = ModManifest.MAGIC_V2 + "\n"
                    + Hashing.md5(newJar) + "\tdemo_mod\tdemo-2.0.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(
                    exchange, 200, currentManifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/base/demo-2.0.jar", exchange -> respond(exchange, 200, newJar, null));
            server.start();

            Path state = Files.createDirectories(root.resolve(".modsync"));
            String v1History = ModManifest.MAGIC_V1 + "\n" + Hashing.md5(oldJar) + "\tdemo-1.0.jar\n";
            Files.writeString(state.resolve("server-manifest.txt"), v1History, StandardCharsets.UTF_8);

            AtomicBoolean planObserved = new AtomicBoolean(false);
            SyncObserver observer = new SyncObserver() {
                @Override
                public RemovalDecision decideServerRemoved(List<String> serverRemoved) {
                    throw new AssertionError("同一 Mod ID 的版本改名不应询问服务器删除");
                }

                @Override
                public UnknownModDecision decideUnknownClientMod(String fileName) {
                    check(fileName.equals("client-helper.jar"), "应询问首次出现的客户端 Mod");
                    return UnknownModDecision.KEEP_CLIENT;
                }

                @Override
                public void beforeDownload(
                        List<String> downloads,
                        List<String> replacedOldVersions,
                        List<String> rejectedUnknownMods,
                        List<String> quarantinedServerRemoved,
                        List<String> retainedServerRemoved,
                        List<String> retainedClientMods) {
                    check(downloads.equals(List.of("demo-2.0.jar")), "应下载新版本文件名");
                    check(replacedOldVersions.equals(List.of("demo-1.0.jar")), "旧文件应识别为同 ID 版本替换");
                    check(rejectedUnknownMods.isEmpty(), "版本改名不属于首次未知 Mod");
                    check(quarantinedServerRemoved.isEmpty(), "版本替换不属于服务器删除");
                    check(retainedServerRemoved.isEmpty(), "版本替换不需要保留选择");
                    check(retainedClientMods.equals(List.of("client-helper.jar")), "独立客户端 Mod 应保留");
                    planObserved.set(true);
                }
            };
            URI uri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt");
            SyncResult result = new ModSyncEngine(config(root, uri, true, true), message -> { }, observer).synchronize();
            check(result.status() == SyncResult.Status.UPDATED, "改名升级应执行同步");
            check(planObserved.get(), "应显示自动版本替换内容");
            check(!Files.exists(oldJar), "旧版本不应继续留在 mods");
            check(Files.isRegularFile(mods.resolve("demo-2.0.jar")), "新版本应安装");
            check(FabricModMetadata.readModId(mods.resolve("demo-2.0.jar")).equals("demo_mod"), "新版本 Mod ID 应正确");
            check(Files.isRegularFile(clientJar), "客户端 Mod 不应受版本替换影响");
            pass("version filename change is automatic replacement");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testPortableFabricModeUpdatesAndRequiresRestart() throws Exception {
        Path root = Files.createTempDirectory("modsync-fabric-portable-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        String previousManifest = System.getProperty("modsync.manifest");
        String previousRequired = System.getProperty("modsync.requireManifest");
        String previousDialogs = System.getProperty("modsync.disableDialogs");
        String previousHelperLaunch = System.getProperty("modsync.disableHelperLaunch");
        try {
            byte[] wanted = "portable fabric update".getBytes(StandardCharsets.UTF_8);
            String manifest = ModManifest.MAGIC + "\n" + Hashing.md5(wanted) + "\t-\twanted.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/base/wanted.jar", exchange -> respond(exchange, 200, wanted, null));
            server.start();

            Files.createDirectories(root.resolve("mods"));
            net.fabricmc.loader.api.FabricLoader.setGameDir(root);
            String manifestUri = "http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt";
            System.setProperty("modsync.manifest", manifestUri);
            System.setProperty("modsync.requireManifest", "true");
            System.setProperty("modsync.disableDialogs", "true");
            System.setProperty("modsync.disableHelperLaunch", "true");
            System.setProperty("modsync.forceDesktopHelper", "true");
            System.setProperty("modsync.disableProcessExit", "true");
            System.clearProperty("modsync.forceMobile");
            System.clearProperty("modsync.forceMobileInProcessUpdate");

            try {
                new FabricPreLaunchEntrypoint().onPreLaunch();
                throw new AssertionError("Fabric 便携模式更新后必须停止本次启动");
            } catch (RuntimeException expected) {
                check(expected.getMessage().contains("辅助进程"), "应明确说明退出后由辅助进程更新");
            } finally {
                FabricPreLaunchEntrypoint.releaseGuard();
            }
            check(!Files.exists(root.resolve("mods/wanted.jar")),
                    "桌面便携模式进程仍存活时只允许检查，不应替换 JAR");

            URI uri = URI.create(manifestUri);
            SyncResult helperResult = PortableUpdateHelper.runNow(config(root, uri, true, true), message -> { });
            check(helperResult.status() == SyncResult.Status.UPDATED, "退出后辅助进程应完成更新");
            check(Arrays.equals(Files.readAllBytes(root.resolve("mods/wanted.jar")), wanted),
                    "辅助进程应完成下载与 MD5 校验");

            SyncProbeResult secondProbe = new ModSyncEngine(
                    config(root, uri, true, true), message -> { }).probeWithoutJarChanges();
            check(secondProbe.status() == SyncProbeResult.Status.UP_TO_DATE,
                    "第二次启动应识别为一致并直接放行");
            pass("portable Fabric mode defers locked JAR update and requires restart");
        } finally {
            FabricPreLaunchEntrypoint.releaseGuard();
            restoreProperty("modsync.manifest", previousManifest);
            restoreProperty("modsync.requireManifest", previousRequired);
            restoreProperty("modsync.disableDialogs", previousDialogs);
            restoreProperty("modsync.disableHelperLaunch", previousHelperLaunch);
            System.clearProperty("modsync.forceDesktopHelper");
            System.clearProperty("modsync.disableProcessExit");
            System.clearProperty("modsync.forceMobile");
            System.clearProperty("modsync.forceMobileInProcessUpdate");
            server.stop(0);
            deleteTree(root);
        }
    }


    private void testMobileInProcessUpdateDisablesOldModsThenRestarts() throws Exception {
        Path root = Files.createTempDirectory("modsync-mobile-inprocess-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        Map<String, String> previous = snapshotProperties(
                "modsync.manifest",
                "modsync.requireManifest",
                "modsync.disableDialogs",
                "modsync.disableHelperLaunch",
                "modsync.forceMobile",
                "modsync.forceMobileInProcessUpdate",
                "modsync.forceDesktopHelper",
                "modsync.disableProcessExit",
                "modsync.syncResourcePacks",
                "modsync.syncServerList",
                "modsync.gameDir");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path oldJar = mods.resolve("skin-old.jar");
            writeFabricJar(oldJar, "customskinloader", "old");
            byte[] wanted = "mobile new skin patch bytes".getBytes(StandardCharsets.UTF_8);
            String manifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(wanted) + "\tcustomskinloader\tskin-new.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/base/skin-new.jar", exchange -> respond(exchange, 200, wanted, null));
            server.start();

            net.fabricmc.loader.api.FabricLoader.setGameDir(root);
            String manifestUri = "http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt";
            System.setProperty("modsync.manifest", manifestUri);
            System.setProperty("modsync.requireManifest", "true");
            System.setProperty("modsync.disableDialogs", "true");
            System.setProperty("modsync.forceMobile", "true");
            System.setProperty("modsync.forceMobileInProcessUpdate", "true");
            System.setProperty("modsync.disableProcessExit", "true");
            System.setProperty("modsync.syncResourcePacks", "false");
            System.setProperty("modsync.syncServerList", "false");
            System.setProperty("modsync.gameDir", root.toString());
            System.clearProperty("modsync.forceDesktopHelper");
            UserNotifier.resetDialogsAvailabilityForTests();

            try {
                new FabricPreLaunchEntrypoint().onPreLaunch();
                throw new AssertionError("手机端更新后必须停止本次启动并要求重启");
            } catch (RuntimeException expected) {
                check(expected.getMessage().contains("手机端") || expected.getMessage().contains("重新启动"),
                        "应说明手机端已完成更新并需要重启: " + expected.getMessage());
            } finally {
                FabricPreLaunchEntrypoint.releaseGuard();
            }

            Path newJar = mods.resolve("skin-new.jar");
            check(Files.isRegularFile(newJar), "手机端应在当前进程内先安装新模组");
            check(Arrays.equals(Files.readAllBytes(newJar), wanted), "新模组内容应正确");
            check(!Files.exists(oldJar), "旧模组应已从 mods 禁用/移出");
            boolean backedUp = false;
            Path modsyncDir = root.resolve(".modsync");
            if (Files.isDirectory(modsyncDir)) {
                try (var stream = Files.walk(modsyncDir)) {
                    backedUp = stream.anyMatch(path -> path.getFileName().toString().equals("skin-old.jar"));
                }
            }
            check(backedUp, "旧模组应备份到 .modsync");
            pass("mobile in-process update disables old mods then restarts");
        } finally {
            FabricPreLaunchEntrypoint.releaseGuard();
            restoreProperties(previous);
            UserNotifier.resetDialogsAvailabilityForTests();
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testBakaXLDualDirectorySync() throws Exception {
        Path minecraft = Files.createTempDirectory("modsync-bakaxl-layout-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            Path persistent = Files.createDirectories(minecraft.resolve("instances/demo"));
            Path runtime = Files.createDirectories(minecraft.resolve("versions/demo"));
            String packageInfo = "{\"uuid\":\"test-instance\",\"name\":\"demo\"}";
            Files.writeString(persistent.resolve("package.info"), packageInfo, StandardCharsets.UTF_8);
            Files.writeString(runtime.resolve("package.info"), packageInfo, StandardCharsets.UTF_8);
            Files.createDirectories(persistent.resolve("mods"));
            Files.createDirectories(runtime.resolve("mods"));
            Files.writeString(persistent.resolve("mods/persistent-client.jar"), "persistent client");
            Files.writeString(runtime.resolve("mods/runtime-client.jar"), "runtime client");

            byte[] wanted = "same managed bytes in both BakaXL directories".getBytes(StandardCharsets.UTF_8);
            String manifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(wanted) + "\tmanaged_mod\tmanaged.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/base/managed.jar", exchange -> respond(exchange, 200, wanted, null));
            server.start();

            List<BakaXLLayout.Target> targets = BakaXLLayout.syncTargets(runtime);
            check(targets.size() == 2, "应识别 BakaXL instances/versions 双目录");
            check(targets.get(0).gameDirectory().equals(persistent), "应先更新持久实例");
            check(targets.get(1).gameDirectory().equals(runtime), "随后应更新运行副本");

            AtomicInteger completions = new AtomicInteger();
            SyncObserver observer = new SyncObserver() {
                @Override
                public void afterUpdate(int downloaded, int quarantined, int unchanged) {
                    check(downloaded == 2, "双目录首次同步应各安装一次托管文件");
                    completions.incrementAndGet();
                }
            };
            URI uri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt");
            SyncResult first = ModSyncCoordinator.synchronize(
                    config(runtime, uri, true, true), message -> { }, observer);
            check(first.status() == SyncResult.Status.UPDATED, "BakaXL 双目录首次同步应更新");
            check(completions.get() == 1, "双目录完成提示应只发送一次");
            check(Arrays.equals(Files.readAllBytes(persistent.resolve("mods/managed.jar")), wanted),
                    "持久实例应安装托管文件");
            check(Arrays.equals(Files.readAllBytes(runtime.resolve("mods/managed.jar")), wanted),
                    "运行副本应安装托管文件");

            SyncResult second = ModSyncCoordinator.synchronize(
                    config(runtime, uri, true, true), message -> { }, SyncObserver.NONE);
            check(second.status() == SyncResult.Status.UNCHANGED, "双目录第二次同步应完全一致");
            pass("BakaXL persistent/runtime directories synchronize together");
        } finally {
            server.stop(0);
            deleteTree(minecraft);
        }
    }


    private void testMobileDefaultManifestUsesPhoneList() throws Exception {
        Map<String, String> previous = snapshotProperties(
                "modsync.forceMobile",
                "modsync.manifest",
                "modsync.mobileManifest",
                "modsync.resourcePackManifest",
                "modsync.mobileResourcePackManifest",
                "modsync.gameDir");
        Path root = Files.createTempDirectory("modsync-mobile-manifest-");
        try {
            System.clearProperty("modsync.manifest");
            System.clearProperty("modsync.mobileManifest");
            System.clearProperty("modsync.resourcePackManifest");
            System.clearProperty("modsync.mobileResourcePackManifest");
            System.setProperty("modsync.forceMobile", "true");
            System.setProperty("modsync.gameDir", root.toString());
            ModSyncConfig config = ModSyncConfig.fromEnvironment(null, root);
            check(config.manifestUri().equals(ModSyncConfig.DEFAULT_MOBILE_MANIFEST_URI),
                    "手机端默认应使用手机版 mods.txt: " + config.manifestUri());
            check(config.resourcePackManifestUri().equals(
                            ModSyncConfig.DEFAULT_MOBILE_RESOURCE_PACK_MANIFEST_URI),
                    "手机端默认应使用手机版 resourcepacks.txt: " + config.resourcePackManifestUri());
            System.clearProperty("modsync.forceMobile");
            ModSyncConfig desktop = ModSyncConfig.fromEnvironment(null, root);
            check(desktop.manifestUri().equals(ModSyncConfig.DEFAULT_MANIFEST_URI),
                    "电脑端默认应继续使用电脑版 mods.txt: " + desktop.manifestUri());
            check(desktop.resourcePackManifestUri().equals(
                            ModSyncConfig.DEFAULT_RESOURCE_PACK_MANIFEST_URI),
                    "电脑端默认应继续使用电脑版 resourcepacks.txt: " + desktop.resourcePackManifestUri());
            pass("mobile default manifest uses phone list");
        } finally {
            restoreProperties(previous);
            deleteTree(root);
        }
    }

    private void testMobileAutoQuarantinesExtrasNotInManifest() throws Exception {
        Path root = Files.createTempDirectory("modsync-mobile-quarantine-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        Map<String, String> previous = snapshotProperties(
                "modsync.forceMobile",
                "modsync.disableDialogs",
                "modsync.gameDir",
                "modsync.syncResourcePacks",
                "modsync.syncServerList");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path extra = mods.resolve("kuayue-broken.jar");
            writeFabricJar(extra, "kuayue", "2.0.0");
            Path c2me = mods.resolve("c2me-opts-natives-math.jar");
            writeFabricJar(c2me, "c2me-opts-natives-math", "0.3.7");
            byte[] wanted = "managed mobile mod".getBytes(StandardCharsets.UTF_8);
            String manifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(wanted) + "\tmanaged_mod\tmanaged.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(
                    exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/base/managed.jar", exchange -> respond(exchange, 200, wanted, null));
            server.start();

            System.setProperty("modsync.forceMobile", "true");
            System.setProperty("modsync.disableDialogs", "true");
            System.setProperty("modsync.gameDir", root.toString());
            System.setProperty("modsync.syncResourcePacks", "false");
            System.setProperty("modsync.syncServerList", "false");
            UserNotifier.resetDialogsAvailabilityForTests();

            URI uri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt");
            UserNotifier notifier = new UserNotifier(true, root);
            SyncResult result = ModSyncCoordinator.synchronize(
                    config(root, uri, true, true), message -> { }, notifier);
            check(result.status() == SyncResult.Status.UPDATED, "手机端应完成同步");
            check(Files.isRegularFile(mods.resolve("managed.jar")), "应安装清单内模组");
            check(!Files.exists(extra), "手机端应移出清单外 kuayue");
            check(!Files.exists(c2me), "手机端应移出清单外 c2me-opts-natives-math");
            boolean backedUpKuayue = false;
            boolean backedUpC2me = false;
            Path modsyncDir = root.resolve(".modsync");
            if (Files.isDirectory(modsyncDir)) {
                try (var stream = Files.walk(modsyncDir)) {
                    for (Path path : stream.toList()) {
                        String name = path.getFileName().toString();
                        if (name.equals("kuayue-broken.jar")) {
                            backedUpKuayue = true;
                        }
                        if (name.equals("c2me-opts-natives-math.jar")) {
                            backedUpC2me = true;
                        }
                    }
                }
            }
            check(backedUpKuayue, "kuayue 应备份到 .modsync");
            check(backedUpC2me, "c2me 应备份到 .modsync");
            pass("mobile auto-quarantines extras not in manifest");
        } finally {
            restoreProperties(previous);
            UserNotifier.resetDialogsAvailabilityForTests();
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testKeepingServerRemovedConvertsItToClientMod() throws Exception {
        Path root = Files.createTempDirectory("modsync-keep-removed-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            byte[] managed = "managed current".getBytes(StandardCharsets.UTF_8);
            String currentManifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(managed) + "\t-\tmanaged.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(
                    exchange,
                    200,
                    currentManifest.getBytes(StandardCharsets.UTF_8),
                    null));
            server.start();

            Path mods = Files.createDirectories(root.resolve("mods"));
            Files.write(mods.resolve("managed.jar"), managed);
            Files.writeString(mods.resolve("removed.jar"), "keep as client");
            Path state = Files.createDirectories(root.resolve(".modsync"));
            String previousManifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(managed) + "\t-\tmanaged.jar\n"
                    + Hashing.md5("keep as client".getBytes(StandardCharsets.UTF_8)) + "\t-\tremoved.jar\n";
            Files.writeString(state.resolve("server-manifest.txt"), previousManifest, StandardCharsets.UTF_8);

            int[] decisions = {0};
            SyncObserver keepObserver = new SyncObserver() {
                @Override
                public RemovalDecision decideServerRemoved(List<String> serverRemoved) {
                    decisions[0]++;
                    check(serverRemoved.equals(List.of("removed.jar")), "应提示服务器已移除文件");
                    return RemovalDecision.KEEP;
                }
            };
            URI uri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt");
            SyncResult first = new ModSyncEngine(config(root, uri, true, true), message -> { }, keepObserver).synchronize();
            check(first.status() == SyncResult.Status.UNCHANGED, "选择保留时不应改动 JAR");
            check(Files.isRegularFile(mods.resolve("removed.jar")), "选择保留的服务器移除 Mod 应留在客户端");

            new ModSyncEngine(config(root, uri, true, true), message -> { }, keepObserver).synchronize();
            check(decisions[0] == 1, "保留后应转为客户端 Mod，不应在下次启动重复询问");
            String savedHistory = Files.readString(state.resolve("server-manifest.txt"), StandardCharsets.UTF_8);
            check(!savedHistory.contains("removed.jar"), "新的服务器历史不应继续管理已选择保留的 Mod");
            pass("keeping server-removed mod converts it to client mod");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testClientModIsPreservedWhenOfflineBlocks() throws Exception {
        Path root = Files.createTempDirectory("modsync-client-offline-");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            byte[] managed = "managed bytes".getBytes(StandardCharsets.UTF_8);
            Files.write(mods.resolve("managed.jar"), managed);
            ModManifest initial = ModManifest.scan(mods);
            initial.write(mods.resolve("mods.txt"));
            Path state = Files.createDirectories(root.resolve(".modsync"));
            initial.write(state.resolve("server-manifest.txt"));
            Files.writeString(mods.resolve("new-client.jar"), "player added while offline");

            try {
                new ModSyncEngine(
                        config(root, URI.create("http://127.0.0.1:1/mods.txt"), true, false),
                        message -> { }).synchronize();
                throw new AssertionError("即使只有客户端 Mod 变化，云端清单故障也不得放行");
            } catch (IOException expected) {
                check(expected.getMessage().contains("已阻止启动"), "应因云端清单不可用阻止启动");
            }
            check(Files.isRegularFile(mods.resolve("new-client.jar")), "离线新增的客户端 Mod 必须保留");
            String snapshot = Files.readString(mods.resolve("mods.txt"), StandardCharsets.UTF_8);
            check(snapshot.contains("new-client.jar"), "本地清单应自动纳入新增客户端 Mod");
            ModManifest.parse(snapshot).verifySnapshot(mods);
            pass("client mod is preserved when offline blocks");
        } finally {
            deleteTree(root);
        }
    }

    private void testInvalidServerManagedModBlocksWhenOffline() throws Exception {
        Path root = Files.createTempDirectory("modsync-local-invalid-");
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Files.writeString(mods.resolve("local.jar"), "current bytes");
            ModManifest.scan(mods).write(mods.resolve("mods.txt"));
            Path state = Files.createDirectories(root.resolve(".modsync"));
            String serverHistory = ModManifest.MAGIC + "\n"
                    + Hashing.md5("different bytes".getBytes(StandardCharsets.UTF_8)) + "\t-\tlocal.jar\n";
            Files.writeString(state.resolve("server-manifest.txt"), serverHistory, StandardCharsets.UTF_8);

            try {
                new ModSyncEngine(
                        config(root, URI.create("http://127.0.0.1:1/mods.txt"), true, false),
                        message -> { }).synchronize();
                throw new AssertionError("服务器管理的 Mod 损坏且离线时不应继续启动");
            } catch (IOException expected) {
                check(expected.getMessage().contains("服务器管理的本地 Mod 校验失败"), "应报告服务器管理文件校验失败");
            }
            check(Files.readString(mods.resolve("local.jar")).equals("current bytes"), "校验失败不能改动本地 Mod");
            pass("invalid server-managed mod blocks when offline");
        } finally {
            deleteTree(root);
        }
    }

    private void testApplyFailureRollsBackOriginalFiles() throws Exception {
        Path root = Files.createTempDirectory("modsync-rollback-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            byte[] wanted = "wanted mod".getBytes(StandardCharsets.UTF_8);
            String manifest = ModManifest.MAGIC + "\n" + Hashing.md5(wanted) + "\t-\twanted.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(exchange, 200, manifest.getBytes(StandardCharsets.UTF_8), null));
            server.createContext("/base/wanted.jar", exchange -> respond(exchange, 200, wanted, null));
            server.start();

            Path mods = Files.createDirectories(root.resolve("mods"));
            Files.writeString(mods.resolve("extra.jar"), "must survive rollback");
            Path state = Files.createDirectories(root.resolve(".modsync"));
            String previousServerManifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5("must survive rollback".getBytes(StandardCharsets.UTF_8)) + "\t-\textra.jar\n";
            Files.writeString(state.resolve("server-manifest.txt"), previousServerManifest, StandardCharsets.UTF_8);
            // 用同名目录制造确定性的提交失败，模拟目标无法被替换的情况。
            Files.createDirectory(mods.resolve("wanted.jar"));

            URI manifestUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt");
            try {
                new ModSyncEngine(config(root, manifestUri, true, true), message -> { }).synchronize();
                throw new AssertionError("目标不可替换时同步不应成功");
            } catch (IOException expected) {
                check(expected.getMessage().contains("自动恢复原 Mod"), "失败信息应确认已回滚");
            }

            check(Files.readString(mods.resolve("extra.jar")).equals("must survive rollback"), "提交失败后额外 Mod 应恢复");
            check(Files.isDirectory(mods.resolve("wanted.jar")), "原有冲突目录不应被删除");
            check(!Files.exists(root.resolve(".modsync/RECOVERY_REQUIRED.txt")), "完整回滚不应留下人工恢复标记");
            pass("apply failure rolls back originals");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private static ModSyncConfig config(Path gameDirectory, URI manifest, boolean strict, boolean requireManifest) {
        return new ModSyncConfig(
                manifest,
                manifest,
                manifest,
                gameDirectory,
                gameDirectory,
                false,
                false,
                strict,
                requireManifest,
                Duration.ofSeconds(2),
                Duration.ofSeconds(5),
                1024 * 1024,
                16 * 1024 * 1024,
                3);
    }

    private static ModSyncConfig resourceConfig(Path gameDirectory, URI resourceManifest) {
        return new ModSyncConfig(
                URI.create("http://127.0.0.1:1/mods.txt"),
                resourceManifest,
                URI.create("http://127.0.0.1:1/serverlist.txt"),
                gameDirectory,
                gameDirectory,
                true,
                false,
                true,
                true,
                Duration.ofSeconds(2),
                Duration.ofSeconds(5),
                1024 * 1024,
                16 * 1024 * 1024,
                3);
    }

    private static void respond(HttpExchange exchange, int status, byte[] body, String location) throws IOException {
        try (exchange) {
            if (location != null) {
                exchange.getResponseHeaders().add("Location", location);
            }
            if (exchange.getRequestMethod().equalsIgnoreCase("HEAD")) {
                exchange.getResponseHeaders().set("Content-Length", Long.toString(body.length));
                exchange.sendResponseHeaders(status, -1);
                return;
            }
            exchange.sendResponseHeaders(status, body.length);
            exchange.getResponseBody().write(body);
        }
    }

    private static void writeFabricJar(Path output, String modId, String marker) throws IOException {
        try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(output))) {
            zip.putNextEntry(new ZipEntry("fabric.mod.json"));
            String json = "{\"custom\":{\"id\":\"wrong_nested_id\"},\"id\":\""
                    + modId + "\",\"version\":\"" + marker + "\"}";
            zip.write(json.getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
            zip.putNextEntry(new ZipEntry("marker.txt"));
            zip.write(marker.getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
    }

    private static void deleteTree(Path root) throws IOException {
        if (root == null || !Files.exists(root)) {
            return;
        }
        try (var stream = Files.walk(root)) {
            for (Path path : stream.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    private static void expectFailure(ThrowingRunnable runnable) {
        try {
            runnable.run();
            throw new AssertionError("预期操作失败，但它成功了");
        } catch (IllegalArgumentException expected) {
        } catch (Exception exception) {
            throw new AssertionError("异常类型不符合预期", exception);
        }
    }


    private void testZalithMobileEnvironmentDetection() throws Exception {
        Map<String, String> previous = snapshotProperties(
                "os.name",
                "os.version",
                "java.awt.headless",
                "awt.toolkit",
                "java.awt.graphicsenv",
                "minecraft.launcher.brand",
                "net.minecraft.clientmodname",
                "pojav.path.minecraft",
                "user.home",
                "java.io.tmpdir",
                "loader.disable_forked_guis",
                "modsync.forceMobile",
                "modsync.disableDialogs",
                "modsync.forceHeadless");
        try {
            System.setProperty("os.name", "Linux");
            System.setProperty("os.version", "Android-12");
            System.setProperty("java.awt.headless", "false");
            System.setProperty("awt.toolkit", "com.github.caciocavallosilano.cacio.ctc.CTCToolkit");
            System.setProperty(
                    "java.awt.graphicsenv",
                    "com.github.caciocavallosilano.cacio.ctc.CTCGraphicsEnvironment");
            System.setProperty("minecraft.launcher.brand", "Zalith Launcher");
            System.setProperty("net.minecraft.clientmodname", "Zalith Launcher");
            System.setProperty(
                    "pojav.path.minecraft",
                    "/storage/emulated/0/Android/data/com.movtery.zalithlauncher.v2/files/.minecraft");
            System.setProperty(
                    "user.home",
                    "/storage/emulated/0/Android/data/com.movtery.zalithlauncher.v2/files/.minecraft");
            System.setProperty(
                    "java.io.tmpdir",
                    "/data/user/0/com.movtery.zalithlauncher.v2/cache");
            System.setProperty("loader.disable_forked_guis", "true");
            System.clearProperty("modsync.forceMobile");
            System.clearProperty("modsync.disableDialogs");
            System.clearProperty("modsync.forceHeadless");
            UserNotifier.resetDialogsAvailabilityForTests();

            RuntimeEnvironment environment = RuntimeEnvironment.detect();
            check(environment.mobile(), "Zalith 特征应识别为手机端");
            check(environment.cacioAwt(), "应识别 Cacio AWT");
            check(!environment.dialogsUsable(), "手机端即使 headless=false 也不应使用独立 Swing 窗口");
            check(environment.launcherName().toLowerCase().contains("zalith"),
                    "启动器名称应包含 Zalith");
            check(environment.summaryLine().contains("progress=log"),
                    "摘要应标明使用日志进度");
            check(!UserNotifier.dialogsAvailable(), "UserNotifier 应关闭弹窗");
            pass("zalith mobile environment detection");
        } finally {
            restoreProperties(previous);
            UserNotifier.resetDialogsAvailabilityForTests();
        }
    }

    private void testSupportedMobileLauncherAllowList() {
        Map<String, String> previous = snapshotProperties(
                "minecraft.launcher.brand",
                "net.minecraft.clientmodname",
                "pojav.path.minecraft",
                "modsync.forceMobile");
        try {
            System.clearProperty("modsync.forceMobile");
            System.clearProperty("pojav.path.minecraft");
            for (String launcher : List.of("PojavLauncher", "MCinaBox", "FCL")) {
                System.setProperty("minecraft.launcher.brand", launcher);
                System.setProperty("net.minecraft.clientmodname", launcher);
                check(RuntimeEnvironment.detect().mobile(), launcher + " 应识别为手机端");
            }
            pass("supported mobile launcher allow list");
        } finally {
            restoreProperties(previous);
        }
    }

    private void testUnsupportedAndroidLauncherUsesDesktopLogic() {
        Map<String, String> previous = snapshotProperties(
                "os.name",
                "os.version",
                "awt.toolkit",
                "java.awt.graphicsenv",
                "minecraft.launcher.brand",
                "net.minecraft.clientmodname",
                "pojav.path.minecraft",
                "user.home",
                "java.io.tmpdir",
                "modsync.forceMobile");
        try {
            System.setProperty("os.name", "Linux");
            System.setProperty("os.version", "Android-14");
            System.setProperty("awt.toolkit", "example.cacio.Toolkit");
            System.setProperty("java.awt.graphicsenv", "example.cacio.GraphicsEnvironment");
            System.setProperty("minecraft.launcher.brand", "Other Android Launcher");
            System.setProperty("net.minecraft.clientmodname", "Other Android Launcher");
            System.clearProperty("pojav.path.minecraft");
            System.setProperty("user.home", "/storage/emulated/0/Android/data/other.launcher/files");
            System.setProperty("java.io.tmpdir", "/data/user/0/other.launcher/cache");
            System.clearProperty("modsync.forceMobile");
            check(!RuntimeEnvironment.detect().mobile(),
                    "未列入白名单的 Android/Cacio 启动器必须按电脑端处理");
            pass("unsupported Android launcher uses desktop logic");
        } finally {
            restoreProperties(previous);
        }
    }

    private void testHeadlessProgressIsLoggedAndWritten() throws Exception {
        Path root = Files.createTempDirectory("modsync-headless-progress-");
        Map<String, String> previous = snapshotProperties(
                "modsync.disableDialogs",
                "modsync.forceMobile",
                "modsync.gameDir",
                "modsync.language");
        try {
            System.setProperty("modsync.disableDialogs", "true");
            System.setProperty("modsync.forceMobile", "true");
            System.setProperty("modsync.gameDir", root.toString());
            System.setProperty("modsync.language", "en_us");
            UserNotifier.resetDialogsAvailabilityForTests();

            UserNotifier notifier = new UserNotifier(true, root);
            notifier.beforeDownload(
                    List.of("demo.jar"),
                    List.of(),
                    List.of(),
                    List.of(),
                    List.of(),
                    List.of());
            notifier.downloadProgress(new SyncObserver.DownloadProgress(
                    "demo.jar",
                    1,
                    1,
                    512 * 1024,
                    1024 * 1024,
                    512 * 1024,
                    1024 * 1024,
                    500));
            notifier.afterUpdate(1, 0, 0);

            Path status = root.resolve(".modsync/ui-status.txt");
            Path progressLog = root.resolve(".modsync/progress.log");
            check(Files.isRegularFile(status), "应写入 ui-status.txt");
            check(Files.isRegularFile(progressLog), "应写入 progress.log");
            String statusText = Files.readString(status);
            String progressText = Files.readString(progressLog);
            check(statusText.contains("progressPermille=") || statusText.contains("Update complete"),
                    "英文状态文件应包含进度或完成信息");
            check(progressText.contains("PROGRESS") || progressText.contains("demo.jar"),
                    "进度日志应包含下载文件信息");
            check(progressText.contains("Environment:")
                            || progressText.contains("ENV ")
                            || progressText.contains("mobile="),
                    "英文进度日志应包含环境识别信息");
            check(statusText.contains("Update complete") && !statusText.contains("更新完成"),
                    "英文系统/配置下 ui-status.txt 应使用英文");
            pass("headless progress is logged and written");
        } finally {
            restoreProperties(previous);
            UserNotifier.resetDialogsAvailabilityForTests();
            deleteTree(root);
        }
    }

    private static Map<String, String> snapshotProperties(String... keys) {
        Map<String, String> snapshot = new java.util.LinkedHashMap<>();
        for (String key : keys) {
            snapshot.put(key, System.getProperty(key));
        }
        return snapshot;
    }

    private static void restoreProperties(Map<String, String> snapshot) {
        for (Map.Entry<String, String> entry : snapshot.entrySet()) {
            restoreProperty(entry.getKey(), entry.getValue());
        }
    }

    private static void restoreProperty(String name, String value) {
        if (value == null) {
            System.clearProperty(name);
        } else {
            System.setProperty(name, value);
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private void pass(String name) {
        passed++;
        System.out.println("PASS: " + name);
    }

    private void testServerListOwnershipLedgerAndOrderProtection() throws Exception {
        Path root = Files.createTempDirectory("modsync-server-list-ownership-");
        try {
            ServerListNbt.Document initialCloud = serverListDocument(root.resolve("initial-cloud.dat"), List.of(
                    new ServerListNbt.ServerInfo("云端同地址", "shared.example.test"),
                    new ServerListNbt.ServerInfo("云端新增", "new.example.test")));
            List<ServerListNbt.ServerInfo> playerEntries = List.of(
                    new ServerListNbt.ServerInfo("玩家第一项", "first.example.test"),
                    new ServerListNbt.ServerInfo("玩家同地址一", "shared.example.test"),
                    new ServerListNbt.ServerInfo("玩家同地址二", "shared.example.test"),
                    new ServerListNbt.ServerInfo("玩家最后一项", "last.example.test"));
            ServerListNbt.Document legacyLocal = serverListDocument(root.resolve("legacy-local.dat"), playerEntries);

            ServerListNbt.MergeResult migrated = ServerListNbt.merge(initialCloud, legacyLocal, null);
            List<ServerListNbt.ServerInfo> migratedEntries = serverListInfo(
                    root.resolve("migrated.dat"), migrated.merged());
            check(migratedEntries.equals(List.of(
                            playerEntries.get(0),
                            playerEntries.get(1),
                            playerEntries.get(2),
                            playerEntries.get(3),
                            new ServerListNbt.ServerInfo("云端新增", "new.example.test"))),
                    "旧版升级时不得认领或去重玩家已有的同地址服务器，真正的新云端条目应追加到末尾");
            check(serverListInfo(root.resolve("migrated-ledger.dat"), migrated.managedState()).equals(List.of(
                            new ServerListNbt.ServerInfo("云端新增", "new.example.test"))),
                    "首次建立所有权台账时只能记录本次实际添加的云端条目");
            ServerListNbt.validateManagedState(migrated.managedState());
            check(!initialCloud.rootName().equals(migrated.managedState().rootName()),
                    "合法所有权台账必须使用区别于普通 servers.dat 的专用 root marker");
            expectManagedStateValidationFailure(initialCloud);
            check(ServerListNbt.isSynchronized(initialCloud, migrated.merged(), migrated.managedState()),
                    "合并后的列表和所有权台账应被判定为已同步");

            ServerListNbt.Document emptyCloud = serverListDocument(root.resolve("empty-cloud.dat"), List.of());
            ServerListNbt.MergeResult removedNew = ServerListNbt.merge(
                    emptyCloud, migrated.merged(), migrated.managedState());
            check(serverListInfo(root.resolve("removed-new.dat"), removedNew.merged()).equals(playerEntries),
                    "云端删除时只能删除台账内的受管条目，两个玩家同地址条目都必须保留");
            check(serverListInfo(root.resolve("removed-new-ledger.dat"), removedNew.managedState()).isEmpty(),
                    "已从云端删除的受管条目也应从所有权台账移除");

            ServerListNbt.MergeResult missingLedgerRemoval = ServerListNbt.merge(
                    emptyCloud, migrated.merged(), null);
            check(serverListInfo(root.resolve("missing-ledger-removal.dat"), missingLedgerRemoval.merged())
                            .equals(migratedEntries),
                    "所有权台账缺失时，远端删除旧地址也不得删除任何现有本地条目");
            ServerListNbt.MergeResult corruptLedgerRemoval = ServerListNbt.merge(
                    emptyCloud, migrated.merged(), null);
            check(serverListInfo(root.resolve("corrupt-ledger-removal.dat"), corruptLedgerRemoval.merged())
                            .equals(migratedEntries),
                    "所有权台账 marker 损坏并进入保守模式时，远端删除旧地址不得删除本地条目");

            ServerListNbt.Document oldManaged = serverListManagedDocument(
                    root.resolve("old-managed-source.dat"), List.of(
                            new ServerListNbt.ServerInfo("旧 A", "a.example.test"),
                            new ServerListNbt.ServerInfo("旧 B", "b.example.test")));
            ServerListNbt.Document orderedLocal = serverListDocument(root.resolve("ordered-local.dat"), List.of(
                    new ServerListNbt.ServerInfo("玩家头部", "player-head.example.test"),
                    new ServerListNbt.ServerInfo("旧 B", "b.example.test"),
                    new ServerListNbt.ServerInfo("玩家中部", "player-middle.example.test"),
                    new ServerListNbt.ServerInfo("旧 A", "a.example.test")));
            ServerListNbt.Document updatedCloud = serverListDocument(root.resolve("updated-cloud.dat"), List.of(
                    new ServerListNbt.ServerInfo("新 A", "a.example.test"),
                    new ServerListNbt.ServerInfo("新 B", "b.example.test"),
                    new ServerListNbt.ServerInfo("新 C", "c.example.test")));
            List<ServerListNbt.ServerInfo> expectedUpdatedOrder = List.of(
                    new ServerListNbt.ServerInfo("玩家头部", "player-head.example.test"),
                    new ServerListNbt.ServerInfo("新 B", "b.example.test"),
                    new ServerListNbt.ServerInfo("玩家中部", "player-middle.example.test"),
                    new ServerListNbt.ServerInfo("新 A", "a.example.test"),
                    new ServerListNbt.ServerInfo("新 C", "c.example.test"));
            ServerListNbt.MergeResult updated = ServerListNbt.merge(updatedCloud, orderedLocal, oldManaged);
            check(serverListInfo(root.resolve("updated.dat"), updated.merged()).equals(expectedUpdatedOrder),
                    "受管条目必须在本地原位置更新，玩家条目顺序不变，新云端条目追加到末尾");

            ServerListNbt.Document reorderedCloud = serverListDocument(root.resolve("reordered-cloud.dat"), List.of(
                    new ServerListNbt.ServerInfo("新 C", "c.example.test"),
                    new ServerListNbt.ServerInfo("新 A", "a.example.test"),
                    new ServerListNbt.ServerInfo("新 B", "b.example.test")));
            ServerListNbt.MergeResult reordered = ServerListNbt.merge(
                    reorderedCloud, updated.merged(), updated.managedState());
            check(serverListInfo(root.resolve("reordered.dat"), reordered.merged()).equals(expectedUpdatedOrder),
                    "只改变云端清单顺序不得改变玩家当前服务器列表顺序");

            ServerListNbt.Document removedBCloud = serverListDocument(root.resolve("removed-b-cloud.dat"), List.of(
                    new ServerListNbt.ServerInfo("新 A", "a.example.test"),
                    new ServerListNbt.ServerInfo("新 C", "c.example.test")));
            ServerListNbt.MergeResult removedB = ServerListNbt.merge(
                    removedBCloud, reordered.merged(), reordered.managedState());
            check(serverListInfo(root.resolve("removed-b.dat"), removedB.merged()).equals(List.of(
                            new ServerListNbt.ServerInfo("玩家头部", "player-head.example.test"),
                            new ServerListNbt.ServerInfo("玩家中部", "player-middle.example.test"),
                            new ServerListNbt.ServerInfo("新 A", "a.example.test"),
                            new ServerListNbt.ServerInfo("新 C", "c.example.test"))),
                    "删除中间的受管条目时不得重排剩余玩家或受管条目");

            ServerListNbt.Document ambiguousLedger = serverListManagedDocument(
                    root.resolve("ambiguous-ledger-source.dat"), List.of(
                            new ServerListNbt.ServerInfo("受管 X", "x.example.test")));
            ServerListNbt.Document ambiguousLocal = serverListDocument(root.resolve("ambiguous-local.dat"), List.of(
                    new ServerListNbt.ServerInfo("受管 X", "x.example.test"),
                    new ServerListNbt.ServerInfo("受管 X", "x.example.test"),
                    new ServerListNbt.ServerInfo("玩家 Y", "y.example.test")));
            ServerListNbt.MergeResult ambiguous = ServerListNbt.merge(
                    emptyCloud, ambiguousLocal, ambiguousLedger);
            check(serverListInfo(root.resolve("ambiguous.dat"), ambiguous.merged()).equals(List.of(
                            new ServerListNbt.ServerInfo("受管 X", "x.example.test"),
                            new ServerListNbt.ServerInfo("受管 X", "x.example.test"),
                            new ServerListNbt.ServerInfo("玩家 Y", "y.example.test"))),
                    "所有权无法唯一确认时必须保守保留全部本地条目");
            check(serverListInfo(root.resolve("ambiguous-next-ledger.dat"), ambiguous.managedState()).isEmpty(),
                    "歧义条目不得继续保留受管身份");
            check(!ambiguous.notices().isEmpty(), "所有权歧义应产生可记录的诊断信息");
            pass("server list ownership ledger protects player order and entries");
        } finally {
            deleteTree(root);
        }
    }

    private static ServerListNbt.Document serverListDocument(
            Path path,
            List<ServerListNbt.ServerInfo> servers) throws IOException {
        ServerListNbt.writeSimple(path, servers);
        return ServerListNbt.read(path);
    }

    private static ServerListNbt.Document serverListManagedDocument(Path source) throws IOException {
        ServerListNbt.Document cloud = ServerListNbt.read(source);
        return ServerListNbt.merge(cloud, null, null).managedState();
    }

    private static ServerListNbt.Document serverListManagedDocument(
            Path source,
            List<ServerListNbt.ServerInfo> servers) throws IOException {
        return ServerListNbt.merge(serverListDocument(source, servers), null, null).managedState();
    }

    private static List<ServerListNbt.ServerInfo> serverListInfo(
            Path path,
            ServerListNbt.Document document) throws IOException {
        ServerListNbt.write(path, document);
        return ServerListNbt.readServerInfo(path);
    }

    private static void expectManagedStateValidationFailure(ServerListNbt.Document document) throws Exception {
        try {
            ServerListNbt.validateManagedState(document);
            throw new AssertionError("普通 servers.dat 不得通过所有权台账 root marker 校验");
        } catch (IOException expected) {
        }
    }

    private static void writeNeoForgeJar(Path output, String modId, String marker) throws IOException {
        try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(output))) {
            zip.putNextEntry(new ZipEntry("META-INF/neoforge.mods.toml"));
            String toml = "modLoader=\"javafml\"\n"
                    + "loaderVersion=\"[1,)\"\n"
                    + "license=\"MIT\"\n"
                    + "[[mods]]\n"
                    + "modId=\"" + modId + "\"\n"
                    + "version=\"" + marker + "\"\n"
                    + "displayName=\"Neo Demo\"\n"
                    + "description='''NeoForge\n"
                    + "description with spaces'''\n";
            zip.write(toml.getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
    }

    public static final class SleepingChild {
        public static void main(String[] arguments) throws InterruptedException {
            Thread.sleep(Duration.ofMinutes(1));
        }
    }

    @FunctionalInterface
    private interface ThrowingRunnable {
        void run() throws Exception;
    }
}
