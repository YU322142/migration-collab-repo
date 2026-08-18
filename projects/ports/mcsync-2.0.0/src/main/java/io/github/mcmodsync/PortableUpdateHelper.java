package io.github.mcmodsync;

import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.FileTime;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import java.util.jar.Attributes;
import java.util.jar.JarFile;

/**
 * Runs the mutating transaction after the loader JVM has fully exited. This
 * avoids Windows locks held by Fabric/NeoForge cached JAR file systems.
 */
public final class PortableUpdateHelper {
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");
    private static final Duration HELPER_COPY_RETENTION = Duration.ofHours(24);
    private static final Duration HELPER_START_TIMEOUT = Duration.ofSeconds(10);
    private static final String HELPER_RUNTIME_DIRECTORY = "helper-runtime-v2";
    static final String INTERNAL_LAUNCH_ARGUMENT = "--internal-portable-helper";
    private static final String HELPER_READY_PROPERTY = "modsync.helperReadyFile";
    private static final String HELPER_MAIN_CLASS_ENTRY =
            "io/github/mcmodsync/PortableUpdateHelper.class";
    private static final String PUBLISHER_MAIN_CLASS_ENTRY =
            "io/github/mcmodsync/PublisherMain.class";
    private static volatile DisplayLanguage language = DisplayLanguage.detect(null);

    private PortableUpdateHelper() {
    }

    public static void main(String[] arguments) {
        System.setProperty("modsync.helperProcess", "true");
        try {
            HelperArguments parsed = HelperArguments.parse(arguments);
            System.setProperty("modsync.gameDir", parsed.config().gameDirectory().toString());
            language = DisplayLanguage.detect(parsed.config().gameDirectory());
            signalReady();
            log("更新辅助进程已完成主类加载，PID=" + ProcessHandle.current().pid(),
                    "Update helper loaded successfully, PID=" + ProcessHandle.current().pid());
            RuntimeEnvironment environment = RuntimeEnvironment.detect();
            if (environment.mobile() || !environment.dialogsUsable()) {
                log("运行环境: " + environment.summaryLine(),
                        "Runtime environment: " + environment.summaryLine());
                log("图形更新窗口: 不可用，改用日志与 .modsync/ui-status.txt / progress.log",
                        "Update GUI: unavailable; using logs plus .modsync/ui-status.txt / progress.log");
                if (environment.mobile()) {
                    log("已识别为手机端/移动启动器环境，下载进度将写入启动器日志",
                            "Mobile/portable launcher detected; download progress will be written to launcher logs");
                }
            } else {
                log("图形更新窗口: 可用，已请求显示并置顶",
                        "Update GUI: available; requested display and topmost placement");
            }
            UserNotifier notifier = new UserNotifier(true, parsed.config().gameDirectory());
            notifier.showWaitingForGameExit(parsed.parentPid());
            waitForParent(parsed.parentPid());
            notifier.phaseChanged("游戏进程已退出，正在读取云端清单……");
            runNow(parsed.config(), PortableUpdateHelper::log, notifier);
            if (!notifier.helperExitScheduled()) {
                System.exit(0);
            }
        } catch (Throwable failure) {
            System.err.println("[MCSync Helper] UPDATE_FAILED");
            failure.printStackTrace(System.err);
            UserNotifier.showFatalError(failure);
            System.exit(1);
        }
    }

    static boolean schedule(ModSyncConfig config, Consumer<String> logger) throws IOException {
        return schedule(config, logger, "Fabric");
    }

    static boolean schedule(ModSyncConfig config, Consumer<String> logger, String loaderName) throws IOException {
        DisplayLanguage language = DisplayLanguage.detect(config.gameDirectory());
        if (Boolean.getBoolean("modsync.disableHelperLaunch")) {
            logger.accept(language.text(
                    "测试模式：已跳过外部更新辅助进程启动",
                    "Test mode: skipped launching the external update helper"));
            return false;
        }

        Path selfJar = locateSelfJar();
        Path javaExecutable = locateJavaExecutable();
        Path stateDirectory = config.gameDirectory().resolve(".modsync");
        Path logPath = stateDirectory.resolve("helper.log");
        Files.createDirectories(logPath.getParent());
        Path helperJar = prepareHelperRuntimeCopy(selfJar, stateDirectory, logger);
        Path readyFile = stateDirectory.resolve(
                "helper-ready-" + ProcessHandle.current().pid() + "-" + System.nanoTime() + ".signal");
        Files.deleteIfExists(readyFile);

        List<String> command = new ArrayList<>();
        command.add(javaExecutable.toString());
        command.add("-Dfile.encoding=UTF-8");
        command.add("-Dsun.stdout.encoding=UTF-8");
        command.add("-Dsun.stderr.encoding=UTF-8");
        command.add("-D" + HELPER_READY_PROPERTY + "=" + readyFile);
        String languageOverride = System.getProperty("modsync.language", "").strip();
        if (!languageOverride.isBlank()) {
            command.add("-Dmodsync.language=" + languageOverride);
        }
        if (System.getProperty("os.name", "").toLowerCase().contains("windows")) {
            command.add("-Djava.awt.headless=false");
        }
        if (Boolean.getBoolean("modsync.disableDialogs")) {
            command.add("-Dmodsync.disableDialogs=true");
        }
        if (Boolean.getBoolean("modsync.forceHeadless")) {
            command.add("-Dmodsync.forceHeadless=true");
        }
        if (Boolean.getBoolean("modsync.forceMobile")) {
            command.add("-Dmodsync.forceMobile=true");
        }
        RuntimeEnvironment parentEnvironment = RuntimeEnvironment.detect();
        if (parentEnvironment.mobile() && !Boolean.getBoolean("modsync.forceMobile")) {
            command.add("-Dmodsync.forceMobile=true");
        }
        if (!parentEnvironment.dialogsUsable() && !Boolean.getBoolean("modsync.disableDialogs")) {
            command.add("-Dmodsync.disableDialogs=true");
        }
        // -jar avoids the Windows class-path parser entirely. In particular,
        // spaces, non-ASCII characters and ';' in an instance path can no
        // longer split or corrupt the helper class path.
        command.add("-jar");
        // Pass only the ASCII-safe file name. Supplying the absolute instance
        // path here still lets the Windows Java launcher reinterpret ';' as a
        // class-path separator, even in -jar mode. The working directory is
        // transferred separately through CreateProcessW and remains Unicode.
        command.add(helperJar.getFileName().toString());
        command.add(INTERNAL_LAUNCH_ARGUMENT);
        command.addAll(HelperArguments.forCurrentProcess(config).serialize());

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(helperJar.getParent().toFile());
        builder.redirectOutput(ProcessBuilder.Redirect.appendTo(logPath.toFile()));
        builder.redirectError(ProcessBuilder.Redirect.appendTo(logPath.toFile()));
        Process process;
        // Keep a live read handle until the child acknowledges that its main
        // class loaded. This also prevents an older MCSync process from
        // deleting the new runtime copy during the launch window on Windows.
        try (JarFile pinned = openVerifiedHelperArchive(helperJar)) {
            process = builder.start();
            logger.accept(language.text(
                    "已创建 " + loaderName + " 更新辅助进程，正在等待主类加载确认，PID=" + process.pid() + "，日志: " + logPath,
                    "Created the " + loaderName + " update-helper process; waiting for main-class readiness, PID="
                            + process.pid() + ", log: " + logPath));
            awaitHelperReadyOrTerminate(process, readyFile, helperJar, logPath, language);
        } finally {
            deleteIfExistsBestEffort(readyFile);
        }
        logger.accept(language.text(
                "更新辅助进程已确认可用，父进程现在可以正常退出，PID=" + process.pid(),
                "Update helper confirmed ready; the parent can now exit normally, PID=" + process.pid()));
        return true;
    }

    private static Path prepareHelperRuntimeCopy(
            Path selfJar,
            Path stateDirectory,
            Consumer<String> logger) throws IOException {
        // A new directory name isolates this launcher from 1.8.5 and older
        // cleanup code, which deleted every JAR in helper-runtime.
        Path helperDirectory = stateDirectory.resolve(HELPER_RUNTIME_DIRECTORY);
        Files.createDirectories(helperDirectory);
        cleanupOldHelperCopies(helperDirectory, logger);

        Path helperJar = helperDirectory.resolve(
                "MCSync-helper-" + ProcessHandle.current().pid() + "-" + System.nanoTime() + ".jar");
        Path partial = helperDirectory.resolve("." + helperJar.getFileName() + ".part");
        try {
            Files.copy(selfJar, partial);
            String sourceMd5 = Hashing.md5(selfJar);
            String copiedMd5 = Hashing.md5(partial);
            String sourceSha256 = Hashing.sha256(selfJar);
            String copiedSha256 = Hashing.sha256(partial);
            if (!sourceMd5.equals(copiedMd5) || !sourceSha256.equals(copiedSha256)) {
                throw new IOException("更新辅助副本 MD5/SHA256 校验失败");
            }
            try (JarFile ignored = openVerifiedHelperArchive(partial)) {
            }
            moveAtomically(partial, helperJar);
            // Windows may preserve the source timestamp even without
            // COPY_ATTRIBUTES. Set it explicitly so age-based cleanup can
            // never classify a brand-new copy as stale.
            Files.setLastModifiedTime(helperJar, FileTime.from(Instant.now()));
            try (JarFile ignored = openVerifiedHelperArchive(helperJar)) {
            }
        } catch (IOException failure) {
            Files.deleteIfExists(partial);
            Files.deleteIfExists(helperJar);
            throw failure;
        } finally {
            Files.deleteIfExists(partial);
        }
        DisplayLanguage language = DisplayLanguage.detect(stateDirectory.getParent());
        logger.accept(language.text(
                "已创建并双哈希校验独立更新辅助副本: " + helperJar
                        + " (" + Files.size(helperJar) + " bytes, SHA256=" + Hashing.sha256(helperJar) + ")",
                "Created and dual-hash-verified an independent update-helper copy: " + helperJar
                        + " (" + Files.size(helperJar) + " bytes, SHA256=" + Hashing.sha256(helperJar) + ")"));
        return helperJar;
    }

    private static JarFile openVerifiedHelperArchive(Path helperJar) throws IOException {
        JarFile archive = new JarFile(helperJar.toFile());
        try {
            if (archive.getEntry(HELPER_MAIN_CLASS_ENTRY) == null) {
                throw new IOException("更新辅助副本缺少主类: " + HELPER_MAIN_CLASS_ENTRY);
            }
            if (archive.getEntry(PUBLISHER_MAIN_CLASS_ENTRY) == null) {
                throw new IOException("更新辅助副本缺少可执行入口: " + PUBLISHER_MAIN_CLASS_ENTRY);
            }
            if (archive.getManifest() == null) {
                throw new IOException("更新辅助副本缺少可执行清单");
            }
            String mainClass = archive.getManifest().getMainAttributes().getValue(Attributes.Name.MAIN_CLASS);
            if (!PublisherMain.class.getName().equals(mainClass)) {
                throw new IOException("更新辅助副本 Main-Class 无效: " + mainClass);
            }
            return archive;
        } catch (IOException | RuntimeException failure) {
            archive.close();
            throw failure;
        }
    }

    private static void awaitHelperReady(
            Process process,
            Path readyFile,
            Path helperJar,
            Path logPath,
            DisplayLanguage language) throws IOException {
        Instant deadline = Instant.now().plus(HELPER_START_TIMEOUT);
        try {
            while (Instant.now().isBefore(deadline)) {
                if (Files.isRegularFile(readyFile)) {
                    String reportedPid = Files.readString(readyFile, StandardCharsets.UTF_8).strip();
                    if (reportedPid.equals(Long.toString(process.pid()))) {
                        return;
                    }
                    throw new IOException(language.text(
                            "更新辅助进程就绪信号 PID 不匹配: ",
                            "Update-helper readiness PID mismatch: ") + reportedPid);
                }
                if (!process.isAlive()) {
                    throw new IOException(language.text(
                            "更新辅助进程在加载主类前提前退出，退出码 ",
                            "Update helper exited before loading its main class, exit code ")
                            + process.exitValue() + language.text("；辅助 JAR: ", "; helper JAR: ") + helperJar
                            + language.text("；日志: ", "; log: ") + logPath);
                }
                Thread.sleep(50L);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
            throw new IOException(language.text(
                    "等待更新辅助进程启动时线程被中断",
                    "Interrupted while waiting for the update helper to start"), exception);
        }
        process.destroyForcibly();
        throw new IOException(language.text(
                "更新辅助进程未在 10 秒内确认主类加载；辅助 JAR: ",
                "Update helper did not confirm main-class loading within 10 seconds; helper JAR: ")
                + helperJar + language.text("；日志: ", "; log: ") + logPath);
    }

    static void awaitHelperReadyOrTerminate(
            Process process,
            Path readyFile,
            Path helperJar,
            Path logPath,
            DisplayLanguage language) throws IOException {
        try {
            awaitHelperReady(process, readyFile, helperJar, logPath, language);
        } catch (IOException | RuntimeException failure) {
            terminateFailedHelper(process);
            throw failure;
        }
    }

    private static void terminateFailedHelper(Process process) {
        if (!process.isAlive()) {
            return;
        }
        process.destroyForcibly();
        try {
            process.waitFor(2, TimeUnit.SECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    private static void signalReady() throws IOException {
        String configured = System.getProperty(HELPER_READY_PROPERTY, "").strip();
        if (configured.isBlank()) {
            return;
        }
        Path readyFile = Path.of(configured).toAbsolutePath().normalize();
        Path parent = readyFile.getParent();
        if (parent == null) {
            throw new IOException("更新辅助进程就绪文件路径无效: " + readyFile);
        }
        Files.createDirectories(parent);
        Path temporary = parent.resolve("." + readyFile.getFileName()
                + "." + ProcessHandle.current().pid() + ".tmp");
        try {
            Files.writeString(
                    temporary,
                    Long.toString(ProcessHandle.current().pid()),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
            moveAtomically(temporary, readyFile);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static void moveAtomically(Path source, Path target) throws IOException {
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(source, target);
        }
    }

    private static void deleteIfExistsBestEffort(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
        }
    }

    static void cleanupOldHelperCopies(Path helperDirectory, Consumer<String> logger) {
        Path stateDirectory = helperDirectory.getParent();
        Path gameDirectory = stateDirectory == null ? null : stateDirectory.getParent();
        DisplayLanguage language = DisplayLanguage.detect(gameDirectory);
        Instant deleteBefore = Instant.now().minus(HELPER_COPY_RETENTION);
        try (var paths = Files.list(helperDirectory)) {
            for (Path path : paths
                    .filter(Files::isRegularFile)
                    .filter(item -> item.getFileName().toString().toLowerCase().endsWith(".jar"))
                    .toList()) {
                try {
                    // Multiple launch attempts can schedule helpers only a few
                    // milliseconds apart. Never touch a recent copy: its JVM
                    // may not have opened the class path yet.
                    if (Files.getLastModifiedTime(path).toInstant().isBefore(deleteBefore)) {
                        Files.deleteIfExists(path);
                    }
                } catch (IOException exception) {
                    logger.accept(language.text(
                            "旧辅助副本暂时仍被占用，将在下次更新时重试清理: " + path.getFileName(),
                            "An old helper copy is still in use; cleanup will retry next update: "
                                    + path.getFileName()));
                }
            }
        } catch (IOException exception) {
            logger.accept(language.text(
                    "无法清理旧辅助副本，将继续创建本次副本: " + exception.getMessage(),
                    "Could not clean old helper copies; continuing with this launch: " + exception.getMessage()));
        }
    }

    static SyncResult runNow(ModSyncConfig config, Consumer<String> logger)
            throws IOException, InterruptedException {
        return runNow(config, logger, new UserNotifier(true, config.gameDirectory()));
    }

    static SyncResult runNow(ModSyncConfig config, Consumer<String> logger, SyncObserver observer)
            throws IOException, InterruptedException {
        DisplayLanguage language = DisplayLanguage.detect(config.gameDirectory());
        InstanceGuard guard = acquireGuardAfterParentExit(config.gameDirectory());
        try (guard) {
            logger.accept(language.text(
                    "游戏进程已退出，开始执行无占用更新",
                    "The game process exited; starting an update without file locks"));
            SyncResult result = ModSyncCoordinator.synchronize(config, logger, observer);
            logger.accept(language.text(
                    "退出后更新完成: " + result.status(),
                    "Post-exit update complete: " + result.status()));
            return result;
        }
    }

    private static void waitForParent(long parentPid) throws IOException, InterruptedException {
        Optional<ProcessHandle> parent = ProcessHandle.of(parentPid);
        if (parent.isEmpty() || !parent.get().isAlive()) {
            return;
        }
        log("等待游戏进程退出，PID=" + parentPid,
                "Waiting for the game process to exit, PID=" + parentPid);
        try {
            parent.get().onExit().get();
        } catch (java.util.concurrent.ExecutionException exception) {
            throw new IOException("等待游戏进程退出失败", exception.getCause());
        }
    }

    private static InstanceGuard acquireGuardAfterParentExit(Path gameDirectory)
            throws IOException, InterruptedException {
        IOException last = null;
        for (int attempt = 1; attempt <= 40; attempt++) {
            try {
                return InstanceGuard.acquire(gameDirectory);
            } catch (IOException exception) {
                last = exception;
                Thread.sleep(250L);
            }
        }
        throw new IOException("游戏进程退出后仍无法取得客户端更新锁", last);
    }

    private static Path locateSelfJar() throws IOException {
        try {
            var codeSource = PortableUpdateHelper.class.getProtectionDomain().getCodeSource();
            if (codeSource != null) {
                Path location = Path.of(codeSource.getLocation().toURI()).toAbsolutePath().normalize();
                if (isJar(location)) {
                    return location;
                }
            }
        } catch (URISyntaxException exception) {
            throw new IOException("MCSync JAR 路径格式无效", exception);
        }

        // Some custom class loaders omit CodeSource. Fall back to either
        // loader's public mod-origin API without introducing compile dependencies.
        try {
            Class<?> loaderClass = Class.forName("net.fabricmc.loader.api.FabricLoader");
            Object loader = loaderClass.getMethod("getInstance").invoke(null);
            Object optional = loaderClass.getMethod("getModContainer", String.class).invoke(loader, "mcmodsync");
            Object container = optional instanceof Optional<?> found ? found.orElse(null) : null;
            if (container != null) {
                Class<?> containerApi = Class.forName("net.fabricmc.loader.api.ModContainer");
                Object origin = containerApi.getMethod("getOrigin").invoke(container);
                Class<?> originApi = Class.forName("net.fabricmc.loader.api.metadata.ModOrigin");
                Object paths = originApi.getMethod("getPaths").invoke(origin);
                if (paths instanceof Iterable<?> iterable) {
                    for (Object item : iterable) {
                        if (item instanceof Path path) {
                            Path normalized = path.toAbsolutePath().normalize();
                            if (isJar(normalized)) {
                                return normalized;
                            }
                        }
                    }
                }
            }
        } catch (ReflectiveOperationException exception) {
            // Try NeoForge's ModList only after Fabric's API is unavailable.
            try {
                Class<?> modListClass = Class.forName("net.neoforged.fml.ModList");
                Object modList = modListClass.getMethod("get").invoke(null);
                Object optional = modListClass.getMethod("getModContainerById", String.class)
                        .invoke(modList, "mcmodsync");
                Object container = optional instanceof Optional<?> found ? found.orElse(null) : null;
                if (container != null) {
                    Class<?> containerApi = Class.forName("net.neoforged.fml.ModContainer");
                    Object modInfo = containerApi.getMethod("getModInfo").invoke(container);
                    Class<?> modInfoApi = Class.forName("net.neoforged.neoforgespi.language.IModInfo");
                    Object owningFile = modInfoApi.getMethod("getOwningFile").invoke(modInfo);
                    Class<?> fileInfoApi = Class.forName("net.neoforged.neoforgespi.language.IModFileInfo");
                    Object modFile = fileInfoApi.getMethod("getFile").invoke(owningFile);
                    Class<?> modFileApi = Class.forName("net.neoforged.neoforgespi.locating.IModFile");
                    Object filePath = modFileApi.getMethod("getFilePath").invoke(modFile);
                    if (filePath instanceof Path path && isJar(path.toAbsolutePath().normalize())) {
                        return path.toAbsolutePath().normalize();
                    }
                }
            } catch (ReflectiveOperationException ignored) {
                // Report the original, more useful loader lookup failure below.
            }
            throw new IOException("无法通过 Fabric/NeoForge Loader 定位 MCSync JAR", exception);
        }
        throw new IOException("无法定位正在运行的 MCSync JAR");
    }

    private static boolean isJar(Path path) {
        return Files.isRegularFile(path)
                && path.getFileName().toString().toLowerCase().endsWith(".jar");
    }

    private static Path locateJavaExecutable() throws IOException {
        String currentCommand = ProcessHandle.current().info().command().orElse("");
        if (!currentCommand.isBlank()) {
            Path current = Path.of(currentCommand).toAbsolutePath().normalize();
            if (Files.isRegularFile(current)) {
                return current;
            }
        }

        boolean windows = System.getProperty("os.name", "").toLowerCase().contains("windows");
        Path fallback = Path.of(
                        System.getProperty("java.home"),
                        "bin",
                        windows ? "javaw.exe" : "java")
                .toAbsolutePath()
                .normalize();
        if (!Files.isRegularFile(fallback)) {
            throw new IOException("找不到用于退出后更新的 Java: " + fallback);
        }
        return fallback;
    }

    private static void log(String message) {
        System.out.println("[MCSync Helper " + TIME.format(LocalDateTime.now()) + "] " + message);
    }

    private static void log(String chinese, String english) {
        log(language.text(chinese, english));
    }

    private record HelperArguments(long parentPid, ModSyncConfig config) {
        private static final int ARGUMENT_COUNT = 14;

        static HelperArguments forCurrentProcess(ModSyncConfig config) {
            return new HelperArguments(ProcessHandle.current().pid(), config);
        }

        List<String> serialize() {
            return List.of(
                    Long.toString(parentPid),
                    config.gameDirectory().toString(),
                    config.manifestUri().toASCIIString(),
                    config.resourcePackManifestUri().toASCIIString(),
                    config.serverListManifestUri().toASCIIString(),
                    Boolean.toString(config.syncResourcePacks()),
                    Boolean.toString(config.syncServerList()),
                    Boolean.toString(config.strict()),
                    Boolean.toString(config.requireManifest()),
                    Long.toString(config.connectTimeout().toMillis()),
                    Long.toString(config.requestTimeout().toMillis()),
                    Long.toString(config.maxManifestBytes()),
                    Long.toString(config.maxFileBytes()),
                    Integer.toString(config.fileOperationRetries()));
        }

        static HelperArguments parse(String[] arguments) {
            if (arguments.length != ARGUMENT_COUNT) {
                throw new IllegalArgumentException("退出后更新参数数量错误: " + arguments.length);
            }
            long parentPid = positiveLong(arguments[0], "parentPid");
            Path gameDirectory = Path.of(arguments[1]).toAbsolutePath().normalize();
            URI manifest = URI.create(arguments[2]);
            URI resourcePackManifest = URI.create(arguments[3]);
            URI serverListManifest = URI.create(arguments[4]);
            boolean syncResourcePacks = strictBoolean(arguments[5], "syncResourcePacks");
            boolean syncServerList = strictBoolean(arguments[6], "syncServerList");
            boolean strict = strictBoolean(arguments[7], "strict");
            boolean requireManifest = strictBoolean(arguments[8], "requireManifest");
            Duration connectTimeout = Duration.ofMillis(positiveLong(arguments[9], "connectTimeout"));
            Duration requestTimeout = Duration.ofMillis(positiveLong(arguments[10], "requestTimeout"));
            long maxManifestBytes = positiveLong(arguments[11], "maxManifestBytes");
            long maxFileBytes = positiveLong(arguments[12], "maxFileBytes");
            long retries = positiveLong(arguments[13], "fileOperationRetries");
            if (retries > Integer.MAX_VALUE) {
                throw new IllegalArgumentException("fileOperationRetries 超出范围");
            }
            return new HelperArguments(
                    parentPid,
                    new ModSyncConfig(
                            manifest,
                            resourcePackManifest,
                            serverListManifest,
                            gameDirectory,
                            gameDirectory,
                            syncResourcePacks,
                            syncServerList,
                            strict,
                            requireManifest,
                            connectTimeout,
                            requestTimeout,
                            maxManifestBytes,
                            maxFileBytes,
                            (int) retries));
        }

        private static long positiveLong(String value, String name) {
            try {
                long parsed = Long.parseLong(value);
                if (parsed <= 0) {
                    throw new IllegalArgumentException(name + " 必须为正整数");
                }
                return parsed;
            } catch (NumberFormatException exception) {
                throw new IllegalArgumentException(name + " 必须为整数", exception);
            }
        }

        private static boolean strictBoolean(String value, String name) {
            if (value.equalsIgnoreCase("true")) {
                return true;
            }
            if (value.equalsIgnoreCase("false")) {
                return false;
            }
            throw new IllegalArgumentException(name + " 必须为 true 或 false");
        }
    }
}
