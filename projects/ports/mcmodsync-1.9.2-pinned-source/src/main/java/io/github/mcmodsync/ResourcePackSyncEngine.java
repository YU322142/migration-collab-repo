package io.github.mcmodsync;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
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
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;

final class ResourcePackSyncEngine {
    private static final DateTimeFormatter BACKUP_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS");

    private final ModSyncConfig config;
    private final Consumer<String> logger;
    private final SyncObserver observer;
    private final HttpClient client;
    private final FileOperations files;
    private final DisplayLanguage language;

    ResourcePackSyncEngine(ModSyncConfig config, Consumer<String> logger) {
        this(config, logger, SyncObserver.NONE);
    }

    ResourcePackSyncEngine(ModSyncConfig config, Consumer<String> logger, SyncObserver observer) {
        this.config = config;
        this.logger = logger;
        this.observer = observer;
        this.language = DisplayLanguage.detect(config.gameDirectory());
        this.client = RequiredManifestFetcher.createClient(config.connectTimeout());
        this.files = new FileOperations(config.fileOperationRetries());
    }

    private void log(String chinese, String english) {
        logger.accept(language.text(chinese, english));
    }

    SyncProbeResult probeWithoutChanges() throws IOException, InterruptedException {
        if (!config.syncResourcePacks()) {
            return new SyncProbeResult(SyncProbeResult.Status.UP_TO_DATE);
        }
        Path resourcePacks = config.gameDirectory().resolve("resourcepacks");
        Path state = config.gameDirectory().resolve(".modsync");
        Files.createDirectories(resourcePacks);
        Files.createDirectories(state);
        ResourcePackManifest history = loadHistory(state);
        IOException localFailure = verifyHistory(history, resourcePacks);

        try (FileChannel channel = FileChannel.open(
                        state.resolve("resourcepack-sync.lock"),
                        StandardOpenOption.CREATE,
                        StandardOpenOption.WRITE);
                FileLock ignored = acquireLock(channel)) {
            ResourcePackManifest desired;
            try {
                desired = downloadManifest();
            } catch (IOException exception) {
                if (localFailure != null) {
                    throw new IOException("服务器管理的本地资源包校验失败，且云端资源包清单不可用，已阻止启动。"
                            + localFailure.getMessage(), exception);
                }
                throw new IOException("无法取得必需的云端资源包清单，已阻止启动", exception);
            }

            for (ResourcePackEntry entry : desired.entries()) {
                Path local = safeTarget(resourcePacks, entry.fileName());
                if (!Files.isRegularFile(local) || !Hashing.md5(local).equals(entry.md5())) {
                    log("检测到需要下载或替换的资源包: " + entry.fileName(),
                            "Detected a resource pack to download or replace: " + entry.fileName());
                    return new SyncProbeResult(SyncProbeResult.Status.CHANGES_REQUIRED);
                }
            }
            if (historyHasRemovedFiles(history, desired, resourcePacks)) {
                return new SyncProbeResult(SyncProbeResult.Status.CHANGES_REQUIRED);
            }
            persistHistory(desired, state);
            log("资源包 MD5 校验一致", "Resource-pack MD5 verification passed");
            return new SyncProbeResult(SyncProbeResult.Status.UP_TO_DATE);
        }
    }

    SyncResult synchronize() throws IOException, InterruptedException {
        if (!config.syncResourcePacks()) {
            return new SyncResult(SyncResult.Status.UNCHANGED, 0, 0, 0);
        }
        Path resourcePacks = config.gameDirectory().resolve("resourcepacks");
        Path state = config.gameDirectory().resolve(".modsync");
        Files.createDirectories(resourcePacks);
        Files.createDirectories(state);
        ResourcePackManifest history = loadHistory(state);
        IOException localFailure = verifyHistory(history, resourcePacks);

        try (FileChannel channel = FileChannel.open(
                        state.resolve("resourcepack-sync.lock"),
                        StandardOpenOption.CREATE,
                        StandardOpenOption.WRITE);
                FileLock ignored = acquireLock(channel)) {
            observer.phaseChanged("正在读取云端资源包 MD5 清单……");
            ResourcePackManifest desired;
            try {
                desired = downloadManifest();
            } catch (IOException exception) {
                if (localFailure != null) {
                    throw new IOException("服务器管理的本地资源包校验失败，且云端资源包清单不可用，已阻止启动。"
                            + localFailure.getMessage(), exception);
                }
                throw new IOException("无法取得必需的云端资源包清单，已阻止启动", exception);
            }

            List<PackPlan> downloads = new ArrayList<>();
            int unchanged = 0;
            for (ResourcePackEntry entry : desired.entries()) {
                Path local = safeTarget(resourcePacks, entry.fileName());
                if (Files.exists(local) && !Files.isRegularFile(local)) {
                    throw new IOException("资源包目标被同名目录占用: " + local);
                }
                if (Files.isRegularFile(local) && Hashing.md5(local).equals(entry.md5())) {
                    unchanged++;
                } else {
                    downloads.add(new PackPlan(entry, Files.isRegularFile(local) ? local : null));
                }
            }

            List<Path> removed = removedHistoryFiles(history, desired, resourcePacks);
            if (downloads.isEmpty() && removed.isEmpty()) {
                persistHistory(desired, state);
                log("云端管理的资源包 MD5 一致，共 " + unchanged + " 个；其他本地资源包已保留",
                        "Cloud-managed resource packs match MD5 (" + unchanged
                                + "); other local resource packs were retained");
                return new SyncResult(SyncResult.Status.UNCHANGED, 0, 0, unchanged);
            }

            observer.beforeResourcePackDownload(
                    downloads.stream().map(plan -> plan.entry().fileName()).toList(),
                    removed.stream().map(path -> path.getFileName().toString()).toList());
            observer.phaseChanged("正在获取资源包大小，准备总进度……");
            long totalExpectedBytes = probeTotalBytes(downloads);
            Path staging = state.resolve("resourcepack-staging").resolve(UUID.randomUUID().toString());
            Files.createDirectories(staging);
            try {
                boolean downloadedInParallel = false;
                if (downloads.size() > 1) {
                    Path parallelStaging = staging.resolve("parallel");
                    Files.createDirectories(parallelStaging);
                    DownloadProgressTracker tracker = new DownloadProgressTracker(
                            observer, downloads.size(), totalExpectedBytes);
                    int threads = ParallelDownloadRunner.threadCount(downloads.size());
                    observer.phaseChanged("正在使用 " + threads + " 个线程并行下载并校验资源包……");
                    log("尝试使用 " + threads + " 个线程并行下载 " + downloads.size() + " 个资源包",
                            "Trying " + threads + " threads to download " + downloads.size()
                                    + " resource pack(s) in parallel");
                    try {
                        ParallelDownloadRunner.run(downloads.size(), index -> downloadAndValidatePack(
                                downloads.get(index),
                                parallelStaging,
                                index + 1,
                                downloads.size(),
                                tracker,
                                true));
                        downloadedInParallel = true;
                    } catch (IOException parallelFailure) {
                        log("资源包并行下载失败，将清理暂存内容并回退单线程下载: "
                                        + parallelFailure.getMessage(),
                                "Parallel resource-pack download failed; clearing staging data and retrying with "
                                        + "one thread: " + parallelFailure.getMessage());
                        observer.phaseChanged("资源包并行下载未成功，正在自动回退单线程重新下载……");
                        deleteTreeBestEffort(parallelStaging);
                        downloads.forEach(plan -> plan.staged(null));
                    }
                }

                if (!downloadedInParallel) {
                    Path serialStaging = staging.resolve("single-thread");
                    Files.createDirectories(serialStaging);
                    DownloadProgressTracker tracker = new DownloadProgressTracker(
                            observer, downloads.size(), totalExpectedBytes);
                    for (int index = 0; index < downloads.size(); index++) {
                        downloadAndValidatePack(
                                downloads.get(index),
                                serialStaging,
                                index + 1,
                                downloads.size(),
                                tracker,
                                false);
                    }
                }

                observer.phaseChanged("资源包下载和 MD5 校验完成，正在安全备份并替换……");
                applyTransaction(downloads, removed, resourcePacks, state);
                persistHistory(desired, state);
            } finally {
                deleteTreeBestEffort(staging);
            }
            log("资源包同步完成：下载/替换 " + downloads.size() + " 个，备份移除 "
                            + removed.size() + " 个，未变化 " + unchanged + " 个",
                    "Resource-pack sync complete: downloaded/replaced " + downloads.size() + ", moved "
                            + removed.size() + " to backup, unchanged " + unchanged);
            return new SyncResult(
                    SyncResult.Status.UPDATED,
                    downloads.size(),
                    removed.size(),
                    unchanged);
        }
    }

    private ResourcePackManifest downloadManifest() throws IOException, InterruptedException {
        byte[] bytes = RequiredManifestFetcher.fetch(
                client,
                config.resourcePackManifestUri(),
                config.requestTimeout(),
                config.maxManifestBytes(),
                BuildInfo.USER_AGENT,
                language.text("资源包清单", "Resource-pack catalog"),
                logger);
        try {
            return ResourcePackManifest.parse(new String(bytes, StandardCharsets.UTF_8));
        } catch (IllegalArgumentException exception) {
            throw new IOException("云端 resourcepacks.txt 格式无效: " + exception.getMessage(), exception);
        }
    }

    private long probeTotalBytes(List<PackPlan> downloads) throws InterruptedException {
        long total = 0;
        for (PackPlan plan : downloads) {
            HttpRequest request = HttpRequest.newBuilder(fileUri(plan.entry()))
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
                    return -1;
                }
                total += length;
            } catch (IOException exception) {
                log("无法预取资源包大小，总进度将按文件数量估算: " + exception.getMessage(),
                        "Could not prefetch resource-pack sizes; overall progress will use file count: "
                                + exception.getMessage());
                return -1;
            }
        }
        return total > 0 ? total : -1;
    }

    private long download(
            ResourcePackEntry entry,
            Path output,
            int fileIndex,
            DownloadProgressTracker tracker) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(fileUri(entry))
                .timeout(config.requestTimeout())
                .header("User-Agent", BuildInfo.USER_AGENT)
                .GET()
                .build();
        HttpResponse<InputStream> response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
        if (response.statusCode() != 200) {
            closeQuietly(response.body());
            throw new IOException("资源包服务器返回 HTTP " + response.statusCode() + ": " + entry.fileName());
        }
        long declaredLength = response.headers().firstValueAsLong("Content-Length").orElse(-1);
        if (declaredLength > config.maxFileBytes()) {
            closeQuietly(response.body());
            throw new IOException("资源包超过大小限制: " + entry.fileName());
        }

        Files.createDirectories(output.getParent());
        long downloaded = 0;
        tracker.report(entry.fileName(), fileIndex, 0, declaredLength, false);
        byte[] buffer = new byte[128 * 1024];
        try (InputStream input = response.body();
                var stream = Files.newOutputStream(output, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            int read;
            while ((read = input.read(buffer)) >= 0) {
                if (read == 0) {
                    continue;
                }
                downloaded += read;
                if (downloaded > config.maxFileBytes()) {
                    throw new IOException("下载资源包超过大小限制: " + entry.fileName());
                }
                stream.write(buffer, 0, read);
                tracker.report(entry.fileName(), fileIndex, downloaded, declaredLength, false);
            }
        }
        if (declaredLength >= 0 && downloaded != declaredLength) {
            throw new IOException("资源包下载长度不符: " + entry.fileName());
        }
        tracker.report(entry.fileName(), fileIndex, downloaded, declaredLength, true);
        return downloaded;
    }

    private void downloadAndValidatePack(
            PackPlan plan,
            Path stagingDirectory,
            int fileIndex,
            int fileCount,
            DownloadProgressTracker tracker,
            boolean parallel) throws IOException, InterruptedException {
        String prefix = parallel ? "并行下载资源包" : "下载资源包";
        String englishPrefix = parallel ? "Parallel resource-pack download" : "Resource-pack download";
        log(prefix + " [" + fileIndex + "/" + fileCount + "]: " + plan.entry().fileName(),
                englishPrefix + " [" + fileIndex + "/" + fileCount + "]: " + plan.entry().fileName());
        Path staged = stagingDirectory.resolve(plan.entry().fileName() + ".part");
        download(plan.entry(), staged, fileIndex, tracker);
        if (!parallel) {
            observer.phaseChanged("正在校验资源包 MD5：[" + fileIndex + "/" + fileCount + "] "
                    + plan.entry().fileName());
        }
        String actual = Hashing.md5(staged);
        if (!actual.equals(plan.entry().md5())) {
            throw new IOException("下载资源包 MD5 不符: " + plan.entry().fileName()
                    + "，期望 " + plan.entry().md5() + "，实际 " + actual);
        }
        plan.staged(staged);
    }

    private void applyTransaction(
            List<PackPlan> downloads,
            List<Path> removed,
            Path resourcePacks,
            Path state) throws IOException {
        Path backup = state.resolve("backups").resolve("resourcepacks")
                .resolve(BACKUP_TIME.format(LocalDateTime.now()) + "-" + UUID.randomUUID());

        Set<Path> originalFiles = new LinkedHashSet<>();
        for (PackPlan plan : downloads) {
            if (plan.original() != null) {
                originalFiles.add(plan.original());
            }
        }
        originalFiles.addAll(removed);
        Map<Path, Path> moved = new HashMap<>();
        List<Path> installed = new ArrayList<>();
        try {
            if (!originalFiles.isEmpty()) {
                Files.createDirectories(backup);
            }
            for (Path original : originalFiles) {
                Path backupFile = backup.resolve(original.getFileName().toString());
                files.move(original, backupFile, false);
                moved.put(original, backupFile);
            }
            for (PackPlan plan : downloads) {
                Path target = safeTarget(resourcePacks, plan.entry().fileName());
                files.move(plan.staged(), target, false);
                installed.add(target);
            }
        } catch (IOException failure) {
            IOException rollback = null;
            for (int index = installed.size() - 1; index >= 0; index--) {
                try {
                    files.deleteIfExists(installed.get(index));
                } catch (IOException exception) {
                    rollback = combine(rollback, exception);
                }
            }
            for (Map.Entry<Path, Path> entry : moved.entrySet()) {
                try {
                    if (Files.exists(entry.getValue()) && !Files.exists(entry.getKey())) {
                        files.move(entry.getValue(), entry.getKey(), false);
                    }
                } catch (IOException exception) {
                    rollback = combine(rollback, exception);
                }
            }
            if (rollback != null) {
                failure.addSuppressed(rollback);
                throw new IOException("资源包更新失败，且自动回滚不完整；请检查 .modsync/backups/resourcepacks", failure);
            }
            throw new IOException("资源包更新失败，已自动恢复原文件: " + failure.getMessage(), failure);
        }
    }

    private ResourcePackManifest loadHistory(Path state) {
        Path history = state.resolve("resourcepack-manifest.txt");
        if (!Files.isRegularFile(history)) {
            return null;
        }
        try {
            return ResourcePackManifest.parse(Files.readString(history, StandardCharsets.UTF_8));
        } catch (IOException | IllegalArgumentException exception) {
            log("上次资源包清单历史无法读取，将保留未知本地资源包: " + exception.getMessage(),
                    "The previous resource-pack catalog history is unreadable; unknown local resource packs will "
                            + "be retained: " + exception.getMessage());
            return null;
        }
    }

    private IOException verifyHistory(ResourcePackManifest history, Path resourcePacks) {
        if (history == null) {
            return null;
        }
        try {
            for (ResourcePackEntry entry : history.entries()) {
                Path local = safeTarget(resourcePacks, entry.fileName());
                if (!Files.isRegularFile(local)) {
                    throw new IOException("本地资源包缺失: " + entry.fileName());
                }
                String actual = Hashing.md5(local);
                if (!actual.equals(entry.md5())) {
                    throw new IOException("本地资源包 MD5 不符: " + entry.fileName()
                            + "，期望 " + entry.md5() + "，实际 " + actual);
                }
            }
            return null;
        } catch (IOException exception) {
            return exception;
        }
    }

    private boolean historyHasRemovedFiles(
            ResourcePackManifest history,
            ResourcePackManifest desired,
            Path resourcePacks) throws IOException {
        return !removedHistoryFiles(history, desired, resourcePacks).isEmpty();
    }

    private List<Path> removedHistoryFiles(
            ResourcePackManifest history,
            ResourcePackManifest desired,
            Path resourcePacks) throws IOException {
        if (history == null) {
            return List.of();
        }
        Set<String> desiredNames = new LinkedHashSet<>();
        for (ResourcePackEntry entry : desired.entries()) {
            desiredNames.add(entry.fileName().toLowerCase(Locale.ROOT));
        }
        List<Path> removed = new ArrayList<>();
        for (ResourcePackEntry previous : history.entries()) {
            if (!desiredNames.contains(previous.fileName().toLowerCase(Locale.ROOT))) {
                Path local = safeTarget(resourcePacks, previous.fileName());
                if (Files.isRegularFile(local)) {
                    removed.add(local);
                }
            }
        }
        removed.sort(Comparator.comparing(path -> path.getFileName().toString(), String.CASE_INSENSITIVE_ORDER));
        return removed;
    }

    private void persistHistory(ResourcePackManifest manifest, Path state) throws IOException {
        Path history = state.resolve("resourcepack-manifest.txt");
        Path temporary = state.resolve("resourcepack-manifest.txt.tmp-" + UUID.randomUUID());
        manifest.write(temporary);
        try {
            files.move(temporary, history, true);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private URI fileUri(ResourcePackEntry entry) {
        return config.resourcePackManifestUri().resolve("./" + Rfc3986.encodePathSegment(entry.fileName()));
    }

    private static Path safeTarget(Path directory, String fileName) throws IOException {
        Path target = directory.resolve(fileName).normalize();
        if (!directory.toAbsolutePath().normalize().equals(target.toAbsolutePath().normalize().getParent())) {
            throw new IOException("资源包文件名越过目标目录: " + fileName);
        }
        return target;
    }

    private static FileLock acquireLock(FileChannel channel) throws IOException {
        try {
            FileLock lock = channel.tryLock();
            if (lock == null) {
                throw new IOException("另一个进程正在同步资源包");
            }
            return lock;
        } catch (OverlappingFileLockException exception) {
            throw new IOException("另一个线程正在同步资源包", exception);
        }
    }

    private static byte[] readLimited(InputStream input, long maximum) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        long total = 0;
        int read;
        while ((read = input.read(buffer)) >= 0) {
            if (read == 0) {
                continue;
            }
            total += read;
            if (total > maximum) {
                throw new IOException("资源包清单超过大小限制");
            }
            output.write(buffer, 0, read);
        }
        return output.toByteArray();
    }

    private static IOException combine(IOException first, IOException second) {
        if (first == null) {
            return second;
        }
        first.addSuppressed(second);
        return first;
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

    private static final class PackPlan {
        private final ResourcePackEntry entry;
        private final Path original;
        private Path staged;

        private PackPlan(ResourcePackEntry entry, Path original) {
            this.entry = entry;
            this.original = original;
        }

        ResourcePackEntry entry() {
            return entry;
        }

        Path original() {
            return original;
        }

        Path staged() {
            return staged;
        }

        void staged(Path staged) {
            this.staged = staged;
        }
    }
}
