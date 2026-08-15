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
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Comparator;
import java.util.UUID;
import java.util.function.Consumer;

final class ServerListSyncEngine {
    private static final DateTimeFormatter BACKUP_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS");
    private static final String MANAGED_STATE_FILE = "server-list-managed-v1.dat";

    private final ModSyncConfig config;
    private final Consumer<String> logger;
    private final SyncObserver observer;
    private final HttpClient client;
    private final FileOperations files;
    private final DisplayLanguage language;

    ServerListSyncEngine(ModSyncConfig config, Consumer<String> logger) {
        this(config, logger, SyncObserver.NONE);
    }

    ServerListSyncEngine(ModSyncConfig config, Consumer<String> logger, SyncObserver observer) {
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
        if (!config.syncServerList()) {
            return new SyncProbeResult(SyncProbeResult.Status.UP_TO_DATE);
        }
        Path state = config.gameDirectory().resolve(".modsync");
        Path local = config.gameDirectory().resolve(ServerListManifest.FILE_NAME);
        Files.createDirectories(state);
        try (FileChannel channel = openLock(state); FileLock ignored = acquireLock(channel)) {
            ServerListManifest desired;
            try {
                desired = downloadManifest();
            } catch (IOException exception) {
                throw new IOException("无法取得必需的服务器列表清单，已阻止启动", exception);
            }

            Path cachedCloud = state.resolve("server-list-cloud.dat");
            Path managedState = state.resolve(MANAGED_STATE_FILE);
            if (!isCurrentMergedState(local, cachedCloud, managedState, desired)) {
                log("检测到服务器列表需要下载或合并更新",
                        "Detected a server-list download or merge update");
                return new SyncProbeResult(SyncProbeResult.Status.CHANGES_REQUIRED);
            }
            log("服务器列表云端版本 MD5 一致；玩家本地条目保持不变",
                    "The cloud server-list MD5 matches; local player entries remain unchanged");
            return new SyncProbeResult(SyncProbeResult.Status.UP_TO_DATE);
        }
    }

    SyncResult synchronize() throws IOException, InterruptedException {
        if (!config.syncServerList()) {
            return new SyncResult(SyncResult.Status.UNCHANGED, 0, 0, 0);
        }
        Path game = config.gameDirectory();
        Path state = game.resolve(".modsync");
        Path local = game.resolve(ServerListManifest.FILE_NAME);
        Path cachedCloud = state.resolve("server-list-cloud.dat");
        Path managedState = state.resolve(MANAGED_STATE_FILE);
        Files.createDirectories(state);
        try (FileChannel channel = openLock(state); FileLock ignored = acquireLock(channel)) {
            observer.phaseChanged("正在读取云端服务器列表 MD5 清单……");
            ServerListManifest desired;
            try {
                desired = downloadManifest();
            } catch (IOException exception) {
                throw new IOException("无法取得必需的服务器列表清单，已阻止启动", exception);
            }

            if (isCurrentMergedState(local, cachedCloud, managedState, desired)) {
                log("服务器列表云端 MD5 未变化；保留当前合并列表",
                        "The cloud server-list MD5 is unchanged; retaining the current merged list");
                return new SyncResult(SyncResult.Status.UNCHANGED, 0, 0, 1);
            }

            observer.beforeServerListDownload(ServerListManifest.FILE_NAME);
            boolean hadLocal = Files.isRegularFile(local);
            Path staging = state.resolve("server-list-staging").resolve(UUID.randomUUID().toString());
            Files.createDirectories(staging);
            Path downloaded = staging.resolve("cloud-servers.dat.part");
            Path merged = staging.resolve("merged-servers.dat.part");
            Path nextManagedState = staging.resolve("managed-servers.dat.part");
            try {
                downloadServersDat(downloaded);
                String actual = Hashing.md5(downloaded);
                if (!actual.equals(desired.md5())) {
                    throw new IOException("下载服务器列表 MD5 不符，期望 " + desired.md5() + "，实际 " + actual);
                }
                observer.phaseChanged("服务器列表下载完成，正在解析 NBT 并合并玩家条目……");
                ServerListNbt.Document cloud = ServerListNbt.read(downloaded);
                ServerListNbt.Document current = readLocalServerList(local);
                ServerListNbt.Document managed = readManagedState(managedState);
                ServerListNbt.MergeResult result = ServerListNbt.merge(cloud, current, managed);
                for (ServerListNbt.MergeNotice notice : result.notices()) {
                    log(notice.chinese(), notice.english());
                }
                boolean localChanged = current == null || !ServerListNbt.documentsEqual(current, result.merged());
                if (localChanged) {
                    ServerListNbt.write(merged, result.merged());
                }
                ServerListNbt.write(nextManagedState, result.managedState());

                observer.phaseChanged("服务器列表合并完成，正在保存管理台账并安全更新 servers.dat……");
                installMergedState(
                        local,
                        localChanged ? merged : null,
                        managedState,
                        nextManagedState,
                        state);
                updateCloudCache(downloaded, cachedCloud, state);
                log("服务器列表更新完成；仅已记录的云端条目会更新或删除，玩家条目及其相对顺序已保留",
                        "Server-list update complete; only recorded cloud-managed entries may be updated or removed, "
                                + "and player entries retained their relative order");
                return new SyncResult(
                        SyncResult.Status.UPDATED,
                        1,
                        localChanged && hadLocal ? 1 : 0,
                        0);
            } finally {
                deleteTreeBestEffort(staging);
            }
        }
    }

    private ServerListManifest downloadManifest() throws IOException, InterruptedException {
        byte[] bytes = RequiredManifestFetcher.fetch(
                client,
                config.serverListManifestUri(),
                config.requestTimeout(),
                config.maxManifestBytes(),
                BuildInfo.USER_AGENT,
                language.text("服务器列表清单", "Server-list catalog"),
                logger);
        try {
            return ServerListManifest.parse(new String(bytes, StandardCharsets.UTF_8));
        } catch (IllegalArgumentException exception) {
            throw new IOException("云端 serverlist.txt 格式无效: " + exception.getMessage(), exception);
        }
    }

    private void downloadServersDat(Path output) throws IOException, InterruptedException {
        URI fileUri = config.serverListManifestUri().resolve("./" + ServerListManifest.FILE_NAME);
        HttpRequest request = HttpRequest.newBuilder(fileUri)
                .timeout(config.requestTimeout())
                .header("User-Agent", BuildInfo.USER_AGENT)
                .GET()
                .build();
        HttpResponse<InputStream> response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
        if (response.statusCode() != 200) {
            closeQuietly(response.body());
            throw new IOException("服务器列表下载返回 HTTP " + response.statusCode());
        }
        long declared = response.headers().firstValueAsLong("Content-Length").orElse(-1);
        if (declared > config.maxFileBytes()) {
            closeQuietly(response.body());
            throw new IOException("servers.dat 超过大小限制");
        }
        long downloaded = 0;
        reportProgress(0, declared, false);
        byte[] buffer = new byte[64 * 1024];
        try (InputStream input = response.body();
                var stream = Files.newOutputStream(output, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            int read;
            while ((read = input.read(buffer)) >= 0) {
                if (read == 0) {
                    continue;
                }
                downloaded += read;
                if (downloaded > config.maxFileBytes()) {
                    throw new IOException("servers.dat 下载内容超过大小限制");
                }
                stream.write(buffer, 0, read);
                reportProgress(downloaded, declared, false);
            }
        }
        if (declared >= 0 && downloaded != declared) {
            throw new IOException("servers.dat 下载长度不符");
        }
        reportProgress(downloaded, declared, true);
    }

    private void reportProgress(long downloaded, long total, boolean finished) {
        double fraction = total > 0 ? Math.min(1.0, (double) downloaded / total) : finished ? 1.0 : 0.0;
        int permille = (int) Math.round(fraction * 1000.0);
        observer.downloadProgress(new SyncObserver.DownloadProgress(
                ServerListManifest.FILE_NAME,
                1,
                1,
                downloaded,
                total,
                total > 0 ? downloaded : -1,
                total,
                Math.max(0, Math.min(1000, permille))));
    }

    private ServerListNbt.Document readLocalServerList(Path path) throws IOException {
        if (!Files.isRegularFile(path)) {
            if (Files.exists(path)) {
                throw new IOException("servers.dat 被同名目录或非普通文件占用，无法安全合并: " + path);
            }
            return null;
        }
        try {
            return ServerListNbt.read(path);
        } catch (IOException exception) {
            log("本地 servers.dat 无法解析；为保护玩家服务器，本次不会覆盖该文件: " + exception.getMessage(),
                    "The local servers.dat could not be parsed; it will not be overwritten, protecting player servers: "
                            + exception.getMessage());
            throw new IOException("本地 servers.dat 无法安全解析，已保留原文件并阻止服务器列表同步", exception);
        }
    }

    private ServerListNbt.Document readManagedState(Path path) {
        if (!Files.isRegularFile(path)) {
            if (Files.exists(path)) {
                log("服务器列表管理台账不是普通文件，将进入保守模式且不删除任何既有条目: " + path,
                        "The server-list ownership ledger is not a regular file; conservative mode will not delete "
                                + "any existing entry: " + path);
            }
            return null;
        }
        try {
            ServerListNbt.Document document = ServerListNbt.read(path);
            ServerListNbt.validateManagedState(document);
            return document;
        } catch (IOException exception) {
            log("服务器列表管理台账无法解析，将进入只保留/新增的安全模式: " + exception.getMessage(),
                    "The server-list ownership ledger could not be parsed; safe retain/add-only mode is active: "
                            + exception.getMessage());
            return null;
        }
    }

    private boolean isCurrentMergedState(
            Path local,
            Path cachedCloud,
            Path managedState,
            ServerListManifest desired) throws IOException {
        if (!Files.isRegularFile(local)
                || !Files.isRegularFile(cachedCloud)
                || !Hashing.md5(cachedCloud).equals(desired.md5())) {
            return false;
        }
        try {
            ServerListNbt.Document managed = readManagedState(managedState);
            if (Files.exists(managedState) && managed == null) {
                return false;
            }
            return ServerListNbt.isSynchronized(
                    ServerListNbt.read(cachedCloud),
                    ServerListNbt.read(local),
                    managed);
        } catch (IOException exception) {
            log("本地服务器列表需要重新合并: " + exception.getMessage(),
                    "The local server list must be merged again: " + exception.getMessage());
            return false;
        }
    }

    private void installMergedState(
            Path local,
            Path merged,
            Path managedState,
            Path nextManagedState,
            Path state) throws IOException {
        boolean localChanged = merged != null;
        boolean hadOriginal = localChanged && Files.isRegularFile(local);
        Path backup = state.resolve("backups").resolve("server-list")
                .resolve(BACKUP_TIME.format(LocalDateTime.now()) + "-" + UUID.randomUUID())
                .resolve(ServerListManifest.FILE_NAME);
        if (localChanged && Files.exists(local) && !hadOriginal) {
            throw new IOException("servers.dat 被同名目录或非普通文件占用: " + local);
        }
        if (Files.exists(managedState) && !Files.isRegularFile(managedState)) {
            throw new IOException("服务器列表管理台账被同名目录或非普通文件占用: " + managedState);
        }
        if (hadOriginal) {
            files.move(local, backup, false);
        }
        boolean installedLocal = false;
        try {
            if (localChanged) {
                files.move(merged, local, false);
                installedLocal = true;
            }
            files.move(nextManagedState, managedState, true);
        } catch (IOException failure) {
            IOException rollbackFailure = null;
            if (installedLocal && Files.exists(local)) {
                try {
                    files.deleteIfExists(local);
                } catch (IOException rollback) {
                    rollbackFailure = rollback;
                }
            }
            if (hadOriginal && Files.isRegularFile(backup) && !Files.exists(local)) {
                try {
                    files.move(backup, local, false);
                } catch (IOException rollback) {
                    if (rollbackFailure == null) {
                        rollbackFailure = rollback;
                    } else {
                        rollbackFailure.addSuppressed(rollback);
                    }
                }
            }
            if (rollbackFailure != null) {
                failure.addSuppressed(rollbackFailure);
                throw new IOException("服务器列表或管理台账写入失败且自动回滚不完整，请检查 " + backup, failure);
            }
            throw new IOException("服务器列表或管理台账写入失败，原 servers.dat 已恢复", failure);
        }
    }

    private void updateCloudCache(Path downloaded, Path cachedCloud, Path state) {
        Path temporary = state.resolve("server-list-cloud.dat.tmp-" + UUID.randomUUID());
        try {
            Files.copy(downloaded, temporary, StandardCopyOption.COPY_ATTRIBUTES);
            files.move(temporary, cachedCloud, true);
        } catch (IOException exception) {
            log("服务器列表已更新，但云端版本缓存写入失败；下次启动会安全重试: " + exception.getMessage(),
                    "The server list was updated, but the cloud-version cache could not be written; the next launch "
                            + "will retry safely: " + exception.getMessage());
        } finally {
            try {
                Files.deleteIfExists(temporary);
            } catch (IOException ignored) {
            }
        }
    }

    private static FileChannel openLock(Path state) throws IOException {
        return FileChannel.open(
                state.resolve("server-list-sync.lock"),
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE);
    }

    private static FileLock acquireLock(FileChannel channel) throws IOException {
        try {
            FileLock lock = channel.tryLock();
            if (lock == null) {
                throw new IOException("另一个进程正在同步服务器列表");
            }
            return lock;
        } catch (OverlappingFileLockException exception) {
            throw new IOException("另一个线程正在同步服务器列表", exception);
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
                throw new IOException("服务器列表清单超过大小限制");
            }
            output.write(buffer, 0, read);
        }
        return output.toByteArray();
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
}
