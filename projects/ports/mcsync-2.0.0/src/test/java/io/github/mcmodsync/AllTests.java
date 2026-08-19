package io.github.mcmodsync;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.math.BigDecimal;
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
import java.util.LinkedHashMap;
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
        testMcsyncBrandingKeepsLegacyTechnicalIdentity();
        testV5ReleaseManifestParsingAndValidation();
        testV5RecommendedSelectionIsDeferredToMinecraftWindow();
        testV5ResourceAndShaderPacksCanBeOptional();
        testV5ModCatalogImportRespectsCurrentClientDeletions();
        testV5PlatformDownloadSourcesAndMirrorTrustBoundary();
        testOnlyModsMayUsePlatformDownloadSources();
        testDefaultDownloadConcurrencyIs128();
        testModArtifactClassificationAndFingerprintNormalization();
        testClientOnlyMetadataDefaultsToRecommended();
        testV5CustomBuildUsesPublisherHostedDistribution();
        testChinaApiMirrorPresetsRemainExplicitThirdPartyCandidates();
        testPublisherResolvesCurseForgeWithoutLeakingCredentials();
        testV5MirrorHashFailureFallsBackToOfficialCandidate();
        testReleaseSequenceAntiDowngradeGate();
        testStructuredConfigMutationEngine();
        testV5AtomicReleaseTransactionAndOwnership();
        testV5InterruptedCommitRecoversFromDurableJournal();
        testV5SelfUpdateReplacesLegacyJarInSameTransaction();
        testV5CoordinatorDownloadsBeforeStartupAndBecomesIdempotent();
        testV5PublisherProjectBuildsDeterministicRelease();
        testPublisherCloudBundleBuildsStableAndLegacyEntrypoints();
        testPublisherCloudBundleExportsServerList();
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

    private void testMcsyncBrandingKeepsLegacyTechnicalIdentity() {
        check(BuildInfo.PRODUCT_NAME.equals("MCSync"), "2.0 产品名应为 MCSync");
        check(BuildInfo.VERSION.equals("2.0.0"), "首个 MCSync 版本应为 2.0.0");
        check(BuildInfo.TECHNICAL_MOD_ID.equals("mcmodsync"), "必须保留旧 modId 才能从 1.9.x 原地升级");
        pass("MCSync branding preserves the legacy technical upgrade identity");
    }

    private void testV5RecommendedSelectionIsDeferredToMinecraftWindow() throws Exception {
        Path root = Files.createTempDirectory("mcsync-v5-recommended-screen-");
        String old = System.getProperty("modsync.forceInGameSelection");
        System.setProperty("modsync.forceInGameSelection", "true");
        try {
            ReleaseManifestV5.DownloadSource hosted = new ReleaseManifestV5.DownloadSource(
                    "publisher-hosted", "", "", null, "redistributable", List.of());
            ReleaseManifestV5.FileEntry required = new ReleaseManifestV5.FileEntry(
                    "mods/core.jar", "1".repeat(64), 1, "mod", true, true, Set.of("client"), hosted,
                    "core", "Core", "1", "核心", "Core", Set.of());
            ReleaseManifestV5.FileEntry optionalA = new ReleaseManifestV5.FileEntry(
                    "mods/optional-a.jar", "2".repeat(64), 1, "mod", false, true, Set.of("client"), hosted,
                    "optional_a", "Optional A", "1", "推荐甲", "Optional A", Set.of());
            ReleaseManifestV5 first = new ReleaseManifestV5(
                    "test", 1, "2.0.0", List.of(new ReleaseManifestV5.ManagedScope("mods", "managed")),
                    List.of(required, optionalA), List.of());

            V5RecommendedSelectionStore.Resolution initial = V5RecommendedSelectionStore.resolve(
                    first, root, RuntimeEnvironment.detect());
            check(initial.selectionPending(), "首次 v5 推荐清单必须等待 Minecraft 窗口确认");
            check(initial.effectiveManifest().files().equals(List.of(required)),
                    "确认前只能同步必须 Mod，不能提前安装推荐 Mod");
            V5RecommendedSelectionStore.PendingSelection pending = V5RecommendedSelectionStore.readPending(root);
            check(pending != null && pending.mods().size() == 1 && pending.mods().getFirst().selected(),
                    "首次推荐项应默认全选");
            V5RecommendedSelectionStore.confirm(root, pending, Set.of());
            V5RecommendedSelectionStore.Resolution declined = V5RecommendedSelectionStore.resolve(
                    first, root, RuntimeEnvironment.detect());
            check(!declined.selectionPending() && declined.effectiveManifest().files().equals(List.of(required)),
                    "同一推荐清单不应重复询问，并应保留取消选择");

            ReleaseManifestV5.FileEntry optionalAUpdated = new ReleaseManifestV5.FileEntry(
                    "mods/optional-a-2.jar", "4".repeat(64), 2, "mod", false, true, Set.of("client"), hosted,
                    "optional_a", "Optional A", "2", "推荐甲（新版）", "Optional A updated", Set.of());
            ReleaseManifestV5 versionOnly = new ReleaseManifestV5(
                    "test", 2, "2.0.0", first.managedScopes(),
                    List.of(required, optionalAUpdated), List.of());
            V5RecommendedSelectionStore.Resolution versionUpdated = V5RecommendedSelectionStore.resolve(
                    versionOnly, root, RuntimeEnvironment.detect());
            check(!versionUpdated.selectionPending()
                            && versionUpdated.effectiveManifest().files().equals(List.of(required)),
                    "推荐 Mod 仅版本、哈希、文件名或描述变化时不得重复询问");

            ReleaseManifestV5.FileEntry optionalB = new ReleaseManifestV5.FileEntry(
                    "mods/optional-b.jar", "3".repeat(64), 1, "mod", false, true, Set.of("client"), hosted,
                    "optional_b", "Optional B", "1", "推荐乙", "Optional B", Set.of());
            ReleaseManifestV5 second = new ReleaseManifestV5(
                    "test", 3, "2.0.0", first.managedScopes(),
                    List.of(required, optionalAUpdated, optionalB), List.of());
            V5RecommendedSelectionStore.Resolution updated = V5RecommendedSelectionStore.resolve(
                    second, root, RuntimeEnvironment.detect());
            check(updated.selectionPending(), "新增推荐 Mod 必须重新显示游戏内选择页");
            V5RecommendedSelectionStore.PendingSelection updatedPending =
                    V5RecommendedSelectionStore.readPending(root);
            Map<String, Boolean> defaults = new LinkedHashMap<>();
            for (V5RecommendedSelectionStore.PendingMod mod : updatedPending.mods()) {
                defaults.put(mod.key(), mod.selected());
            }
            check(Boolean.FALSE.equals(defaults.get("optional_a"))
                            && Boolean.TRUE.equals(defaults.get("optional_b")),
                    "旧取消项必须保持取消，只有新增推荐项默认勾选");
            pass("v5 recommendations wait for the Minecraft window and preserve prior choices");
        } finally {
            if (old == null) System.clearProperty("modsync.forceInGameSelection");
            else System.setProperty("modsync.forceInGameSelection", old);
        }
    }

    private void testClientOnlyMetadataDefaultsToRecommended() throws Exception {
        Path root = Files.createTempDirectory("mcsync-client-only-metadata-");
        try {
            Path clientOnly = root.resolve("client-only.jar");
            try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(clientOnly))) {
                zip.putNextEntry(new ZipEntry("fabric.mod.json"));
                zip.write(("{\"id\":\"client_only\",\"version\":\"1\","
                        + "\"environment\":\"client\"}").getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
            Path requiredSync = root.resolve("mcsync.jar");
            try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(requiredSync))) {
                zip.putNextEntry(new ZipEntry("fabric.mod.json"));
                zip.write(("{\"id\":\"mcmodsync\",\"version\":\"2.0.0\","
                        + "\"environment\":\"client\"}").getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
            check(ModMetadata.recommendedByMetadata(clientOnly),
                    "明确 environment=client 的普通 Mod 应保守默认归入推荐");
            check(!ModMetadata.recommendedByMetadata(requiredSync),
                    "MCSync 本体即使标为客户端侧也必须始终属于必需 Mod");
            pass("explicit client-only metadata defaults to recommended without weakening MCSync");
        } finally {
            deleteTree(root);
        }
    }

    private void testV5ResourceAndShaderPacksCanBeOptional() throws Exception {
        Path root = Files.createTempDirectory("mcsync-v5-optional-packs-");
        String old = System.getProperty("modsync.forceInGameSelection");
        System.setProperty("modsync.forceInGameSelection", "true");
        try {
            ReleaseManifestV5.DownloadSource hosted = new ReleaseManifestV5.DownloadSource(
                    "publisher-hosted", "", "", null, "redistributable", List.of());
            ReleaseManifestV5.FileEntry required = new ReleaseManifestV5.FileEntry(
                    "kubejs/client_scripts/core.js", "1".repeat(64), 1, "kubejs", true, true,
                    Set.of("client"), hosted);
            ReleaseManifestV5.FileEntry resource = new ReleaseManifestV5.FileEntry(
                    "resourcepacks/pretty.zip", "2".repeat(64), 2, "resource-pack", false, false,
                    Set.of("client"), hosted, "", "Pretty Pack", "1", "美化资源包", "Visual resource pack", Set.of());
            ReleaseManifestV5.FileEntry shader = new ReleaseManifestV5.FileEntry(
                    "shaderpacks/light.zip", "3".repeat(64), 3, "shader-pack", false, false,
                    Set.of("client"), hosted, "", "Light Shader", "1", "轻量光影", "Lightweight shader", Set.of());
            ReleaseManifestV5 manifest = new ReleaseManifestV5(
                    "packs", 1, "2.0.0", List.of(), List.of(required, resource, shader), List.of());

            V5RecommendedSelectionStore.Resolution initial = V5RecommendedSelectionStore.resolve(
                    manifest, root, RuntimeEnvironment.detect());
            check(initial.selectionPending() && initial.effectiveManifest().files().equals(List.of(required)),
                    "可选资源包和光影包必须等待游戏内确认，确认前不得下载");
            V5RecommendedSelectionStore.PendingSelection pending = V5RecommendedSelectionStore.readPending(root);
            check(pending != null && pending.mods().size() == 2
                            && pending.mods().stream().anyMatch(item -> item.kind().equals("resource-pack"))
                            && pending.mods().stream().anyMatch(item -> item.kind().equals("shader-pack"))
                            && pending.mods().stream().allMatch(V5RecommendedSelectionStore.PendingMod::selected),
                    "游戏内选择页必须区分资源包和光影包，且首次出现时默认全部勾选");
            V5RecommendedSelectionStore.confirm(root, pending, Set.of(resource.selectionKey()));
            V5RecommendedSelectionStore.Resolution selected = V5RecommendedSelectionStore.resolve(
                    manifest, root, RuntimeEnvironment.detect());
            check(!selected.selectionPending()
                            && selected.effectiveManifest().files().equals(List.of(required, resource)),
                    "玩家取消的可选光影不得同步，选中的资源包应保留");
            pass("v5 resource packs and shader packs can be optional in the Minecraft selection screen");
        } finally {
            if (old == null) System.clearProperty("modsync.forceInGameSelection");
            else System.setProperty("modsync.forceInGameSelection", old);
        }
    }

    private void testV5ModCatalogImportRespectsCurrentClientDeletions() {
        ReleaseManifestV5.DownloadSource hosted = new ReleaseManifestV5.DownloadSource(
                "publisher-hosted", "", "", null, "redistributable", List.of());
        ReleaseManifestV5.FileEntry unchanged = new ReleaseManifestV5.FileEntry(
                "mods/a-old.jar", "1".repeat(64), 1, "mod", false, true, Set.of("client"), hosted,
                "mod_a", "A", "1", "甲", "A", Set.of());
        ReleaseManifestV5.FileEntry upgraded = new ReleaseManifestV5.FileEntry(
                "mods/b-old.jar", "2".repeat(64), 1, "mod", true, true, Set.of("client"), hosted,
                "mod_b", "B", "1", "乙", "B", Set.of());
        ReleaseManifestV5.FileEntry deleted = new ReleaseManifestV5.FileEntry(
                "mods/deleted.jar", "3".repeat(64), 1, "mod", true, true, Set.of("client"), hosted,
                "mod_deleted", "Deleted", "1", "已删除", "Deleted", Set.of());
        ReleaseManifestV5.FileEntry ambiguousOne = new ReleaseManifestV5.FileEntry(
                "mods/ambiguous-1.jar", "4".repeat(64), 1, "mod", true, true, Set.of("client"), hosted,
                "duplicate", "Duplicate 1", "1", "重复一", "Duplicate 1", Set.of());
        ReleaseManifestV5.FileEntry ambiguousTwo = new ReleaseManifestV5.FileEntry(
                "mods/ambiguous-2.jar", "5".repeat(64), 1, "mod", true, true, Set.of("client"), hosted,
                "duplicate", "Duplicate 2", "1", "重复二", "Duplicate 2", Set.of());

        V5ModCatalogMatcher.MatchResult result = V5ModCatalogMatcher.match(
                List.of(
                        new V5ModCatalogMatcher.CurrentMod("mods/a-renamed.jar", "wrong_metadata", "1".repeat(64)),
                        new V5ModCatalogMatcher.CurrentMod("mods/b-new.jar", "mod_b", "9".repeat(64)),
                        new V5ModCatalogMatcher.CurrentMod("mods/new.jar", "new_mod", "a".repeat(64)),
                        new V5ModCatalogMatcher.CurrentMod("mods/unknown.jar", "duplicate", "b".repeat(64))),
                List.of(unchanged, upgraded, deleted, ambiguousOne, ambiguousTwo));

        check(result.byCurrentPath().size() == 2
                        && result.byCurrentPath().get("mods/a-renamed.jar").equals(unchanged)
                        && result.byCurrentPath().get("mods/b-new.jar").equals(upgraded),
                "v5 Mods 导入应先按 SHA-256 识别改名文件，并只用唯一 modId 继承升级后的元数据");
        check(result.newCurrentPaths().containsAll(Set.of("mods/new.jar", "mods/unknown.jar")),
                "新增 Mod 与歧义 modId 必须保留当前扫描默认值，不能猜测继承");
        check(result.deletedImportedPaths().containsAll(Set.of(
                        "mods/deleted.jar", "mods/ambiguous-1.jar", "mods/ambiguous-2.jar")),
                "旧 v5 中已从客户端删除或无法唯一对应的 Mod 不得被恢复");
        pass("v5 Mods-only import preserves translations without reviving deleted mods");
    }

    private void testPublisherResolvesCurseForgeWithoutLeakingCredentials() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            server.createContext("/v1/mods/238222/files/987654/download-url", exchange ->
                    respond(exchange, 200,
                            "{\"data\":\"https://cdn.example.invalid/files/fixed.jar\"}"
                                    .getBytes(StandardCharsets.UTF_8),
                            "application/json"));
            server.start();
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1/";
            Map<String, Object> resolved = new PublisherPlatformResolver(HttpClient.newHttpClient()).resolve(Map.of(
                    "type", "curseforge",
                    "projectId", "238222",
                    "fileId", new BigDecimal("987654"),
                    "distributionPolicy", "upstream-only",
                    "endpoints", List.of(Map.of(
                            "url", base,
                            "role", "mirror",
                            "purpose", "api",
                            "region", "cn",
                            "priority", new BigDecimal("10"),
                            "thirdParty", true))));
            String serialized = StrictJson.stringify(resolved);
            check(serialized.contains("https://cdn.example.invalid/files/fixed.jar")
                            && !serialized.toLowerCase(Locale.ROOT).contains("api-key")
                            && !serialized.toLowerCase(Locale.ROOT).contains("x-api-key"),
                    "发布器应把固定 fileId 解析成无凭据下载候选，绝不把 API key 写进清单");
            pass("publisher resolves CurseForge file IDs without leaking credentials");
        } finally {
            server.stop(0);
        }
    }

    private void testV5MirrorHashFailureFallsBackToOfficialCandidate() throws Exception {
        Path root = Files.createTempDirectory("mcsync-v5-source-fallback-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            byte[] expected = "official-fixed-build".getBytes(StandardCharsets.UTF_8);
            AtomicInteger mirrorRequests = new AtomicInteger();
            AtomicInteger officialRequests = new AtomicInteger();
            server.createContext("/mirror.jar", exchange -> {
                mirrorRequests.incrementAndGet();
                respond(exchange, 200, "corrupted-mirror".getBytes(StandardCharsets.UTF_8), null);
            });
            server.createContext("/official.jar", exchange -> {
                officialRequests.incrementAndGet();
                respond(exchange, 200, expected, null);
            });
            server.start();
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            ReleaseManifestV5.FileEntry entry = new ReleaseManifestV5.FileEntry(
                    "mods/fixed.jar", Hashing.sha256(expected), expected.length, "mod", true, true,
                    Set.of("client"),
                    new ReleaseManifestV5.DownloadSource(
                            "direct", "", "", null, "upstream-only", List.of(
                            new ReleaseManifestV5.DownloadEndpoint(
                                    URI.create(base + "/mirror.jar"), "mirror", "file", "cn", 10, true),
                            new ReleaseManifestV5.DownloadEndpoint(
                                    URI.create(base + "/official.jar"), "official", "file", "global", 100, false))));
            ModSyncConfig config = config(root, URI.create(base + "/manifest.json"), false, false);
            byte[] actual = new ReleaseArtifactResolver(config, message -> { }).fetch(entry);
            check(Arrays.equals(actual, expected) && mirrorRequests.get() == 1 && officialRequests.get() == 1,
                    "镜像返回错误内容时必须由 SHA256 拒绝并回退官方固定候选");
            pass("v5 mirror hash failures fall back to the official candidate");
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private void testV5ReleaseManifestParsingAndValidation() {
        String manifestText = """
                {
                  "schema": 5,
                  "releaseId": "motiquies-2.0.0-ota.1",
                  "releaseSequence": 2000001,
                  "minimumMCSyncVersion": "2.0.0",
                  "files": [
                    {
                      "path": "mods/example-1.0.jar",
                      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                      "size": 1234,
                      "kind": "mod",
                      "required": true,
                      "restartRequired": true,
                      "side": ["client"]
                    }
                  ],
                  "configOperations": [
                    {
                      "path": "config/example-common.toml",
                      "op": "config-set",
                      "format": "toml",
                      "key": "features.safeMode",
                      "valueType": "boolean",
                      "expected": false,
                      "desired": true,
                      "conflictPolicy": "replace-if-expected",
                      "restartRequired": true
                    }
                  ]
                }
                """;
        ReleaseManifestV5 parsed = ReleaseManifestV5.parse(manifestText.getBytes(StandardCharsets.UTF_8));
        check(parsed.releaseSequence() == 2_000_001L, "v5 发布序号应精确解析");
        check(parsed.files().getFirst().path().equals("mods/example-1.0.jar"), "v5 文件路径应精确解析");
        check(parsed.configOperations().getFirst().key().equals("features.safeMode"),
                "v5 应支持精确到配置键的 OTA");
        ReleaseManifestV5 roundTrip = ReleaseManifestV5.parse(parsed.serialize());
        check(roundTrip.equals(parsed), "v5 清单规范序列化后应无语义漂移");
        check(Arrays.equals(parsed.serialize(), roundTrip.serialize()), "v5 规范 JSON 输出必须确定性一致");

        expectFailure(() -> ReleaseManifestV5.parse(manifestText
                .replace("mods/example-1.0.jar", "../outside.jar")
                .getBytes(StandardCharsets.UTF_8)));
        expectFailure(() -> ReleaseManifestV5.parse(manifestText
                .replace("\"releaseSequence\": 2000001,", "\"releaseSequence\": 2000001,\n  \"releaseSequence\": 2000002,")
                .getBytes(StandardCharsets.UTF_8)));
        expectFailure(() -> ReleaseManifestV5.parse(manifestText
                .replace("\"schema\": 5,", "\"schema\": 5,\n  \"typoField\": true,")
                .getBytes(StandardCharsets.UTF_8)));
        expectFailure(() -> ReleaseManifestV5.parse(manifestText
                .replace("features.safeMode", "security.apiToken")
                .getBytes(StandardCharsets.UTF_8)));
        expectFailure(() -> ReleaseManifestV5.parse(manifestText
                .replace("\"configOperations\": [", "\"configOperations\": [{"
                        + "\"path\":\"kubejs/startup_scripts/a.js\",\"op\":\"file-replace\","
                        + "\"format\":\"text\",\"desired\":\"from-file-entry\"},")
                .getBytes(StandardCharsets.UTF_8)));
        pass("v5 release manifest parsing, config operations, and unsafe-input rejection");
    }

    private void testReleaseSequenceAntiDowngradeGate() throws Exception {
        Path root = Files.createTempDirectory("mcsync-release-gate-");
        try {
            ReleaseSequenceGate gate = new ReleaseSequenceGate(root.resolve(".modsync"));
            ReleaseManifestV5 first = releaseManifest(100, "release-100");
            String firstHash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
            check(gate.validate(first, firstHash).newRelease(), "首次发布应允许进入事务");
            check(!Files.exists(gate.stateFile()), "仅验证清单时不得提前提交防降级状态");
            gate.commit(first, firstHash);
            check(gate.validate(first, firstHash).alreadyApplied(), "完全相同的发布应幂等");

            expectIoFailure(() -> gate.validate(releaseManifest(99, "release-99"),
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));
            expectIoFailure(() -> gate.validate(releaseManifest(100, "forked-release-100"),
                    "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"));

            ReleaseManifestV5 next = releaseManifest(101, "release-101");
            String nextHash = "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd";
            check(gate.validate(next, nextHash).newRelease(), "更高发布序号应允许升级");
            gate.commit(next, nextHash);
            check(gate.read().releaseSequence() == 101, "成功事务后应原子记录最新发布序号");
            pass("monotonic release sequence blocks downgrade and same-sequence forks");
        } finally {
            deleteTree(root);
        }
    }

    private void testV5PlatformDownloadSourcesAndMirrorTrustBoundary() {
        String manifest = """
                {
                  "schema": 5,
                  "releaseId": "platform-downloads-1",
                  "releaseSequence": 2000002,
                  "minimumMCSyncVersion": "2.0.0",
                  "files": [
                    {
                      "path": "mods/modrinth-example.jar",
                      "sha256": "1111111111111111111111111111111111111111111111111111111111111111",
                      "size": 10,
                      "kind": "mod",
                      "download": {
                        "type": "modrinth",
                        "projectId": "AABBCCDD",
                        "versionId": "IIJJKKLL",
                        "distributionPolicy": "upstream-only",
                        "endpoints": [
                          {"url": "https://api.modrinth.com/v2/", "role": "official", "purpose": "api", "region": "global", "priority": 100},
                          {"url": "https://mod.mcimirror.top/modrinth/v2/", "role": "mirror", "purpose": "api", "region": "cn", "priority": 10, "thirdParty": true}
                        ]
                      }
                    },
                    {
                      "path": "mods/curseforge-example.jar",
                      "sha256": "2222222222222222222222222222222222222222222222222222222222222222",
                      "size": 20,
                      "kind": "mod",
                      "download": {
                        "type": "curseforge",
                        "projectId": "123456",
                        "fileId": 7654321,
                        "distributionPolicy": "upstream-only",
                        "endpoints": [
                          {"url": "https://api.curseforge.com/v1/", "role": "official", "purpose": "api", "region": "global", "priority": 100}
                          ,{"url": "https://mod.mcimirror.top/curseforge/v1/", "role": "mirror", "purpose": "api", "region": "cn", "priority": 10, "thirdParty": true}
                        ]
                      }
                    }
                  ]
                }
                """;
        ReleaseManifestV5 parsed = ReleaseManifestV5.parse(manifest.getBytes(StandardCharsets.UTF_8));
        check(parsed.files().get(0).download().type().equals("modrinth"), "应保留 Modrinth 固定版本来源");
        check(parsed.files().get(0).download().endpoints().get(1).role().equals("mirror"),
                "中国镜像应作为显式候选端点，而非替换信任根");
        check(parsed.files().get(1).download().distributionPolicy().equals("upstream-only"),
                "CurseForge 上游下载不应被误标为允许随包再分发");

        expectFailure(() -> ReleaseManifestV5.parse(manifest
                .replace("https://mod.mcimirror.top/modrinth/v2/", "http://mirror.invalid/v2/")
                .getBytes(StandardCharsets.UTF_8)));
        expectFailure(() -> ReleaseManifestV5.parse(manifest
                .replace("\"fileId\": 7654321", "\"fileId\": 0")
                .getBytes(StandardCharsets.UTF_8)));
        expectFailure(() -> ReleaseManifestV5.parse(manifest
                .replace("\"type\": \"modrinth\"", "\"type\": \"publisher-hosted\"")
                .getBytes(StandardCharsets.UTF_8)));
        ReleaseManifestV5 proxied = ReleaseManifestV5.parse(manifest
                .replace(
                        "\"url\": \"https://mod.mcimirror.top/modrinth/v2/\", \"role\": \"mirror\", \"purpose\": \"api\"",
                        "\"url\": \"https://mirror.example.invalid/files/example.jar\", \"role\": \"mirror\", \"purpose\": \"file\"")
                .getBytes(StandardCharsets.UTF_8));
        check(proxied.files().getFirst().download().endpoints().get(1).thirdParty(),
                "特殊网络环境允许 upstream-only 使用显式第三方文件代理");
        expectFailure(() -> ReleaseManifestV5.parse(manifest
                .replace("\"thirdParty\": true", "\"thirdParty\": false")
                .getBytes(StandardCharsets.UTF_8)));
        pass("v5 pins Modrinth/CurseForge sources and treats mirrors as hash-checked candidates");
    }

    private void testV5CustomBuildUsesPublisherHostedDistribution() {
        String manifest = """
                {
                  "schema": 5,
                  "releaseId": "custom-build-1",
                  "releaseSequence": 2000003,
                  "minimumMCSyncVersion": "2.0.0",
                  "files": [{
                    "path": "mods/our-compat-fix.jar",
                    "sha256": "3333333333333333333333333333333333333333333333333333333333333333",
                    "size": 30,
                    "kind": "mod",
                    "download": {
                      "type": "publisher-hosted",
                      "distributionPolicy": "redistributable"
                    }
                  }]
                }
                """;
        ReleaseManifestV5 parsed = ReleaseManifestV5.parse(manifest.getBytes(StandardCharsets.UTF_8));
        check(parsed.files().getFirst().download().type().equals("publisher-hosted"),
                "手工适配和自制模组应保留发布目录下载方式");
        pass("custom builds retain publisher-hosted delivery only when redistributable");
    }

    private void testOnlyModsMayUsePlatformDownloadSources() {
        String localResourcePack = """
                {
                  "schema":5,"releaseId":"nonmod-local","releaseSequence":2000004,
                  "minimumMCSyncVersion":"2.0.0",
                  "files":[{
                    "path":"resourcepacks/example.zip",
                    "sha256":"4444444444444444444444444444444444444444444444444444444444444444",
                    "size":40,"kind":"resource-pack",
                    "download":{"type":"publisher-hosted","distributionPolicy":"redistributable"}
                  }]
                }
                """;
        ReleaseManifestV5 parsed = ReleaseManifestV5.parse(localResourcePack.getBytes(StandardCharsets.UTF_8));
        check(parsed.files().getFirst().download().type().equals("publisher-hosted"),
                "资源包等非 Mod 文件应固定使用本地发布源");

        String platformSource = """
                "download":{
                  "type":"modrinth","projectId":"demo","versionId":"fixed-version",
                  "distributionPolicy":"upstream-only",
                  "endpoints":[{"url":"https://api.modrinth.com/v2/","role":"official",
                    "purpose":"api","region":"global","priority":100}]
                }
                """;
        expectFailure(() -> ReleaseManifestV5.parse(localResourcePack
                .replace("\"download\":{\"type\":\"publisher-hosted\",\"distributionPolicy\":\"redistributable\"}",
                        platformSource.strip())
                .getBytes(StandardCharsets.UTF_8)));
        expectFailure(() -> ReleaseManifestV5.parse(localResourcePack
                .replace("\"download\":{\"type\":\"publisher-hosted\",\"distributionPolicy\":\"redistributable\"}",
                        "\"download\":{\"type\":\"direct\",\"distributionPolicy\":\"upstream-only\","
                                + "\"endpoints\":[{\"url\":\"https://files.example.test/a.zip\","
                                + "\"role\":\"official\",\"purpose\":\"file\",\"region\":\"global\","
                                + "\"priority\":100}]}" )
                .getBytes(StandardCharsets.UTF_8)));
        pass("only direct mods may use platform or upstream download sources");
    }

    private void testDefaultDownloadConcurrencyIs128() {
        String old = System.getProperty("mcsync.downloadThreads");
        try {
            System.clearProperty("mcsync.downloadThreads");
            check(ParallelDownloadRunner.configuredThreads() == 128
                            && ParallelDownloadRunner.threadCount(300) == 128
                            && ParallelDownloadRunner.threadCount(12) == 12,
                    "默认并发应为 128，小任务不得创建多余线程");
            System.setProperty("mcsync.downloadThreads", "16");
            check(ParallelDownloadRunner.threadCount(300) == 16, "应允许管理员降低下载并发");
            System.setProperty("mcsync.downloadThreads", "999");
            check(ParallelDownloadRunner.configuredThreads() == 128, "配置不得超过安全上限 128");
            System.setProperty("mcsync.downloadThreads", "0");
            check(ParallelDownloadRunner.configuredThreads() == 1, "配置下限应为 1");
            System.setProperty("mcsync.downloadThreads", "invalid");
            check(ParallelDownloadRunner.configuredThreads() == 128, "无效配置应回退默认 128");
        } finally {
            if (old == null) System.clearProperty("mcsync.downloadThreads");
            else System.setProperty("mcsync.downloadThreads", old);
        }
        pass("download concurrency defaults to 128 with bounded override");
    }

    private void testModArtifactClassificationAndFingerprintNormalization() {
        check(PublisherModAutoMatcher.isModArtifact("mods/example.jar", "mod"),
                "直接位于 mods 的 JAR 应进入平台匹配");
        check(!PublisherModAutoMatcher.isModArtifact("mods/nested/example.jar", "mod")
                        && !PublisherModAutoMatcher.isModArtifact("resourcepacks/example.jar", "mod")
                        && !PublisherModAutoMatcher.isModArtifact("mods/example.jar", "support")
                        && !PublisherModAutoMatcher.isModArtifact("mods/example.zip", "mod"),
                "嵌套、非 mods、类型不符和非 JAR 文件不得进入模组站匹配");
        check(PublisherModAutoMatcher.curseForgeFingerprint("a b\r\nc\t".getBytes(StandardCharsets.UTF_8))
                        == PublisherModAutoMatcher.curseForgeFingerprint("abc".getBytes(StandardCharsets.UTF_8)),
                "CurseForge fingerprint 必须按平台规则忽略 ASCII 空白");
        pass("mod artifact classification and CurseForge fingerprint normalization");
    }

    private void testChinaApiMirrorPresetsRemainExplicitThirdPartyCandidates() {
        List<ReleaseManifestV5.DownloadEndpoint> modrinth =
                DownloadEndpointPresets.forPlatform("modrinth", true);
        check(modrinth.getFirst().uri().equals(DownloadEndpointPresets.MODRINTH_MCIMIRROR),
                "Modrinth 中国区预设应使用 MCIMirror 的 modrinth/v2 前缀");
        check(modrinth.getFirst().thirdParty() && modrinth.getFirst().role().equals("mirror"),
                "镜像预设必须保留第三方身份");
        check(modrinth.getLast().uri().equals(DownloadEndpointPresets.MODRINTH_OFFICIAL),
                "镜像预设必须保留官方回退");

        List<ReleaseManifestV5.DownloadEndpoint> curseforge =
                DownloadEndpointPresets.forPlatform("curseforge", true);
        check(curseforge.getFirst().uri().equals(DownloadEndpointPresets.CURSEFORGE_MCIMIRROR),
                "CurseForge 中国区预设应使用 MCIMirror 的 curseforge/v1 前缀");
        check(curseforge.getLast().role().equals("official"), "CurseForge 也必须保留官方候选");
        pass("MCIMirror API presets remain explicit third-party candidates with official fallback");
    }

    private static ReleaseManifestV5 releaseManifest(long sequence, String releaseId) {
        String json = """
                {
                  "schema": 5,
                  "releaseId": "%s",
                  "releaseSequence": %d,
                  "minimumMCSyncVersion": "2.0.0",
                  "files": [{
                    "path": "mods/mcsync.jar",
                    "sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                    "size": 1,
                    "kind": "mod",
                    "side": ["client"]
                  }]
                }
                """.formatted(releaseId, sequence);
        return ReleaseManifestV5.parse(json.getBytes(StandardCharsets.UTF_8));
    }

    private void testStructuredConfigMutationEngine() {
        ReleaseManifestV5.ConfigOperation toml = configOperation("""
                {
                  "path":"config/example-common.toml","op":"config-set","format":"toml",
                  "key":"features.safeMode","valueType":"boolean","expected":false,"desired":true,
                  "missingPolicy":"block","conflictPolicy":"replace-if-expected"
                }
                """);
        byte[] tomlInput = "# user note\r\n[features]\r\nsafeMode = false # keep this\r\nvolume = 7\r\n"
                .getBytes(StandardCharsets.UTF_8);
        ConfigMutationEngine.MutationResult tomlResult = ConfigMutationEngine.apply(tomlInput, toml);
        String tomlOutput = new String(tomlResult.bytes(), StandardCharsets.UTF_8);
        check(tomlResult.changed(), "TOML 精确键更新应报告 changed");
        check(tomlOutput.equals("# user note\r\n[features]\r\nsafeMode = true # keep this\r\nvolume = 7\r\n"),
                "TOML 更新必须保留注释、换行和无关配置");

        ReleaseManifestV5.ConfigOperation json = configOperation("""
                {
                  "path":"kubejs/config/common.json","op":"config-merge","format":"json",
                  "key":"server.features","valueType":"object","expected":{"existing":1},
                  "desired":{"enabled":true,"nested":{"limit":8}},
                  "missingPolicy":"create","conflictPolicy":"replace-if-expected"
                }
                """);
        ConfigMutationEngine.MutationResult jsonResult = ConfigMutationEngine.apply(
                "{\"server\":{\"features\":{\"existing\":1},\"local\":\"keep\"}}"
                        .getBytes(StandardCharsets.UTF_8), json);
        @SuppressWarnings("unchecked")
        Map<String, Object> jsonRoot = (Map<String, Object>) StrictJson.parse(
                new String(jsonResult.bytes(), StandardCharsets.UTF_8));
        @SuppressWarnings("unchecked")
        Map<String, Object> server = (Map<String, Object>) jsonRoot.get("server");
        check(server.get("local").equals("keep"), "JSON merge 必须保留相邻本地配置");
        @SuppressWarnings("unchecked")
        Map<String, Object> features = (Map<String, Object>) server.get("features");
        check(features.containsKey("existing") && features.get("enabled").equals(Boolean.TRUE),
                "JSON merge 应保留旧对象并合入目标键");

        ReleaseManifestV5.ConfigOperation properties = configOperation("""
                {
                  "path":"modsync.properties","op":"config-set","format":"properties",
                  "key":"requestTimeoutSeconds","valueType":"integer","expected":60,"desired":90,
                  "missingPolicy":"block","conflictPolicy":"replace-if-expected"
                }
                """);
        ConfigMutationEngine.MutationResult propertiesResult = ConfigMutationEngine.apply(
                "# local\nrequestTimeoutSeconds=60\nlanguage=zh_cn"
                        .getBytes(StandardCharsets.UTF_8), properties);
        check(new String(propertiesResult.bytes(), StandardCharsets.UTF_8)
                        .equals("# local\nrequestTimeoutSeconds=90\nlanguage=zh_cn"),
                "properties 更新必须保留无关行且不凭空增加末尾换行");

        ReleaseManifestV5.ConfigOperation keepLocal = configOperation("""
                {
                  "path":"config/example.toml","op":"config-set","format":"toml",
                  "key":"enabled","valueType":"boolean","expected":false,"desired":false,
                  "missingPolicy":"block","conflictPolicy":"keep-local"
                }
                """);
        byte[] localBytes = "enabled = true\n".getBytes(StandardCharsets.UTF_8);
        ConfigMutationEngine.MutationResult kept = ConfigMutationEngine.apply(localBytes, keepLocal);
        check(!kept.changed() && Arrays.equals(kept.bytes(), localBytes)
                        && kept.outcome().equals("kept-local"),
                "用户已修改的配置在 keep-local 策略下必须原样保留");

        ReleaseManifestV5.ConfigOperation missingSkip = configOperation("""
                {
                  "path":"config/example.toml","op":"config-set","format":"toml",
                  "key":"missing","valueType":"boolean","expected":false,"desired":true,
                  "missingPolicy":"skip","conflictPolicy":"block"
                }
                """);
        ConfigMutationEngine.MutationResult skipped = ConfigMutationEngine.apply(localBytes, missingSkip);
        check(!skipped.changed() && skipped.outcome().equals("skipped-missing"),
                "missingPolicy=skip 不得创建未知配置键");

        expectFailure(() -> ConfigMutationEngine.apply(
                "enabled = true\nenabled = false\n".getBytes(StandardCharsets.UTF_8), keepLocal));
        expectFailure(() -> ConfigMutationEngine.apply(new byte[]{(byte) 0xC3, (byte) 0x28}, keepLocal));
        pass("structured config OTA preserves local data and fails closed on ambiguity");
    }

    private static ReleaseManifestV5.ConfigOperation configOperation(String operationJson) {
        String manifest = """
                {
                  "schema":5,
                  "releaseId":"config-test",
                  "releaseSequence":1,
                  "minimumMCSyncVersion":"2.0.0",
                  "files":[{
                    "path":"mods/anchor.jar",
                    "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "size":1,
                    "kind":"mod"
                  }],
                  "configOperations":[%s]
                }
                """.formatted(operationJson);
        return ReleaseManifestV5.parse(manifest.getBytes(StandardCharsets.UTF_8))
                .configOperations().getFirst();
    }

    private void testV5AtomicReleaseTransactionAndOwnership() throws Exception {
        Path root = Files.createTempDirectory("mcsync-v5-transaction-");
        try {
            byte[] firstMod = "first-mod".getBytes(StandardCharsets.UTF_8);
            byte[] secondMod = "second-mod".getBytes(StandardCharsets.UTF_8);
            Files.createDirectories(root.resolve("config"));
            Files.writeString(root.resolve("config/gameplay.toml"),
                    "# local comment\n[balance]\nenabled = false\nuserChoice = 42\n",
                    StandardCharsets.UTF_8);

            ReleaseManifestV5 first = transactionManifest(
                    10,
                    "tx-10",
                    List.of(fileJson("mods/old.jar", firstMod)),
                    """
                    [{
                      "path":"config/gameplay.toml","op":"config-set","format":"toml",
                      "key":"balance.enabled","valueType":"boolean","expected":false,"desired":true,
                      "missingPolicy":"block","conflictPolicy":"replace-if-expected"
                    }]
                    """);
            ReleaseTransactionEngine engine = new ReleaseTransactionEngine(root, 2);
            ReleaseTransactionEngine.Result firstResult = engine.apply(
                    first, Hashing.sha256(first.serialize()),
                    entry -> entry.path().equals("mods/old.jar") ? firstMod : null);
            check(firstResult.changed() && firstResult.installed() == 2 && firstResult.configChanged() == 1,
                    "首个 v5 事务应同时提交模组与配置键");
            check(Arrays.equals(Files.readAllBytes(root.resolve("mods/old.jar")), firstMod),
                    "v5 事务应写入已校验模组");
            String configured = Files.readString(root.resolve("config/gameplay.toml"));
            check(configured.contains("enabled = true") && configured.contains("userChoice = 42"),
                    "v5 配置事务应保留用户配置并修改目标键");
            check(Files.isRegularFile(firstResult.receipt()), "成功事务必须生成可审计 receipt");

            ReleaseManifestV5 second = transactionManifest(
                    11,
                    "tx-11",
                    List.of(fileJson("mods/new.jar", secondMod)),
                    "[]");
            ReleaseTransactionEngine.Result secondResult = engine.apply(
                    second, Hashing.sha256(second.serialize()), entry -> secondMod);
            check(secondResult.removed() == 1 && !Files.exists(root.resolve("mods/old.jar")),
                    "managed 范围内的旧受管文件应按 ownership 哈希移除");
            check(Arrays.equals(Files.readAllBytes(root.resolve("mods/new.jar")), secondMod),
                    "下一发布应原子安装新文件");

            Files.writeString(root.resolve("mods/new.jar"), "user-modified", StandardCharsets.UTF_8);
            byte[] thirdMod = "third-mod".getBytes(StandardCharsets.UTF_8);
            ReleaseManifestV5 third = transactionManifest(
                    12,
                    "tx-12",
                    List.of(fileJson("mods/third.jar", thirdMod)),
                    "[]");
            engine.apply(third, Hashing.sha256(third.serialize()), entry -> thirdMod);
            check(Files.readString(root.resolve("mods/new.jar")).equals("user-modified"),
                    "用户修改过的旧受管文件不得被 ownership 清理覆盖");

            ReleaseManifestV5 failed = transactionManifest(
                    13,
                    "tx-13",
                    List.of(fileJson("mods/bad.jar", "expected".getBytes(StandardCharsets.UTF_8))),
                    "[]");
            expectIoFailure(() -> engine.apply(
                    failed, Hashing.sha256(failed.serialize()),
                    entry -> "wrong".getBytes(StandardCharsets.UTF_8)));
            check(new ReleaseSequenceGate(root.resolve(".modsync")).read().releaseSequence() == 12,
                    "下载或验签失败不得推进防降级序号");
            check(!Files.exists(root.resolve("mods/bad.jar")), "失败事务不得留下半成品");

            ReleaseManifestV5 forbidden = transactionManifest(
                    13,
                    "tx-forbidden",
                    List.of(fileJson("saves/world/level.dat", thirdMod)),
                    "[]");
            expectIoFailure(() -> engine.apply(
                    forbidden, Hashing.sha256(forbidden.serialize()), entry -> thirdMod));

            Files.writeString(root.resolve("options.txt"), "user-options", StandardCharsets.UTF_8);
            byte[] packagedOptions = "pack-options".getBytes(StandardCharsets.UTF_8);
            String firstInstallJson = """
                    {
                      "schema":5,"releaseId":"tx-first-install","releaseSequence":13,
                      "minimumMCSyncVersion":"2.0.0",
                      "managedScopes":[
                        {"path":"mods","policy":"additive"},
                        {"path":"options.txt","policy":"first-install"}
                      ],
                      "files":[%s,%s],"configOperations":[]
                    }
                    """.formatted(fileJson("mods/third.jar", thirdMod), fileJson("options.txt", packagedOptions));
            ReleaseManifestV5 firstInstall = ReleaseManifestV5.parse(
                    firstInstallJson.getBytes(StandardCharsets.UTF_8));
            AtomicInteger fetched = new AtomicInteger();
            engine.apply(firstInstall, Hashing.sha256(firstInstall.serialize()), entry -> {
                fetched.incrementAndGet();
                return thirdMod;
            });
            check(Files.readString(root.resolve("options.txt")).equals("user-options") && fetched.get() == 0,
                    "first-install 文件和已正确安装的内容都应直接复用，不得重复下载覆盖");

            Path script = root.resolve("kubejs/startup_scripts/controlled.js");
            Files.createDirectories(script.getParent());
            byte[] oldScript = "old-script\n".getBytes(StandardCharsets.UTF_8);
            byte[] newScript = "new-script\n".getBytes(StandardCharsets.UTF_8);
            Files.write(script, oldScript);
            ReleaseManifestV5 fileReplace = ReleaseManifestV5.parse(("""
                    {
                      "schema":5,"releaseId":"tx-file-replace","releaseSequence":14,
                      "minimumMCSyncVersion":"2.0.0",
                      "managedScopes":[{"path":"kubejs","policy":"additive"}],
                      "files":[%s],
                      "configOperations":[{
                        "path":"kubejs/startup_scripts/controlled.js","op":"file-replace","format":"text",
                        "valueType":"binary","expectedSha256":"%s","desired":"from-file-entry",
                        "missingPolicy":"block","conflictPolicy":"replace-if-expected"
                      }]
                    }
                    """).formatted(
                    fileJson("kubejs/startup_scripts/controlled.js", newScript), Hashing.sha256(oldScript))
                    .getBytes(StandardCharsets.UTF_8));
            engine.apply(fileReplace, Hashing.sha256(fileReplace.serialize()), entry -> newScript);
            check(Arrays.equals(Files.readAllBytes(script), newScript),
                    "file-replace 只有在旧 SHA 前像精确匹配时才应提交");

            ReleaseManifestV5 wrongPreimage = ReleaseManifestV5.parse(("""
                    {
                      "schema":5,"releaseId":"tx-file-replace-wrong","releaseSequence":15,
                      "minimumMCSyncVersion":"2.0.0",
                      "managedScopes":[{"path":"kubejs","policy":"additive"}],
                      "files":[%s],
                      "configOperations":[{
                        "path":"kubejs/startup_scripts/controlled.js","op":"file-replace","format":"text",
                        "valueType":"binary","expectedSha256":"%s","desired":"from-file-entry"
                      }]
                    }
                    """).formatted(
                    fileJson("kubejs/startup_scripts/controlled.js", oldScript), Hashing.sha256(oldScript))
                    .getBytes(StandardCharsets.UTF_8));
            expectIoFailure(() -> engine.apply(
                    wrongPreimage, Hashing.sha256(wrongPreimage.serialize()), entry -> oldScript));
            check(Arrays.equals(Files.readAllBytes(script), newScript)
                            && new ReleaseSequenceGate(root.resolve(".modsync")).read().releaseSequence() == 14,
                    "file-replace 前像不符必须保持当前文件并禁止推进发布序号");
            pass("v5 release transaction is atomic, ownership-aware, and save-state safe");
        } finally {
            deleteTree(root);
        }
    }

    private static ReleaseManifestV5 transactionManifest(
            long sequence,
            String releaseId,
            List<String> files,
            String configOperations) {
        String json = """
                {
                  "schema":5,
                  "releaseId":"%s",
                  "releaseSequence":%d,
                  "minimumMCSyncVersion":"2.0.0",
                  "managedScopes":[
                    {"path":"mods","policy":"managed"},
                    {"path":"config","policy":"additive"}
                  ],
                  "files":[%s],
                  "configOperations":%s
                }
                """.formatted(releaseId, sequence, String.join(",", files), configOperations);
        return ReleaseManifestV5.parse(json.getBytes(StandardCharsets.UTF_8));
    }

    private void testV5InterruptedCommitRecoversFromDurableJournal() throws Exception {
        Path root = Files.createTempDirectory("mcsync-v5-recovery-");
        try {
            Path target = root.resolve("mods/recover.jar");
            Path transaction = root.resolve(".modsync/transactions/interrupted-test");
            Path backup = transaction.resolve("backup/mods/recover.jar");
            Files.createDirectories(target.getParent());
            Files.createDirectories(backup.getParent());
            byte[] original = "original-before-crash".getBytes(StandardCharsets.UTF_8);
            Files.write(backup, original);
            Files.writeString(target, "partially-committed", StandardCharsets.UTF_8);
            Files.writeString(transaction.resolve("journal.json"), """
                    {
                      "schema":1,"state":"PREPARED","releaseId":"interrupted","releaseSequence":77,
                      "manifestSha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                      "createdAt":"2026-08-18T00:00:00Z",
                      "backups":[{"path":"mods/recover.jar","existed":true,"sha256":"%s"}]
                    }
                    """.formatted(Hashing.sha256(original)), StandardCharsets.UTF_8);
            ReleaseTransactionEngine engine = new ReleaseTransactionEngine(root, 2);
            check(engine.recoverPendingTransactions() == 1
                            && Arrays.equals(Files.readAllBytes(target), original),
                    "下次启动必须从持久日志恢复强杀时的部分提交");
            check(!Files.exists(transaction.resolve("journal.json"))
                            && Files.isRegularFile(transaction.resolve("recovery-receipt.json")),
                    "自动恢复完成后应留下恢复回执并清除活动日志");
            check(engine.recoverPendingTransactions() == 0,
                    "已恢复事务必须幂等，不得在后续启动重复回滚");
            pass("v5 interrupted commits recover from durable journals");
        } finally {
            deleteTree(root);
        }
    }

    private void testV5SelfUpdateReplacesLegacyJarInSameTransaction() throws Exception {
        Path root = Files.createTempDirectory("mcsync-v5-self-update-");
        try {
            Files.createDirectories(root.resolve("mods"));
            Path legacy = root.resolve("mods/MCModSync-1.9.2.jar");
            Path candidate = root.resolve("candidate-MCSync-2.1.0.jar");
            writeFabricJar(legacy, BuildInfo.TECHNICAL_MOD_ID, "1.9.2");
            writeFabricJar(candidate, BuildInfo.TECHNICAL_MOD_ID, "2.1.0");
            byte[] candidateBytes = Files.readAllBytes(candidate);
            byte[] gameplay = "gameplay-update".getBytes(StandardCharsets.UTF_8);
            ReleaseManifestV5 manifest = transactionManifest(
                    30,
                    "self-update-30",
                    List.of(
                            fileJson("mods/MCSync-2.1.0.jar", candidateBytes),
                            fileJson("mods/gameplay.jar", gameplay)),
                    "[]");
            ReleaseTransactionEngine.Result result = new ReleaseTransactionEngine(root, 2).apply(
                    manifest, Hashing.sha256(manifest.serialize()),
                    entry -> entry.path().contains("MCSync") ? candidateBytes : gameplay);
            check(result.installed() == 2 && result.removed() == 1
                            && !Files.exists(legacy)
                            && ModMetadata.readVersion(root.resolve("mods/MCSync-2.1.0.jar")).equals("2.1.0")
                            && Arrays.equals(Files.readAllBytes(root.resolve("mods/gameplay.jar")), gameplay),
                    "1.9.x 同 modId JAR 必须与 2.0+ 自更新及玩法文件在一个事务中替换");
            long selfJars;
            try (var stream = Files.list(root.resolve("mods"))) {
                selfJars = stream.filter(Files::isRegularFile)
                        .filter(path -> ModMetadata.readModId(path).equals(BuildInfo.TECHNICAL_MOD_ID))
                        .count();
            }
            check(selfJars == 1, "自更新后 mods 中必须只剩一个技术 modId=mcmodsync 的 JAR");
            pass("v5 self update replaces the legacy 1.9.x JAR atomically");
        } finally {
            deleteTree(root);
        }
    }

    private static String fileJson(String path, byte[] bytes) {
        return """
                {
                  "path":"%s","sha256":"%s","size":%d,"kind":"%s",
                  "required":true,"restartRequired":true,"side":["client"]
                }
                """.formatted(
                path,
                Hashing.sha256(bytes),
                bytes.length,
                path.startsWith("mods/") ? "mod" : "support");
    }

    private void testV5CoordinatorDownloadsBeforeStartupAndBecomesIdempotent() throws Exception {
        Path root = Files.createTempDirectory("mcsync-v5-http-");
        HttpServer server = null;
        try {
            byte[] mod = "v5-http-mod".getBytes(StandardCharsets.UTF_8);
            ReleaseManifestV5 manifest = transactionManifest(
                    20, "http-20", List.of(fileJson("mods/demo.jar", mod)), "[]");
            byte[] manifestBytes = manifest.serialize();
            AtomicInteger manifestRequests = new AtomicInteger();
            AtomicInteger fileRequests = new AtomicInteger();
            server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
            server.createContext("/release/manifest.json", exchange -> {
                manifestRequests.incrementAndGet();
                respond(exchange, 200, manifestBytes, null);
            });
            server.createContext("/release/mods/demo.jar", exchange -> {
                fileRequests.incrementAndGet();
                respond(exchange, 200, mod, null);
            });
            server.start();
            URI uri = URI.create("http://127.0.0.1:" + server.getAddress().getPort()
                    + "/release/manifest.json");
            ModSyncConfig runtimeConfig = config(root, uri, false, false);
            SyncProbeResult initialProbe = ModSyncCoordinator.probe(runtimeConfig, message -> { }, SyncObserver.NONE);
            check(initialProbe.status() == SyncProbeResult.Status.CHANGES_REQUIRED && fileRequests.get() == 1,
                    "NeoForge 初始检查应先在当前窗口生命周期内下载并缓存更新");
            SyncResult applied = ModSyncCoordinator.synchronize(runtimeConfig, message -> { }, SyncObserver.NONE);
            check(applied.status() == SyncResult.Status.UPDATED
                            && Arrays.equals(Files.readAllBytes(root.resolve("mods/demo.jar")), mod),
                    "启动辅助进程应在游戏加载前完成 v5 文件下载与提交");
            check(fileRequests.get() == 1, "辅助进程提交时应复用已验哈希缓存，不得再次联网下载");

            SyncProbeResult probe = ModSyncCoordinator.probe(runtimeConfig, message -> { }, SyncObserver.NONE);
            check(probe.status() == SyncProbeResult.Status.UP_TO_DATE,
                    "同一 releaseSequence 完成后再次启动应幂等通过");
            SyncResult repeated = ModSyncCoordinator.synchronize(runtimeConfig, message -> { }, SyncObserver.NONE);
            check(repeated.status() == SyncResult.Status.UNCHANGED && fileRequests.get() == 1,
                    "幂等启动不得重新下载已正确安装的文件");

            Files.writeString(root.resolve("mods/demo.jar"), "tampered", StandardCharsets.UTF_8);
            SyncProbeResult repairProbe = ModSyncCoordinator.probe(
                    runtimeConfig, message -> { }, SyncObserver.NONE);
            check(repairProbe.status() == SyncProbeResult.Status.CHANGES_REQUIRED,
                    "同一 releaseSequence 的受管文件被篡改后必须重新进入修复流程");
            SyncResult repaired = ModSyncCoordinator.synchronize(
                    runtimeConfig, message -> { }, SyncObserver.NONE);
            check(repaired.status() == SyncResult.Status.UPDATED
                            && Arrays.equals(Files.readAllBytes(root.resolve("mods/demo.jar")), mod),
                    "同版本同清单也必须修复哈希漂移，不能被防降级状态误判为已完成");
            check(fileRequests.get() == 1,
                    "同版本修复应复用已验哈希缓存，不必重复从远端下载");
            check(manifestRequests.get() == 6, "每次启动检查都应重新取得小型清单以发现 OTA");
            pass("v5 coordinator downloads pre-start and remains idempotent");
        } finally {
            if (server != null) server.stop(0);
            deleteTree(root);
        }
    }

    private void testV5PublisherProjectBuildsDeterministicRelease() throws Exception {
        Path root = Files.createTempDirectory("mcsync-v5-publisher-");
        try {
            byte[] custom = "custom-build".getBytes(StandardCharsets.UTF_8);
            byte[] upstream = "upstream-build".getBytes(StandardCharsets.UTF_8);
            Files.createDirectories(root.resolve("mods"));
            Files.write(root.resolve("mods/custom.jar"), custom);
            Files.write(root.resolve("mods/upstream.jar"), upstream);
            Path project = root.resolve("publisher-project.json");
            Files.writeString(project, """
                    {
                      "schema":1,"releaseId":"publisher-1","releaseSequence":100,
                      "minimumMCSyncVersion":"2.0.0",
                      "managedScopes":[{"path":"mods","policy":"managed"}],
                      "files":[
                        {
                          "path":"mods/custom.jar","kind":"mod","required":true,
                          "restartRequired":true,"side":["client"],
                          "download":{"type":"publisher-hosted","distributionPolicy":"redistributable"}
                        },
                        {
                          "path":"mods/upstream.jar","kind":"mod","required":true,
                          "restartRequired":true,"side":["client"],
                          "download":{
                            "type":"direct","distributionPolicy":"upstream-only",
                            "endpoints":[{
                              "url":"https://downloads.example.invalid/upstream.jar",
                              "role":"official","purpose":"file","region":"global","priority":100
                            }]
                          }
                        }
                      ],
                      "configOperations":[]
                    }
                    """, StandardCharsets.UTF_8);
            @SuppressWarnings("unchecked")
            Map<String, Object> inMemoryProject = (Map<String, Object>) StrictJson.parse(
                    Files.readString(project, StandardCharsets.UTF_8));
            ReleaseManifestV5 validated = PublisherProjectV5.validateProject(root, inMemoryProject);
            check(validated.files().size() == 2 && validated.configOperations().isEmpty(),
                    "GUI 内存项目应在不写输出的前提下完成严格 v5 预检");
            Path output = root.resolve("release");
            PublisherProjectV5.Publication publication = PublisherProjectV5.publish(root, project, output);
            check(publication.hostedFiles() == 1, "发布器只应复制允许二次分发的 publisher-hosted 文件");
            check(Arrays.equals(Files.readAllBytes(output.resolve("mods/custom.jar")), custom),
                    "自制/适配模组应被复制到发布目录");
            check(!Files.exists(output.resolve("mods/upstream.jar")),
                    "upstream-only 模组不得被发布器二次打包");
            ReleaseManifestV5 generated = ReleaseManifestV5.parse(Files.readAllBytes(publication.manifestPath()));
            check(generated.files().get(0).sha256().equals(Hashing.sha256(custom))
                            && generated.files().get(1).sha256().equals(Hashing.sha256(upstream)),
                    "发布器必须锁定所有本地验证文件的精确 SHA256");
            check(Files.isRegularFile(publication.reportPath()), "发布器应输出机器可读审计报告");
            pass("v5 publisher project separates redistributable and upstream-only files");
        } finally {
            deleteTree(root);
        }
    }

    private void testPublisherCloudBundleBuildsStableAndLegacyEntrypoints() throws Exception {
        Path root = Files.createTempDirectory("mcsync-cloud-bundle-");
        try {
            long generatedSequence = PublisherProjectV5.currentTimeReleaseSequence();
            String generatedSequenceText = Long.toString(generatedSequence);
            check(generatedSequenceText.matches("\\d{17}")
                            && generatedSequenceText.substring(0, 8).equals(
                            java.time.LocalDate.now().format(java.time.format.DateTimeFormatter.BASIC_ISO_DATE)),
                    "发布序号应按当前系统日期时间生成 yyyyMMddHHmmssSSS");
            Files.createDirectories(root.resolve("game/mods"));
            Files.writeString(root.resolve("game/mods/custom.jar"), "custom", StandardCharsets.UTF_8);
            Path updater = root.resolve("MCSync-2.0.0.jar");
            writeNeoForgeJar(updater, "mcmodsync", "2.0.0");
            @SuppressWarnings("unchecked")
            Map<String, Object> project = (Map<String, Object>) StrictJson.parse("""
                    {
                      "schema":1,"releaseId":"cloud-1","releaseSequence":2000001,
                      "minimumMCSyncVersion":"2.0.0",
                      "managedScopes":[{"path":"mods","policy":"managed"}],
                      "files":[{
                        "path":"mods/custom.jar","kind":"mod","required":true,
                        "restartRequired":true,"side":["client"],
                        "download":{"type":"publisher-hosted","distributionPolicy":"redistributable"}
                      }],
                      "configOperations":[]
                    }
                    """);
            Path output = root.resolve("cloud");
            PublisherCloudBundle.Result result = PublisherCloudBundle.publish(
                    root.resolve("game"), project, output, "https://files.example.test/mcsync",
                    "channel/stable/mods-v5.json", "legacy/1.9/mods-v4.txt", "legacy/1.6/mods.txt",
                    null, "", true, updater);
            ReleaseManifestV5 stable = ReleaseManifestV5.parse(Files.readAllBytes(result.stableManifest()));
            check(stable.releaseSequence() == 2_000_001L
                            && stable.files().getFirst().download().endpoints().getFirst().uri().toASCIIString()
                            .equals("https://files.example.test/mcsync/releases/2000001/mods/custom.jar"),
                    "稳定 v5 入口应锁定不可变版本目录中的托管文件");
            ModManifest v4 = ModManifest.parse(Files.readString(
                    output.resolve("legacy/1.9/mods-v4.txt"), StandardCharsets.UTF_8));
            String v2 = Files.readString(output.resolve("legacy/1.6/mods.txt"), StandardCharsets.UTF_8);
            long v2DataRows = v2.lines().filter(line -> !line.isBlank() && !line.startsWith("#")).count();
            check(v4.entries().size() == 2 && v4.catalogVersion().equals("2000001")
                            && v2.startsWith(ModManifest.MAGIC_V2 + "\n") && v2DataRows == 2,
                    "1.9.x 与 1.6.x/1.7.x 网关都应只包含 MCSync 和配置引导");
            check(v4.managedClientConfig().orElseThrow().values().get("manifest")
                            .equals("https://files.example.test/mcsync/channel/stable/mods-v5.json"),
                    "旧版配置引导应把升级后客户端切到 2.0 稳定入口");
            check(Files.isRegularFile(output.resolve("legacy/1.6/MCModSync-Config.jar"))
                            && v2.contains("\tMCModSync-Config.jar\n"),
                    "1.6.x/1.7.x 网关必须下发已锁定的配置引导 JAR");
            check(Files.isRegularFile(result.stableManifest())
                            && result.stableManifest().getFileName().toString().equals("mods-v5.json"),
                    "新版稳定入口必须使用 mods-v5.json，旧版网关单独输出");
            pass("publisher cloud bundle builds v5 JSON and separate legacy v4/v2 materials");
        } finally {
            deleteTree(root);
        }
    }

    private void testPublisherCloudBundleExportsServerList() throws Exception {
        Path root = Files.createTempDirectory("mcsync-cloud-server-list-");
        try {
            Files.createDirectories(root.resolve("game/mods"));
            Files.writeString(root.resolve("game/mods/custom.jar"), "custom", StandardCharsets.UTF_8);
            Path servers = root.resolve("servers.dat");
            Files.writeString(servers, "server-list-fixture", StandardCharsets.UTF_8);
            @SuppressWarnings("unchecked")
            Map<String, Object> project = (Map<String, Object>) StrictJson.parse("""
                    {
                      "schema":1,"releaseId":"cloud-server-list","releaseSequence":2000002,
                      "minimumMCSyncVersion":"2.0.0",
                      "managedScopes":[{"path":"mods","policy":"managed"}],
                      "files":[{
                        "path":"mods/custom.jar","kind":"mod","required":true,
                        "restartRequired":true,"side":["client"],
                        "download":{"type":"publisher-hosted","distributionPolicy":"redistributable"}
                      }],
                      "configOperations":[]
                    }
                    """);
            Path output = root.resolve("cloud");
            PublisherCloudBundle.Result result = PublisherCloudBundle.publish(
                    root.resolve("game"), project, output, "https://files.example.test/mcsync",
                    "channel/stable/mods-v5.json", "legacy/1.9/mods-v4.txt", "legacy/1.6/mods.txt",
                    servers, "server-list/serverlist.txt", false, null);
            Path exportedServers = output.resolve("server-list/servers.dat");
            ServerListManifest manifest = ServerListManifest.parse(Files.readString(
                    result.serverListManifest(), StandardCharsets.UTF_8));
            String properties = Files.readString(result.clientProperties(), StandardCharsets.UTF_8);
            check(Files.mismatch(servers, exportedServers) == -1
                            && manifest.md5().equals(Hashing.md5(servers)),
                    "发布器应把服务器列表清单与 servers.dat 作为同级文件导出");
            check(properties.contains("syncServerList=true\n")
                            && properties.contains("serverListManifest=https://files.example.test/mcsync/server-list/serverlist.txt\n"),
                    "客户端配置模板应启用服务器列表同步并指向导出清单");
            pass("publisher cloud bundle exports server list and managed client configuration");
        } finally {
            deleteTree(root);
        }
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

    private static void expectIoFailure(ThrowingRunnable runnable) {
        try {
            runnable.run();
            throw new AssertionError("预期 I/O 操作失败，但它成功了");
        } catch (IOException expected) {
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
            Path statusJson = root.resolve(".modsync/ui-status.json");
            Path progressLog = root.resolve(".modsync/progress.log");
            check(Files.isRegularFile(status), "应写入 ui-status.txt");
            check(Files.isRegularFile(statusJson), "应写入机器可读的 ui-status.json");
            check(Files.isRegularFile(progressLog), "应写入 progress.log");
            String statusText = Files.readString(status);
            Map<?, ?> statusObject = (Map<?, ?>) StrictJson.parse(Files.readString(statusJson));
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
            check(statusObject.get("progressPermille").toString().equals("1000"),
                    "ui-status.json 应反映完成进度");
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
