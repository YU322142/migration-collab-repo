package io.github.mcmodsync;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class ModSyncEngine {
    private static final DateTimeFormatter BACKUP_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS");
    private static final Pattern NUMERIC_VERSION = Pattern.compile("(?<!\\d)(\\d+(?:\\.\\d+){1,3})(?!\\d)");

    private final ModSyncConfig config;
    private final HttpClient client;
    private final FileOperations files;
    private final Consumer<String> logger;
    private final SyncObserver observer;
    private final DisplayLanguage language;

    ModSyncEngine(ModSyncConfig config, Consumer<String> logger) {
        this(config, logger, SyncObserver.NONE);
    }

    ModSyncEngine(ModSyncConfig config, Consumer<String> logger, SyncObserver observer) {
        this.config = config;
        this.logger = logger;
        this.observer = observer;
        this.language = DisplayLanguage.detect(config.gameDirectory());
        this.files = new FileOperations(config.fileOperationRetries());
        this.client = RequiredManifestFetcher.createClient(config.connectTimeout());
    }

    private void log(String chinese, String english) {
        logger.accept(language.text(chinese, english));
    }

    /**
     * Checks whether JAR changes are required without moving, replacing or
     * deleting any JAR. This is used after the loader has already opened mod file
     * systems, so the actual transaction can be deferred to a helper process.
     */
    SyncProbeResult probeWithoutJarChanges() throws IOException, InterruptedException {
        Path gameDirectory = config.gameDirectory();
        Path modsDirectory = gameDirectory.resolve("mods");
        Path stateDirectory = gameDirectory.resolve(".modsync");
        Path recoveryMarker = stateDirectory.resolve("RECOVERY_REQUIRED.txt");
        Files.createDirectories(modsDirectory);
        Files.createDirectories(stateDirectory);

        if (Files.exists(recoveryMarker)) {
            throw new IOException("检测到上次同步未能完整回滚。请先按照此文件恢复后再启动: " + recoveryMarker);
        }

        LocalSnapshot localSnapshot = prepareLocalSnapshot(modsDirectory, stateDirectory);
        Path lockPath = stateDirectory.resolve("sync.lock");
        try (FileChannel channel = FileChannel.open(
                        lockPath,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.WRITE);
                FileLock ignored = acquireLock(channel)) {
            String manifestText;
            try {
                manifestText = downloadManifest();
            } catch (IOException exception) {
                if (localSnapshot.status() == LocalSnapshotStatus.INVALID) {
                    throw new IOException(
                            "服务器管理的本地 Mod 校验失败，且云端清单不可用，无法安全修复。已阻止启动。"
                                    + "本地错误: " + localSnapshot.message(),
                            exception);
                }
                throw new IOException("无法取得必需的云端 Mod 清单，已阻止启动", exception);
            }

            ModManifest desiredManifest;
            try {
                desiredManifest = ModManifest.parse(manifestText);
                desiredManifest.ensureUniqueModIds();
            } catch (IllegalArgumentException exception) {
                throw new IOException("云端 Mod 清单格式无效，已阻止启动: " + exception.getMessage(), exception);
            }
            if (desiredManifest.managedClientConfig().isPresent()
                    && desiredManifest.managedClientConfig().get().apply(config.configurationDirectory())) {
                log("服务器管理的 modsync.properties 已更新，需要重新启动后应用",
                        "The server-managed modsync.properties was updated; restart to apply it");
                return new SyncProbeResult(SyncProbeResult.Status.CHANGES_REQUIRED);
            }

            ModManifest previousManifest = loadServerHistory(stateDirectory);
            Map<String, Path> local = listLocalMods(modsDirectory);
            ModManifest fullManifest = desiredManifest;
            RecommendedSelectionStore.Resolution selection = RecommendedSelectionStore.resolve(
                    desiredManifest,
                    gameDirectory,
                    local,
                    config.manifestUri(),
                    RuntimeEnvironment.detect(),
                    observer,
                    logger);
            desiredManifest = selection.effectiveManifest();
            desiredManifest = protectFromSelfDowngrade(desiredManifest, local.values());
            Set<String> excludedNames = new HashSet<>();
            Set<String> excludedIds = new HashSet<>();
            for (ManifestEntry entry : fullManifest.entries()) {
                if (entry.recommended()
                        && selection.excludedRecommendedKeys().contains(entry.selectionKey())) {
                    excludedNames.add(key(entry.fileName()));
                    if (!entry.modId().isBlank()) {
                        excludedIds.add(entry.modId());
                    }
                }
            }
            Map<String, ManifestEntry> desiredByName = new HashMap<>();
            Set<String> desiredIds = new HashSet<>();
            for (ManifestEntry desired : desiredManifest.entries()) {
                desiredByName.put(key(desired.fileName()), desired);
                if (!desired.modId().isEmpty()) {
                    desiredIds.add(desired.modId());
                }
                Path existing = local.get(key(desired.fileName()));
                if (existing == null || !ModManifest.fileMatches(desired, existing)) {
                    log("便携模式检测到需要下载或替换: " + desired.fileName(),
                            "Portable mode detected a required download or replacement: " + desired.fileName());
                    return new SyncProbeResult(SyncProbeResult.Status.CHANGES_REQUIRED);
                }
            }

            Set<String> previousNames = new HashSet<>();
            Set<String> previousIds = new HashSet<>();
            if (previousManifest != null) {
                for (ManifestEntry previous : previousManifest.entries()) {
                    previousNames.add(key(previous.fileName()));
                    if (!previous.modId().isEmpty()) {
                        previousIds.add(previous.modId());
                    }
                }
            }

            for (Map.Entry<String, Path> localEntry : local.entrySet()) {
                if (desiredByName.containsKey(localEntry.getKey())) {
                    continue;
                }
                String localModId = ModMetadata.readModId(localEntry.getValue());
                if (excludedNames.contains(localEntry.getKey()) || excludedIds.contains(localModId)) {
                    log("便携模式检测到需要移出已取消/不兼容的推荐模组: "
                                    + localEntry.getValue().getFileName(),
                            "Portable mode detected a deselected or incompatible recommended mod to move out: "
                                    + localEntry.getValue().getFileName());
                    return new SyncProbeResult(SyncProbeResult.Status.CHANGES_REQUIRED);
                }
                if (localModId.equals("mcmodsync") && !desiredIds.contains("mcmodsync")) {
                    continue;
                }
                if ((!localModId.isEmpty() && desiredIds.contains(localModId))
                        || previousNames.contains(localEntry.getKey())
                        || (!localModId.isEmpty() && previousIds.contains(localModId))) {
                    log("便携模式检测到需要替换或处理的旧 Mod: "
                                    + localEntry.getValue().getFileName(),
                            "Portable mode detected an old mod that must be replaced or handled: "
                                    + localEntry.getValue().getFileName());
                    return new SyncProbeResult(SyncProbeResult.Status.CHANGES_REQUIRED);
                }
            }

            refreshAndVerifyLocalSnapshot(modsDirectory);
            persistServerHistory(desiredManifest, stateDirectory, modsDirectory);
            log("便携模式只读检查完成：云端管理文件无需更改，可继续启动。",
                    "Portable read-only check complete: cloud-managed files need no changes; startup may continue.");
            return new SyncProbeResult(SyncProbeResult.Status.UP_TO_DATE);
        }
    }

    SyncResult synchronize() throws IOException, InterruptedException {
        Path gameDirectory = config.gameDirectory();
        Path modsDirectory = gameDirectory.resolve("mods");
        Path stateDirectory = gameDirectory.resolve(".modsync");
        Path recoveryMarker = stateDirectory.resolve("RECOVERY_REQUIRED.txt");
        Files.createDirectories(modsDirectory);
        Files.createDirectories(stateDirectory);

        if (Files.exists(recoveryMarker)) {
            throw new IOException("检测到上次同步未能完整回滚。请先按照此文件恢复后再启动: " + recoveryMarker);
        }

        LocalSnapshot localSnapshot = prepareLocalSnapshot(modsDirectory, stateDirectory);

        Path lockPath = stateDirectory.resolve("sync.lock");
        try (FileChannel channel = FileChannel.open(
                        lockPath,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.WRITE);
                FileLock ignored = acquireLock(channel)) {
            return synchronizeLocked(modsDirectory, stateDirectory, recoveryMarker, localSnapshot);
        }
    }

    private SyncResult synchronizeLocked(
            Path modsDirectory,
            Path stateDirectory,
            Path recoveryMarker,
            LocalSnapshot localSnapshot)
            throws IOException, InterruptedException {
        log("正在读取云端清单: " + config.manifestUri(),
                "Reading cloud catalog: " + config.manifestUri());
        observer.phaseChanged("正在读取云端清单……");
        String manifestText;
        try {
            manifestText = downloadManifest();
        } catch (IOException exception) {
            if (localSnapshot.status() == LocalSnapshotStatus.INVALID) {
                throw new IOException(
                        "服务器管理的本地 Mod 校验失败，且云端清单不可用，无法安全修复。已阻止启动。"
                                + "本地错误: " + localSnapshot.message(),
                        exception);
            }
            throw new IOException("无法取得必需的云端 Mod 清单，已阻止启动", exception);
        }

        ModManifest manifest;
        try {
            manifest = ModManifest.parse(manifestText);
            manifest.ensureUniqueModIds();
        } catch (IllegalArgumentException exception) {
            throw new IOException("云端 Mod 清单格式无效，已阻止启动: " + exception.getMessage(), exception);
        }
        boolean managedConfigChanged = manifest.managedClientConfig().isPresent()
                && manifest.managedClientConfig().get().apply(config.configurationDirectory());
        if (managedConfigChanged) {
            log("服务器管理的 modsync.properties 已更新；同步完成后需要重新启动",
                    "The server-managed modsync.properties was updated; restart after synchronization");
        }

        ModManifest previousServerManifest = loadServerHistory(stateDirectory);
        Set<String> previouslyManaged = new HashSet<>();
        Set<String> previouslyManagedIds = new HashSet<>();
        Map<String, ManifestEntry> previousByFileName = new HashMap<>();
        if (previousServerManifest != null) {
            for (ManifestEntry entry : previousServerManifest.entries()) {
                previouslyManaged.add(key(entry.fileName()));
                previousByFileName.put(key(entry.fileName()), entry);
                if (!entry.modId().isEmpty()) {
                    previouslyManagedIds.add(entry.modId());
                }
            }
        }

        Map<String, Path> local = listLocalMods(modsDirectory);
        Map<String, String> localModIds = new HashMap<>();
        for (Map.Entry<String, Path> entry : local.entrySet()) {
            localModIds.put(entry.getKey(), ModMetadata.readModId(entry.getValue()));
        }
        Map<String, ManifestEntry> desired = new LinkedHashMap<>();
        Map<String, ManifestEntry> desiredByModId = new HashMap<>();
        List<DownloadPlan> downloads = new ArrayList<>();
        int unchanged = 0;
        ModManifest fullManifest = manifest;
        RecommendedSelectionStore.Resolution selection = RecommendedSelectionStore.resolve(
                fullManifest,
                config.gameDirectory(),
                local,
                config.manifestUri(),
                RuntimeEnvironment.detect(),
                observer,
                logger);
        manifest = selection.effectiveManifest();
        manifest = protectFromSelfDowngrade(manifest, local.values());

        Map<String, ManifestEntry> excludedRecommendedByName = new HashMap<>();
        Map<String, ManifestEntry> excludedRecommendedByModId = new HashMap<>();
        for (ManifestEntry entry : fullManifest.entries()) {
            if (!entry.recommended() || !selection.excludedRecommendedKeys().contains(entry.selectionKey())) {
                continue;
            }
            excludedRecommendedByName.put(key(entry.fileName()), entry);
            if (!entry.modId().isBlank()) {
                excludedRecommendedByModId.put(entry.modId(), entry);
            }
        }

        for (ManifestEntry entry : manifest.entries()) {
            String key = key(entry.fileName());
            desired.put(key, entry);
            if (!entry.modId().isEmpty()) {
                desiredByModId.put(entry.modId(), entry);
            }
            Path existing = local.get(key);
            if (existing != null && ModManifest.fileMatches(entry, existing)) {
                unchanged++;
            } else {
                downloads.add(new DownloadPlan(entry, existing));
            }
        }

        List<Path> versionReplaced = new ArrayList<>();
        List<Path> serverRemoved = new ArrayList<>();
        List<Path> deselectedRecommended = new ArrayList<>();
        List<Path> clientAdded = new ArrayList<>();
        List<Path> unknownWithoutSnapshot = new ArrayList<>();
        for (Map.Entry<String, Path> entry : local.entrySet()) {
            if (!desired.containsKey(entry.getKey())) {
                String modId = localModIds.getOrDefault(entry.getKey(), "");
                ManifestEntry previousEntry = previousByFileName.get(entry.getKey());
                if (modId.isEmpty() && previousEntry != null) {
                    modId = previousEntry.modId();
                }
                if (excludedRecommendedByName.containsKey(entry.getKey())
                        || (!modId.isEmpty() && excludedRecommendedByModId.containsKey(modId))) {
                    deselectedRecommended.add(entry.getValue());
                } else if (!modId.isEmpty() && desiredByModId.containsKey(modId)) {
                    versionReplaced.add(entry.getValue());
                } else if (modId.equals("mcmodsync")) {
                    // Never remove the updater merely because an older cloud
                    // manifest omitted it. It is managed only when the cloud
                    // explicitly contains modId=mcmodsync.
                    clientAdded.add(entry.getValue());
                } else if (previouslyManaged.contains(entry.getKey())
                        || (!modId.isEmpty() && previouslyManagedIds.contains(modId))) {
                    serverRemoved.add(entry.getValue());
                } else {
                    if (localSnapshot.status() == LocalSnapshotStatus.GENERATED_VALID) {
                        unknownWithoutSnapshot.add(entry.getValue());
                    } else {
                        clientAdded.add(entry.getValue());
                    }
                }
            }
        }
        Comparator<Path> fileNameOrder = Comparator.comparing(
                path -> path.getFileName().toString(),
                String.CASE_INSENSITIVE_ORDER);
        versionReplaced.sort(fileNameOrder);
        serverRemoved.sort(fileNameOrder);
        deselectedRecommended.sort(fileNameOrder);
        clientAdded.sort(fileNameOrder);
        unknownWithoutSnapshot.sort(fileNameOrder);

        List<Path> rejectedUnknown = new ArrayList<>();
        for (Path unknown : unknownWithoutSnapshot) {
            SyncObserver.UnknownModDecision decision = observer.decideUnknownClientMod(
                    unknown.getFileName().toString());
            if (decision == SyncObserver.UnknownModDecision.KEEP_CLIENT) {
                clientAdded.add(unknown);
            } else {
                rejectedUnknown.add(unknown);
            }
        }
        clientAdded.sort(fileNameOrder);

        List<Path> extras = new ArrayList<>();
        extras.addAll(versionReplaced);
        extras.addAll(rejectedUnknown);
        extras.addAll(deselectedRecommended);
        List<Path> retainedServerRemoved = new ArrayList<>();
        if (!serverRemoved.isEmpty() && config.strict()) {
            SyncObserver.RemovalDecision decision = observer.decideServerRemoved(
                    serverRemoved.stream().map(path -> path.getFileName().toString()).toList());
            if (decision == SyncObserver.RemovalDecision.BACKUP) {
                extras.addAll(serverRemoved);
            } else {
                retainedServerRemoved.addAll(serverRemoved);
            }
        } else {
            retainedServerRemoved.addAll(serverRemoved);
        }

        if (!clientAdded.isEmpty()) {
            log("检测到 " + clientAdded.size() + " 个用户客户端 Mod，将全部保留。",
                    "Detected " + clientAdded.size() + " user client mod(s); all will be retained.");
        }
        if (!deselectedRecommended.isEmpty()) {
            String names = deselectedRecommended.stream()
                    .map(path -> path.getFileName().toString())
                    .reduce((left, right) -> left + ", " + right)
                    .orElse("");
            log("推荐模组已取消选择或与当前平台不兼容，将自动移出并备份: " + names,
                    "Recommended mods were deselected or are incompatible with this platform; moving to backup: "
                            + names);
        }

        if (downloads.isEmpty() && extras.isEmpty()) {
            refreshAndVerifyLocalSnapshot(modsDirectory);
            persistServerHistory(manifest, stateDirectory, modsDirectory);
            RecommendedSelectionStore.markMobileCompleted(selection);
            log("服务器管理的 Mod 与云端清单一致，共 " + unchanged + " 个文件；客户端 Mod 已保留。",
                    "Server-managed mods match the cloud catalog (" + unchanged
                            + " file(s)); client mods were retained.");
            return new SyncResult(
                    managedConfigChanged ? SyncResult.Status.UPDATED : SyncResult.Status.UNCHANGED,
                    0,
                    0,
                    unchanged);
        }

        int removedByChoice = extras.size() - versionReplaced.size() - rejectedUnknown.size()
                - deselectedRecommended.size();
        log("需要下载 " + downloads.size() + " 个文件，自动替换旧版本 " + versionReplaced.size()
                        + " 个，首次确认非纯客户端 Mod " + rejectedUnknown.size()
                        + " 个，取消/不兼容推荐模组 " + deselectedRecommended.size()
                        + " 个，用户选择移出服务器已移除文件 " + removedByChoice + " 个。",
                "Download " + downloads.size() + " file(s); replace " + versionReplaced.size()
                        + " old version(s); move " + rejectedUnknown.size()
                        + " newly rejected non-client mod(s), " + deselectedRecommended.size()
                        + " deselected/incompatible recommended mod(s), and " + removedByChoice
                        + " server-removed file(s) selected by the user.");
        observer.beforeDownload(
                downloads.stream().map(plan -> plan.entry().fileName()).toList(),
                versionReplaced.stream().map(path -> path.getFileName().toString()).toList(),
                rejectedUnknown.stream().map(path -> path.getFileName().toString()).toList(),
                extras.stream()
                        .filter(path -> !versionReplaced.contains(path) && !rejectedUnknown.contains(path))
                        .map(path -> path.getFileName().toString())
                        .toList(),
                retainedServerRemoved.stream().map(path -> path.getFileName().toString()).toList(),
                clientAdded.stream().map(path -> path.getFileName().toString()).toList());
        observer.phaseChanged("正在获取下载文件大小，准备总进度……");
        DownloadSizePlan sizePlan = probeDownloadSizes(downloads);
        if (sizePlan.totalBytes() > 0) {
            log("总下载大小: " + sizePlan.totalBytes() + " bytes",
                    "Total download size: " + sizePlan.totalBytes() + " bytes");
        } else {
            log("服务器未完整提供文件大小，总进度将按文件数量估算",
                    "The server did not provide every file size; overall progress will use file count");
        }
        observer.phaseChanged("准备下载 " + downloads.size() + " 个 Mod……");
        Path stagingDirectory = stateDirectory.resolve("staging").resolve(UUID.randomUUID().toString());
        Files.createDirectories(stagingDirectory);
        try {
            boolean downloadedInParallel = false;
            if (downloads.size() > 1) {
                Path parallelStaging = stagingDirectory.resolve("parallel");
                Files.createDirectories(parallelStaging);
                DownloadProgressTracker tracker = new DownloadProgressTracker(
                        observer, downloads.size(), sizePlan.totalBytes());
                int threads = ParallelDownloadRunner.threadCount(downloads.size());
                observer.phaseChanged("正在使用 " + threads + " 个线程并行下载并校验 Mod……");
                log("尝试使用 " + threads + " 个线程并行下载 " + downloads.size() + " 个 Mod",
                        "Trying " + threads + " threads to download " + downloads.size() + " mod(s) in parallel");
                try {
                    ParallelDownloadRunner.run(downloads.size(), index -> downloadAndValidateMod(
                            downloads.get(index),
                            parallelStaging,
                            index + 1,
                            downloads.size(),
                            tracker,
                            true));
                    downloadedInParallel = true;
                } catch (IOException parallelFailure) {
                    log("并行下载失败，将清理暂存内容并回退单线程下载: "
                                    + parallelFailure.getMessage(),
                            "Parallel download failed; clearing staging data and retrying with one thread: "
                                    + parallelFailure.getMessage());
                    observer.phaseChanged("并行下载未成功，正在自动回退单线程重新下载……");
                    deleteTreeBestEffort(parallelStaging);
                    downloads.forEach(plan -> plan.stagedFile(null));
                }
            }

            if (!downloadedInParallel) {
                Path serialStaging = stagingDirectory.resolve("single-thread");
                Files.createDirectories(serialStaging);
                DownloadProgressTracker tracker = new DownloadProgressTracker(
                        observer, downloads.size(), sizePlan.totalBytes());
                for (int index = 0; index < downloads.size(); index++) {
                    downloadAndValidateMod(
                            downloads.get(index),
                            serialStaging,
                            index + 1,
                            downloads.size(),
                            tracker,
                            false);
                }
            }

            observer.phaseChanged("下载和校验完成，正在安全备份并替换 Mod……");
            applyTransaction(downloads, extras, modsDirectory, stateDirectory, recoveryMarker);
            observer.phaseChanged("正在生成并校验本地 Mod 清单……");
            refreshAndVerifyLocalSnapshot(modsDirectory);
            persistServerHistory(manifest, stateDirectory, modsDirectory);
            RecommendedSelectionStore.markMobileCompleted(selection);
        } finally {
            deleteTreeBestEffort(stagingDirectory);
        }

        log("同步完成：下载 " + downloads.size() + " 个，备份服务器移除文件 " + extras.size()
                        + " 个，未变化 " + unchanged + " 个。",
                "Synchronization complete: downloaded " + downloads.size() + ", moved " + extras.size()
                        + " file(s) to backup, unchanged " + unchanged + ".");
        observer.afterUpdate(downloads.size(), extras.size(), unchanged);
        return new SyncResult(SyncResult.Status.UPDATED, downloads.size(), extras.size(), unchanged);
    }

    private ModManifest protectFromSelfDowngrade(
            ModManifest manifest,
            Iterable<Path> localFiles) throws IOException {
        LocalSelf newest = newestLocalSync(localFiles);
        if (newest == null) {
            return manifest;
        }
        boolean protectedEntry = false;
        List<ManifestEntry> effective = new ArrayList<>(manifest.entries().size());
        for (ManifestEntry entry : manifest.entries()) {
            if (isOutdatedSelfEntry(entry, newest.version())) {
                effective.add(new ManifestEntry(
                        Hashing.sha256(newest.path()),
                        Hashing.md5(newest.path()),
                        "mcmodsync",
                        newest.path().getFileName().toString(),
                        entry.kind(),
                        entry.incompatiblePlatforms(),
                        entry.displayName(),
                        newest.version(),
                        entry.descriptionZh(),
                        entry.descriptionEn()));
                protectedEntry = true;
                log("忽略云端较旧的 MCSync " + versionIn(entry.fileName())
                                + "；保留本地 " + newest.version() + "，防止同步器降级",
                        "Ignoring older cloud MCSync " + versionIn(entry.fileName())
                                + "; retaining local " + newest.version() + " to prevent a downgrade");
            } else {
                effective.add(entry);
            }
        }
        return protectedEntry ? manifest.withEntries(effective) : manifest;
    }

    private static LocalSelf newestLocalSync(Iterable<Path> localFiles) {
        LocalSelf newest = null;
        for (Path file : localFiles) {
            if (!ModMetadata.readModId(file).equals("mcmodsync")) {
                continue;
            }
            String candidate = ModMetadata.readVersion(file);
            if (candidate.isBlank()) {
                candidate = versionIn(file.getFileName().toString());
            }
            if (!candidate.isBlank()
                    && (newest == null || compareVersions(candidate, newest.version()) > 0)) {
                newest = new LocalSelf(file, candidate);
            }
        }
        return newest;
    }

    private static boolean isOutdatedSelfEntry(ManifestEntry entry, String localVersion) {
        if (!entry.modId().equals("mcmodsync") || localVersion.isBlank()) {
            return false;
        }
        String desiredVersion = versionIn(entry.fileName());
        return !desiredVersion.isBlank() && compareVersions(desiredVersion, localVersion) < 0;
    }

    private static String versionIn(String value) {
        Matcher matcher = NUMERIC_VERSION.matcher(value);
        return matcher.find() ? matcher.group(1) : "";
    }

    private static int compareVersions(String left, String right) {
        int[] leftParts = numericParts(left);
        int[] rightParts = numericParts(right);
        if (leftParts == null || rightParts == null) {
            return 0;
        }
        int length = Math.max(leftParts.length, rightParts.length);
        for (int index = 0; index < length; index++) {
            int leftPart = index < leftParts.length ? leftParts[index] : 0;
            int rightPart = index < rightParts.length ? rightParts[index] : 0;
            int compared = Integer.compare(leftPart, rightPart);
            if (compared != 0) {
                return compared;
            }
        }
        return 0;
    }

    private static int[] numericParts(String value) {
        String version = versionIn(value);
        if (version.isBlank()) {
            return null;
        }
        String[] parts = version.split("\\.");
        int[] result = new int[parts.length];
        try {
            for (int index = 0; index < parts.length; index++) {
                result[index] = Integer.parseInt(parts[index]);
            }
            return result;
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    private record LocalSelf(Path path, String version) {
    }

    private ModManifest loadServerHistory(Path stateDirectory) {
        Path historyPath = stateDirectory.resolve("server-manifest.txt");
        if (!Files.isRegularFile(historyPath)) {
            return null;
        }
        try {
            ModManifest history = ModManifest.parse(Files.readString(historyPath, StandardCharsets.UTF_8));
            history.ensureUniqueModIds();
            return history;
        } catch (IOException | IllegalArgumentException exception) {
            log("警告：上次云端清单历史无法读取。为避免误删，本次将未知额外 Mod 视为客户端 Mod。原因: "
                            + exception.getMessage(),
                    "Warning: the previous cloud-catalog history is unreadable. Unknown extra mods will be treated "
                            + "as client mods to avoid accidental removal. Reason: " + exception.getMessage());
            return null;
        }
    }

    private void persistServerHistory(
            ModManifest manifest,
            Path stateDirectory,
            Path modsDirectory) throws IOException {
        Path historyPath = stateDirectory.resolve("server-manifest.txt");
        if (manifest.entries().isEmpty()) {
            Files.deleteIfExists(historyPath);
            log("当前没有云端管理的已选 Mod；已清除旧的服务器清单历史。",
                    "No selected cloud-managed mods remain; the old server-catalog history was removed.");
            return;
        }
        writeSnapshotAtomically(manifest, historyPath);
        ModManifest saved = ModManifest.parse(Files.readString(historyPath, StandardCharsets.UTF_8));
        saved.verifyManagedFiles(modsDirectory);
        log("本次云端清单历史已保存，用于下次识别服务器移除与客户端自定义 Mod。",
                "Cloud-catalog history was saved for detecting server removals and custom client mods next time.");
    }

    private LocalSnapshot prepareLocalSnapshot(Path modsDirectory, Path stateDirectory) throws IOException {
        Path snapshotPath = modsDirectory.resolve("mods.txt");
        boolean existed = Files.exists(snapshotPath);
        ModManifest serverHistory = loadServerHistory(stateDirectory);
        if (serverHistory != null) {
            try {
                serverHistory.requiredOnly().verifyManagedFiles(modsDirectory);
            } catch (IOException exception) {
                log("警告：服务器管理的本地 Mod 校验失败，将尝试使用云端清单修复。原因: "
                                + exception.getMessage(),
                        "Warning: verification of server-managed local mods failed; the cloud catalog will be used "
                                + "to repair them. Reason: " + exception.getMessage());
                return new LocalSnapshot(LocalSnapshotStatus.INVALID, exception.getMessage());
            }
        }

        try {
            ModManifest generated = ModManifest.scan(modsDirectory);
            writeSnapshotAtomically(generated, snapshotPath);
            ModManifest.parse(Files.readString(snapshotPath, StandardCharsets.UTF_8)).verifySnapshot(modsDirectory);
            if (existed) {
                log("本地 mods.txt 已按当前服务器 Mod 与客户端自定义 Mod 重建，MD5/SHA256 校验通过。",
                        "Local mods.txt was rebuilt from current server and custom client mods; MD5/SHA256 passed.");
                return new LocalSnapshot(LocalSnapshotStatus.EXISTING_VALID, "");
            }
            log("本地 mods.txt 不存在，已自动生成并完成 MD5/SHA256 校验: " + snapshotPath,
                    "Local mods.txt was missing; generated automatically and verified with MD5/SHA256: "
                            + snapshotPath);
            return new LocalSnapshot(LocalSnapshotStatus.GENERATED_VALID, "");
        } catch (IOException exception) {
            if (isModsDirectoryEmpty(modsDirectory)) {
                log("本地 mods 目录为空，将在云端文件下载完成后生成 mods.txt。",
                        "The local mods directory is empty; mods.txt will be generated after cloud files download.");
                return new LocalSnapshot(LocalSnapshotStatus.EMPTY, exception.getMessage());
            }
            throw exception;
        }
    }

    private void refreshAndVerifyLocalSnapshot(Path modsDirectory) throws IOException {
        Path snapshotPath = modsDirectory.resolve("mods.txt");
        if (isModsDirectoryEmpty(modsDirectory)) {
            Files.deleteIfExists(snapshotPath);
            log("最终 mods 目录为空；未生成本地 mods.txt，允许在不选择推荐模组时继续启动。",
                    "The final mods directory is empty; mods.txt was not generated, and startup may continue with "
                            + "no recommended mods selected.");
            return;
        }
        ModManifest snapshot = ModManifest.scan(modsDirectory);
        writeSnapshotAtomically(snapshot, snapshotPath);
        ModManifest.parse(Files.readString(snapshotPath, StandardCharsets.UTF_8)).verifySnapshot(modsDirectory);
        log("本地 mods.txt 已按最终 Mod 组合更新并完成 MD5/SHA256 校验。",
                "Local mods.txt was updated for the final mod set and verified with MD5/SHA256.");
    }

    private void writeSnapshotAtomically(ModManifest manifest, Path snapshotPath) throws IOException {
        Path temporary = snapshotPath.getParent().resolve("."
                + snapshotPath.getFileName() + "." + UUID.randomUUID() + ".tmp");
        try {
            Files.writeString(
                    temporary,
                    manifest.serialize(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
            files.move(temporary, snapshotPath, true);
        } finally {
            try {
                Files.deleteIfExists(temporary);
            } catch (IOException ignored) {
            }
        }
    }

    private static boolean isModsDirectoryEmpty(Path modsDirectory) throws IOException {
        try (var stream = Files.list(modsDirectory)) {
            return stream.noneMatch(path -> Files.isRegularFile(path)
                    && path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".jar"));
        }
    }

    private void applyTransaction(
            List<DownloadPlan> downloads,
            List<Path> extras,
            Path modsDirectory,
            Path stateDirectory,
            Path recoveryMarker) throws IOException {
        String transactionId = UUID.randomUUID().toString();
        Path transactionDirectory = stateDirectory.resolve("transactions").resolve(transactionId);
        Path originalsDirectory = transactionDirectory.resolve("originals");
        Files.createDirectories(originalsDirectory);

        List<MovedOriginal> movedOriginals = new ArrayList<>();
        List<Path> installed = new ArrayList<>();
        Set<String> pathsToMove = new HashSet<>();

        for (DownloadPlan plan : downloads) {
            if (plan.originalFile() != null) {
                pathsToMove.add(key(plan.originalFile().getFileName().toString()));
            }
        }
        for (Path extra : extras) {
            pathsToMove.add(key(extra.getFileName().toString()));
        }

        List<Path> originals = new ArrayList<>();
        for (DownloadPlan plan : downloads) {
            if (plan.originalFile() != null) {
                originals.add(plan.originalFile());
            }
        }
        for (Path extra : extras) {
            if (pathsToMove.contains(key(extra.getFileName().toString()))) {
                originals.add(extra);
            }
        }
        originals = originals.stream().distinct().toList();

        try {
            // 这一步既是占用探测，也是事务开始：全部旧文件先移入同盘临时区。
            for (Path original : originals) {
                Path temporary = originalsDirectory.resolve(original.getFileName().toString());
                files.move(original, temporary, false);
                movedOriginals.add(new MovedOriginal(original, temporary));
            }

            // 只有所有旧文件都可移动后，才安装已完成 MD5/SHA256 校验的新文件。
            for (DownloadPlan plan : downloads) {
                Path target = modsDirectory.resolve(plan.entry().fileName()).normalize();
                ensureDirectChild(modsDirectory, target);
                files.move(plan.stagedFile(), target, false);
                installed.add(target);
            }
        } catch (IOException failure) {
            IOException rollbackFailure = rollback(installed, movedOriginals);
            if (rollbackFailure != null) {
                writeRecoveryMarker(recoveryMarker, failure, rollbackFailure, transactionDirectory);
                failure.addSuppressed(rollbackFailure);
                throw new IOException(
                        "文件被占用或替换失败，且自动回滚未完全成功。已阻止启动，请查看: " + recoveryMarker,
                        failure);
            }
            deleteTreeBestEffort(transactionDirectory);
            throw new IOException("文件被占用或替换失败，已自动恢复原 Mod，未应用本次更新", failure);
        }

        boolean transactionMayBeDeleted = movedOriginals.isEmpty();
        if (!movedOriginals.isEmpty()) {
            Path backupDirectory = uniqueBackupDirectory(stateDirectory);
            try {
                files.move(originalsDirectory, backupDirectory, false);
                log("旧模组已禁用并备份至: " + backupDirectory,
                        "Old mods were disabled and backed up to: " + backupDirectory);
                transactionMayBeDeleted = true;
            } catch (IOException exception) {
                // 当前 Mod 组合已经完整提交；旧文件仍安全保留在事务目录，不阻止游戏启动。
                log("警告：无法整理备份目录，旧文件仍保留在: " + originalsDirectory,
                        "Warning: could not organize the backup directory; old files remain at: "
                                + originalsDirectory);
            }
        }
        if (transactionMayBeDeleted) {
            deleteTreeBestEffort(transactionDirectory);
        }
    }

    private IOException rollback(List<Path> installed, List<MovedOriginal> movedOriginals) {
        IOException combined = null;
        for (int index = installed.size() - 1; index >= 0; index--) {
            try {
                files.deleteIfExists(installed.get(index));
            } catch (IOException exception) {
                combined = combine(combined, exception);
            }
        }
        for (int index = movedOriginals.size() - 1; index >= 0; index--) {
            MovedOriginal moved = movedOriginals.get(index);
            try {
                if (Files.exists(moved.temporary()) && !Files.exists(moved.original())) {
                    files.move(moved.temporary(), moved.original(), false);
                }
            } catch (IOException exception) {
                combined = combine(combined, exception);
            }
        }
        return combined;
    }

    private String downloadManifest() throws IOException, InterruptedException {
        byte[] bytes = RequiredManifestFetcher.fetch(
                client,
                config.manifestUri(),
                config.requestTimeout(),
                config.maxManifestBytes(),
                BuildInfo.USER_AGENT,
                language.text("Mod 清单", "Mod catalog"),
                logger);
        return decodeUtf8Strict(bytes);
    }

    private long downloadMod(
            ManifestEntry entry,
            Path output,
            int fileIndex,
            int fileCount,
            DownloadProgressTracker tracker) throws IOException, InterruptedException {
        URI fileUri = config.manifestUri().resolve("./" + Rfc3986.encodePathSegment(entry.fileName()));
        HttpRequest request = HttpRequest.newBuilder(fileUri)
                .timeout(config.requestTimeout())
                .header("User-Agent", BuildInfo.USER_AGENT)
                .GET()
                .build();
        HttpResponse<InputStream> response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
        if (response.statusCode() != 200) {
            closeQuietly(response.body());
            throw new IOException("下载服务器返回 HTTP " + response.statusCode() + ": " + entry.fileName());
        }

        long declaredLength = response.headers().firstValueAsLong("Content-Length").orElse(-1);
        if (declaredLength > config.maxFileBytes()) {
            closeQuietly(response.body());
            throw new IOException("文件超过大小限制: " + entry.fileName() + " (" + declaredLength + " bytes)");
        }

        Files.createDirectories(output.getParent());
        long total = 0;
        tracker.report(entry.fileName(), fileIndex, 0, declaredLength, false);
        byte[] buffer = new byte[128 * 1024];
        try (InputStream input = response.body();
                var stream = Files.newOutputStream(
                        output,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE)) {
            int read;
            while ((read = input.read(buffer)) >= 0) {
                if (read == 0) {
                    continue;
                }
                total += read;
                if (total > config.maxFileBytes()) {
                    throw new IOException("下载内容超过大小限制: " + entry.fileName());
                }
                stream.write(buffer, 0, read);
                tracker.report(entry.fileName(), fileIndex, total, declaredLength, false);
            }
        }
        if (declaredLength >= 0 && total != declaredLength) {
            throw new IOException("下载长度不符: " + entry.fileName() + "，期望 " + declaredLength + "，实际 " + total);
        }
        tracker.report(entry.fileName(), fileIndex, total, declaredLength, true);
        return total;
    }

    private void downloadAndValidateMod(
            DownloadPlan plan,
            Path stagingDirectory,
            int fileIndex,
            int fileCount,
            DownloadProgressTracker tracker,
            boolean parallel) throws IOException, InterruptedException {
        String prefix = parallel ? "并行下载" : "下载";
        String englishPrefix = parallel ? "Parallel download" : "Download";
        log(prefix + " [" + fileIndex + "/" + fileCount + "]: " + plan.entry().fileName(),
                englishPrefix + " [" + fileIndex + "/" + fileCount + "]: " + plan.entry().fileName());
        Path staged = stagingDirectory.resolve(plan.entry().fileName() + ".part");
        downloadMod(plan.entry(), staged, fileIndex, fileCount, tracker);
        if (!parallel) {
            observer.phaseChanged("正在校验 MD5/SHA256：[" + fileIndex + "/" + fileCount + "] "
                    + plan.entry().fileName());
        }
        String actualMd5 = Hashing.md5(staged);
        if (!actualMd5.equals(plan.entry().md5())) {
            throw new IOException(
                    "下载文件 MD5 不符: " + plan.entry().fileName()
                            + "，期望 " + plan.entry().md5() + "，实际 " + actualMd5);
        }
        if (!plan.entry().sha256().isBlank()) {
            String actualSha256 = Hashing.sha256(staged);
            if (!actualSha256.equals(plan.entry().sha256())) {
                throw new IOException(
                        "下载文件 SHA256 不符: " + plan.entry().fileName()
                                + "，期望 " + plan.entry().sha256() + "，实际 " + actualSha256);
            }
        }
        plan.stagedFile(staged);
    }

    private DownloadSizePlan probeDownloadSizes(List<DownloadPlan> downloads) throws InterruptedException {
        long total = 0;
        for (DownloadPlan plan : downloads) {
            URI fileUri = config.manifestUri().resolve(
                    "./" + Rfc3986.encodePathSegment(plan.entry().fileName()));
            HttpRequest request = HttpRequest.newBuilder(fileUri)
                    .timeout(config.requestTimeout())
                    .header("User-Agent", BuildInfo.USER_AGENT)
                    .method("HEAD", HttpRequest.BodyPublishers.noBody())
                    .build();
            try {
                HttpResponse<Void> response = client.send(request, HttpResponse.BodyHandlers.discarding());
                long length = response.statusCode() == 200
                        ? response.headers().firstValueAsLong("Content-Length").orElse(-1)
                        : -1;
                if (length < 0 || length > config.maxFileBytes() || Long.MAX_VALUE - total < length) {
                    return DownloadSizePlan.UNKNOWN;
                }
                total += length;
            } catch (IOException exception) {
                log("无法预取文件大小，将使用文件数量估算总进度: " + exception.getMessage(),
                        "Could not prefetch file sizes; overall progress will use file count: "
                                + exception.getMessage());
                return DownloadSizePlan.UNKNOWN;
            }
        }
        return total > 0 ? new DownloadSizePlan(total) : DownloadSizePlan.UNKNOWN;
    }

    private static Map<String, Path> listLocalMods(Path modsDirectory) throws IOException {
        Map<String, Path> result = new HashMap<>();
        try (var stream = Files.list(modsDirectory)) {
            for (Path path : stream
                    .filter(Files::isRegularFile)
                    .filter(item -> item.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".jar"))
                    .toList()) {
                String key = key(path.getFileName().toString());
                Path previous = result.putIfAbsent(key, path);
                if (previous != null) {
                    throw new IOException("本地存在仅大小写不同的重复 Mod，无法安全同步: "
                            + previous.getFileName() + " / " + path.getFileName());
                }
            }
        }
        return result;
    }

    private static FileLock acquireLock(FileChannel channel) throws IOException {
        try {
            FileLock lock = channel.tryLock();
            if (lock == null) {
                throw new IOException("另一个 Minecraft 或同步进程正在操作此客户端，请先将其关闭");
            }
            return lock;
        } catch (OverlappingFileLockException exception) {
            throw new IOException("另一个同步线程正在操作此客户端", exception);
        }
    }

    private static byte[] readLimited(InputStream input, long maximum) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[16 * 1024];
        long total = 0;
        int read;
        while ((read = input.read(buffer)) >= 0) {
            if (read == 0) {
                continue;
            }
            total += read;
            if (total > maximum) {
                throw new IOException("响应内容超过安全大小限制 " + maximum + " bytes");
            }
            output.write(buffer, 0, read);
        }
        return output.toByteArray();
    }

    private static String decodeUtf8Strict(byte[] bytes) throws IOException {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException exception) {
            throw new IOException("Mod 清单不是有效的 UTF-8 文本", exception);
        }
    }

    private static Path uniqueBackupDirectory(Path stateDirectory) {
        String timestamp = BACKUP_TIME.format(LocalDateTime.now());
        return stateDirectory.resolve("backups").resolve(timestamp + "-" + UUID.randomUUID().toString().substring(0, 8));
    }

    private static void ensureDirectChild(Path directory, Path child) throws IOException {
        Path normalizedDirectory = directory.toAbsolutePath().normalize();
        Path normalizedChild = child.toAbsolutePath().normalize();
        if (!normalizedDirectory.equals(normalizedChild.getParent())) {
            throw new IOException("拒绝写入 mods 目录以外的路径: " + normalizedChild);
        }
    }

    private static IOException combine(IOException existing, IOException addition) {
        if (existing == null) {
            return addition;
        }
        existing.addSuppressed(addition);
        return existing;
    }

    private static void writeRecoveryMarker(
            Path marker,
            IOException original,
            IOException rollback,
            Path transactionDirectory) {
        String content = "MCSync 自动回滚未完全成功。\n"
                + "为避免加载器加载不完整的 Mod 组合，后续启动已被阻止。\n"
                + "事务文件目录: " + transactionDirectory + "\n"
                + "原始错误: " + original + "\n"
                + "回滚错误: " + rollback + "\n"
                + "请关闭所有 Minecraft/Java 进程，将 originals 中的文件放回 mods 后，再删除本文件。\n";
        try {
            Files.writeString(
                    marker,
                    content,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.TRUNCATE_EXISTING,
                    StandardOpenOption.WRITE);
        } catch (IOException ignored) {
            // 已经没有更可靠的落盘位置；主异常仍会阻止加载器启动。
        }
    }

    private static void closeQuietly(InputStream input) {
        try {
            input.close();
        } catch (IOException ignored) {
        }
    }

    private static void deleteTreeBestEffort(Path root) {
        if (!Files.exists(root)) {
            return;
        }
        try (var stream = Files.walk(root)) {
            for (Path path : stream.sorted(Comparator.reverseOrder()).toList()) {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ignored) {
                }
            }
        } catch (IOException ignored) {
        }
    }

    private static String key(String fileName) {
        return fileName.toLowerCase(Locale.ROOT);
    }

    private record MovedOriginal(Path original, Path temporary) {
    }

    private record DownloadSizePlan(long totalBytes) {
        private static final DownloadSizePlan UNKNOWN = new DownloadSizePlan(-1);
    }

    private static final class DownloadPlan {
        private final ManifestEntry entry;
        private final Path originalFile;
        private Path stagedFile;

        private DownloadPlan(ManifestEntry entry, Path originalFile) {
            this.entry = entry;
            this.originalFile = originalFile;
        }

        ManifestEntry entry() {
            return entry;
        }

        Path originalFile() {
            return originalFile;
        }

        Path stagedFile() {
            return stagedFile;
        }

        void stagedFile(Path stagedFile) {
            this.stagedFile = stagedFile;
        }
    }

    private enum LocalSnapshotStatus {
        GENERATED_VALID,
        EXISTING_VALID,
        EMPTY,
        INVALID
    }

    private record LocalSnapshot(LocalSnapshotStatus status, String message) {
    }
}
