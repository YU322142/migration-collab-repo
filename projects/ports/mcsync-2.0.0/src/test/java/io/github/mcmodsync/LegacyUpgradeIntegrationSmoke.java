package io.github.mcmodsync;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

/** End-to-end smoke using an actual historical MCModSync JAR supplied locally. */
public final class LegacyUpgradeIntegrationSmoke {
    private LegacyUpgradeIntegrationSmoke() {
    }

    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 4) {
            throw new IllegalArgumentException(
                    "Expected <legacy-jar> <current-jar> <test-classes> <legacy-entrypoint-class>");
        }
        Path legacyJar = Path.of(arguments[0]).toAbsolutePath().normalize();
        Path currentJar = Path.of(arguments[1]).toAbsolutePath().normalize();
        Path testClasses = Path.of(arguments[2]).toAbsolutePath().normalize();
        String legacyEntrypoint = arguments[3];
        if (!Files.isRegularFile(legacyJar) || !Files.isRegularFile(currentJar)
                || !Files.isDirectory(testClasses)) {
            throw new IllegalArgumentException("Legacy upgrade smoke input is missing");
        }

        Path root = Files.createTempDirectory("modsync-real-legacy-upgrade-");
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            Path mods = Files.createDirectories(root.resolve("mods"));
            Path installedLegacy = mods.resolve(legacyJar.getFileName());
            Files.copy(legacyJar, installedLegacy);
            byte[] oldManagedBytes = "legacy mobile managed mod".getBytes(StandardCharsets.UTF_8);
            Path oldManaged = mods.resolve("old-mobile-managed.jar");
            Files.write(oldManaged, oldManagedBytes);
            Path state = Files.createDirectories(root.resolve(".modsync"));
            Files.writeString(
                    state.resolve("server-manifest.txt"),
                    ModManifest.MAGIC_V2 + "\n"
                            + Hashing.md5(Files.readAllBytes(installedLegacy)) + "\tmcmodsync\t"
                            + installedLegacy.getFileName() + "\n"
                            + Hashing.md5(oldManagedBytes) + "\told_mobile_managed\t"
                            + oldManaged.getFileName() + "\n",
                    StandardCharsets.UTF_8);
            byte[] currentBytes = Files.readAllBytes(currentJar);
            byte[] mergedModBytes = "complete merged catalog mod".getBytes(StandardCharsets.UTF_8);
            String currentName = currentJar.getFileName().toString();
            String legacyManifestUri = "http://127.0.0.1:" + server.getAddress().getPort()
                    + "/legacy-mobile/mods.txt";
            String currentManifestUri = "http://127.0.0.1:" + server.getAddress().getPort()
                    + "/merged/mods-v4.txt";
            Files.writeString(
                    root.resolve("modsync.properties"),
                    "manifest=" + legacyManifestUri + "\n"
                            + "mobileManifest=" + legacyManifestUri + "\n"
                            + "language=en_us\n"
                            + "syncResourcePacks=false\n"
                            + "syncServerList=false\n"
                            + "strict=true\n"
                            + "requireManifest=true\n",
                    StandardCharsets.UTF_8);
            ManagedClientConfig managedConfig = ManagedClientConfig.fromManifestText(
                    "# client-config.manifest=" + currentManifestUri + "\n"
                            + "# client-config.syncResourcePacks=false\n"
                            + "# client-config.syncServerList=false\n"
                            + "# client-config.strict=true\n"
                            + "# client-config.requireManifest=true\n")
                    .orElseThrow();
            Path publication = Files.createDirectories(root.resolve("publication"));
            ManifestEntry bootstrap = ManagedClientConfig.writeBootstrapJar(publication, managedConfig);
            byte[] bootstrapBytes = Files.readAllBytes(
                    publication.resolve(ManagedClientConfig.BOOTSTRAP_FILE_NAME));
            ManifestEntry updater = new ManifestEntry(
                    Hashing.sha256(currentBytes),
                    Hashing.md5(currentBytes),
                    "mcmodsync",
                    currentName,
                    ModKind.REQUIRED,
                    Set.of(),
                    "MCModSync",
                    FabricModMetadata.readVersion(currentJar),
                    "同步器",
                    "Synchronizer");
            ManifestEntry mergedMod = new ManifestEntry(
                    Hashing.sha256(mergedModBytes),
                    Hashing.md5(mergedModBytes),
                    "merged_catalog_mod",
                    "merged-catalog-mod.jar",
                    ModKind.REQUIRED,
                    Set.of(),
                    "Merged Catalog Mod",
                    "1.0",
                    "合并清单测试模组",
                    "Merged catalog test mod");
            ModManifest productionCatalog = ModManifest.fromEntries(
                            "real-legacy-upgrade",
                            List.of(updater, bootstrap, mergedMod))
                    .withManagedClientConfig(managedConfig);
            String transition = LegacyUpgradeManifest.serialize(productionCatalog);
            String production = productionCatalog.serialize();
            long legacyEntryCount = transition.lines()
                    .map(String::strip)
                    .filter(line -> !line.isEmpty() && !line.startsWith("#"))
                    .count();
            if (legacyEntryCount != 2
                    || transition.contains("merged_catalog_mod")) {
                throw new AssertionError("Legacy gateway must contain upgrade components only");
            }

            server.createContext("/legacy-mobile/mods.txt", exchange -> respond(
                    exchange, transition.getBytes(StandardCharsets.UTF_8), "text/plain; charset=utf-8"));
            server.createContext("/merged/mods-v4.txt", exchange -> respond(
                    exchange, production.getBytes(StandardCharsets.UTF_8), "text/plain; charset=utf-8"));
            server.createContext("/legacy-mobile/" + currentName, exchange -> respond(
                    exchange, currentBytes, "application/java-archive"));
            server.createContext("/legacy-mobile/" + ManagedClientConfig.BOOTSTRAP_FILE_NAME, exchange -> respond(
                    exchange, bootstrapBytes, "application/java-archive"));
            server.createContext("/merged/" + currentName, exchange -> respond(
                    exchange, currentBytes, "application/java-archive"));
            server.createContext("/merged/" + ManagedClientConfig.BOOTSTRAP_FILE_NAME, exchange -> respond(
                    exchange, bootstrapBytes, "application/java-archive"));
            server.createContext("/merged/" + mergedMod.fileName(), exchange -> respond(
                    exchange, mergedModBytes, "application/java-archive"));
            server.start();

            Path processLog = root.resolve("legacy-process.log");
            Process process = new ProcessBuilder(
                    javaExecutable().toString(),
                    "-Dfile.encoding=UTF-8",
                    "-Dmodsync.disableDialogs=true",
                    "-Dmodsync.forceMobile=true",
                    "-Dmodsync.forceDesktopHelper=true",
                    "-Dmodsync.manifest=" + legacyManifestUri,
                    "-Dmodsync.syncResourcePacks=false",
                    "-Dmodsync.syncServerList=false",
                    "-Dlegacy.gameDir=" + root,
                    "-cp",
                    legacyJar + System.getProperty("path.separator") + testClasses,
                    LegacyFabricInvoker.class.getName(),
                    legacyEntrypoint)
                    .redirectErrorStream(true)
                    .redirectOutput(processLog.toFile())
                    .start();
            if (!process.waitFor(Duration.ofSeconds(30).toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS)) {
                process.destroyForcibly();
                throw new AssertionError("Historical preLaunch process timed out");
            }
            String launchLog = readLog(processLog);
            if (process.exitValue() != 0 || !launchLog.contains("RESTART_REQUIRED")
                    || launchLog.contains("LEGACY_GAME_MAIN_WOULD_CONTINUE")) {
                throw new AssertionError("Historical preLaunch did not block normally:\n" + launchLog);
            }

            Path installedCurrent = mods.resolve(currentName);
            Path installedBootstrap = mods.resolve(ManagedClientConfig.BOOTSTRAP_FILE_NAME);
            long deadline = System.nanoTime() + Duration.ofSeconds(45).toNanos();
            boolean upgraded = false;
            while (System.nanoTime() < deadline) {
                if (Files.isRegularFile(installedCurrent)
                        && Hashing.sha256(installedCurrent).equals(Hashing.sha256(currentBytes))
                        && Files.isRegularFile(installedBootstrap)
                        && Hashing.sha256(installedBootstrap).equals(Hashing.sha256(bootstrapBytes))
                        && !Files.exists(installedLegacy)
                        && !Files.exists(oldManaged)
                        && backupContains(root, oldManaged.getFileName().toString())) {
                    upgraded = true;
                    break;
                }
                Thread.sleep(200);
            }
            if (upgraded) {
                Path helperLog = root.resolve(".modsync").resolve("helper.log");
                long helperDeadline = System.nanoTime() + Duration.ofSeconds(10).toNanos();
                while (System.nanoTime() < helperDeadline) {
                    if (Files.isRegularFile(helperLog)
                            && (readLog(helperLog).contains("退出后更新完成")
                                    || readLog(helperLog).contains("UPDATE_FAILED"))) {
                        break;
                    }
                    Thread.sleep(100);
                }
                Path currentProcessLog = root.resolve("current-sync-process.log");
                Process currentProcess = new ProcessBuilder(
                        javaExecutable().toString(),
                        "-Dfile.encoding=UTF-8",
                        "-Dmodsync.disableDialogs=true",
                        "-Dmodsync.forceDesktopHelper=true",
                        "-Dlegacy.gameDir=" + root,
                        "-cp",
                        installedCurrent + System.getProperty("path.separator") + testClasses,
                        LegacyFabricInvoker.class.getName(),
                        "io.github.mcmodsync.FabricPreLaunchEntrypoint")
                        .redirectErrorStream(true)
                        .redirectOutput(currentProcessLog.toFile())
                        .start();
                if (!currentProcess.waitFor(
                        Duration.ofSeconds(30).toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS)) {
                    currentProcess.destroyForcibly();
                    throw new AssertionError("Upgraded MCModSync process timed out");
                }
                String currentLog = readLog(currentProcessLog);
                if (currentProcess.exitValue() != 0
                        || !currentLog.contains("RESTART_REQUIRED")
                        || currentLog.contains("LEGACY_GAME_MAIN_WOULD_CONTINUE")
                        || currentLog.contains("STARTUP_BLOCKED")) {
                    throw new AssertionError("Upgraded client did not synchronize the merged mods-v4.txt:\n"
                            + currentLog);
                }
                java.util.Properties installedConfig = new java.util.Properties();
                try (var input = Files.newInputStream(root.resolve("modsync.properties"))) {
                    installedConfig.load(input);
                }
                if (!currentManifestUri.equals(installedConfig.getProperty("manifest"))
                        || installedConfig.containsKey("mobileManifest")
                        || !"en_us".equals(installedConfig.getProperty("language"))) {
                    throw new AssertionError(
                            "Bootstrap did not configure a single merged mods-v4.txt: " + installedConfig);
                }

                Path installedMergedMod = mods.resolve(mergedMod.fileName());
                long mergedDeadline = System.nanoTime() + Duration.ofSeconds(45).toNanos();
                boolean mergedInstalled = false;
                while (System.nanoTime() < mergedDeadline) {
                    if (Files.isRegularFile(installedMergedMod)
                            && Hashing.sha256(installedMergedMod).equals(Hashing.sha256(mergedModBytes))) {
                        String savedHistory = Files.isRegularFile(state.resolve("server-manifest.txt"))
                                ? Files.readString(state.resolve("server-manifest.txt"), StandardCharsets.UTF_8)
                                : "";
                        if (savedHistory.contains("merged_catalog_mod")) {
                            mergedInstalled = true;
                            break;
                        }
                    }
                    Thread.sleep(200);
                }
                if (!mergedInstalled) {
                    throw new AssertionError("Current helper did not restore the complete merged catalog:\n"
                            + (Files.isRegularFile(helperLog) ? readLog(helperLog) : "<missing helper.log>"));
                }

                Path finalProcessLog = root.resolve("current-final-process.log");
                Process finalProcess = new ProcessBuilder(
                        javaExecutable().toString(),
                        "-Dfile.encoding=UTF-8",
                        "-Dmodsync.disableDialogs=true",
                        "-Dmodsync.forceDesktopHelper=true",
                        "-Dlegacy.gameDir=" + root,
                        "-cp",
                        installedCurrent + System.getProperty("path.separator") + testClasses,
                        LegacyFabricInvoker.class.getName(),
                        "io.github.mcmodsync.FabricPreLaunchEntrypoint")
                        .redirectErrorStream(true)
                        .redirectOutput(finalProcessLog.toFile())
                        .start();
                if (!finalProcess.waitFor(
                        Duration.ofSeconds(30).toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS)) {
                    finalProcess.destroyForcibly();
                    throw new AssertionError("Final upgraded MCModSync process timed out");
                }
                String finalLog = readLog(finalProcessLog);
                if (finalProcess.exitValue() != 0
                        || !finalLog.contains("LEGACY_GAME_MAIN_WOULD_CONTINUE")
                        || finalLog.contains("STARTUP_BLOCKED")
                        || finalLog.contains("RESTART_REQUIRED")) {
                    throw new AssertionError("Complete merged catalog did not allow startup:\n" + finalLog);
                }
                System.out.println("Real legacy mobile migration passed: "
                        + legacyJar.getFileName() + " -> upgrade-only mods.txt -> "
                        + currentName + " -> merged mods-v4.txt");
                return;
            }
            Path helperLog = root.resolve(".modsync").resolve("helper.log");
            String helper = Files.isRegularFile(helperLog)
                    ? readLog(helperLog)
                    : "<missing helper.log>";
            throw new AssertionError("Historical helper did not install the current JAR.\nLaunch:\n"
                    + launchLog + "\nHelper:\n" + helper);
        } finally {
            server.stop(0);
            deleteTree(root);
        }
    }

    private static boolean backupContains(Path root, String fileName) throws IOException {
        Path backups = root.resolve(".modsync").resolve("backups");
        if (!Files.isDirectory(backups)) {
            return false;
        }
        try (var paths = Files.walk(backups)) {
            return paths.anyMatch(path -> Files.isRegularFile(path)
                    && path.getFileName().toString().equals(fileName));
        }
    }

    private static void respond(HttpExchange exchange, byte[] body, String contentType) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", contentType);
        exchange.getResponseHeaders().set("Content-Length", Integer.toString(body.length));
        if (exchange.getRequestMethod().equalsIgnoreCase("HEAD")) {
            exchange.sendResponseHeaders(200, -1);
        } else {
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
        }
        exchange.close();
    }

    private static Path javaExecutable() {
        String executable = System.getProperty("os.name", "").toLowerCase().contains("win")
                ? "java.exe"
                : "java";
        return Path.of(System.getProperty("java.home"), "bin", executable).toAbsolutePath().normalize();
    }

    private static String readLog(Path path) throws IOException {
        // Historical Windows builds may emit a mixture of the active code page and UTF-8.
        // This constructor replaces malformed input instead of failing the compatibility test.
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }

    private static void deleteTree(Path root) {
        if (root == null || !Files.exists(root)) {
            return;
        }
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ignored) {
                }
            }
        } catch (IOException ignored) {
        }
    }
}
