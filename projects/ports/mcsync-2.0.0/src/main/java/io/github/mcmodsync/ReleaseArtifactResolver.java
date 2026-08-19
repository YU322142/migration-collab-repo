package io.github.mcmodsync;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

/** Resolves pinned v5 sources into hash-checked bytes; mirrors are transport candidates only. */
final class ReleaseArtifactResolver implements ReleaseTransactionEngine.ArtifactProvider {
    private final ModSyncConfig config;
    private final HttpClient client;
    private final Consumer<String> logger;
    private final SyncObserver observer;
    private final AtomicInteger completedFiles = new AtomicInteger();
    private int totalFiles = 1;

    ReleaseArtifactResolver(ModSyncConfig config, Consumer<String> logger) {
        this(config, logger, SyncObserver.NONE);
    }

    ReleaseArtifactResolver(ModSyncConfig config, Consumer<String> logger, SyncObserver observer) {
        this.config = config;
        this.logger = logger;
        this.observer = observer;
        this.client = RequiredManifestFetcher.createClient(config.connectTimeout());
    }

    void setTotalFiles(int totalFiles) {
        this.totalFiles = Math.max(totalFiles, 1);
        completedFiles.set(0);
    }

    void prefetch(List<ReleaseManifestV5.FileEntry> entries) throws IOException, InterruptedException {
        setTotalFiles(entries.size());
        ParallelDownloadRunner.run(entries.size(), index -> fetch(entries.get(index)));
    }

    byte[] readCached(ReleaseManifestV5.FileEntry entry) throws IOException {
        Path cached = cachePath(entry);
        if (!Files.isRegularFile(cached) || Files.size(cached) != entry.size()
                || !Hashing.sha256(cached).equals(entry.sha256())) {
            throw new IOException("预下载缓存缺失或已损坏: " + entry.path());
        }
        return Files.readAllBytes(cached);
    }

    @Override
    public byte[] fetch(ReleaseManifestV5.FileEntry entry) throws IOException, InterruptedException {
        Path cached = cachePath(entry);
        if (Files.isRegularFile(cached) && Files.size(cached) == entry.size()
                && Hashing.sha256(cached).equals(entry.sha256())) {
            byte[] bytes = Files.readAllBytes(cached);
            reportCompleted(entry, bytes.length);
            return bytes;
        }
        Files.deleteIfExists(cached);
        List<URI> candidates = resolveCandidates(entry);
        IOException last = null;
        for (URI candidate : candidates) {
            try {
                byte[] bytes = RequiredManifestFetcher.fetch(
                        client,
                        candidate,
                        config.requestTimeout(),
                        Math.min(config.maxFileBytes(), Math.max(entry.size(), 1L)),
                        BuildInfo.USER_AGENT,
                        "MCSync file " + entry.path(),
                        logger);
                if (bytes.length != entry.size() || !Hashing.sha256(bytes).equals(entry.sha256())) {
                    throw new IOException("候选源返回的文件与清单锁定哈希不一致");
                }
                storeCache(cached, bytes);
                reportCompleted(entry, bytes.length);
                return bytes;
            } catch (IOException failure) {
                last = failure;
                logger.accept("MCSync 下载候选失败，正在尝试下一来源: " + candidate + " — " + failure.getMessage());
            }
        }
        throw new IOException("所有下载候选均失败: " + entry.path(), last);
    }

    private void reportCompleted(ReleaseManifestV5.FileEntry entry, long bytes) {
        int completed = completedFiles.incrementAndGet();
        observer.downloadProgress(new SyncObserver.DownloadProgress(
                entry.path(), completed, totalFiles, bytes, bytes,
                completed, totalFiles, completed * 1000 / totalFiles));
    }

    private Path cachePath(ReleaseManifestV5.FileEntry entry) throws IOException {
        Path directory = config.gameDirectory().resolve(".modsync").resolve("cache-v5");
        Files.createDirectories(directory);
        return directory.resolve(entry.sha256() + ".bin");
    }

    private static void storeCache(Path target, byte[] bytes) throws IOException {
        Path temporary = Files.createTempFile(target.getParent(), ".download-", ".part");
        Files.write(temporary, bytes);
        try {
            Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException failure) {
            Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private List<URI> resolveCandidates(ReleaseManifestV5.FileEntry entry)
            throws IOException, InterruptedException {
        ReleaseManifestV5.DownloadSource source = entry.download();
        ArrayList<URI> result = new ArrayList<>();
        source.endpoints().stream()
                .filter(endpoint -> endpoint.purpose().equals("file"))
                .sorted(Comparator.comparingInt(ReleaseManifestV5.DownloadEndpoint::priority))
                .map(ReleaseManifestV5.DownloadEndpoint::uri)
                .forEach(result::add);
        switch (source.type()) {
            case "publisher-hosted" -> {
                if (result.isEmpty()) result.add(resolvePublisherPath(entry.path()));
            }
            case "direct" -> {
                // Explicit file endpoints above are the complete candidate set.
            }
            case "modrinth" -> result.addAll(resolveModrinth(source));
            case "curseforge" -> {
                if (result.isEmpty()) {
                    throw new IOException("CurseForge 文件必须由发布器解析成固定 file URL；客户端不携带 API key");
                }
            }
            case "manual" -> throw new IOException("manual 文件不参与自动下载");
            default -> throw new IOException("未知下载源: " + source.type());
        }
        return result.stream().distinct().toList();
    }

    private List<URI> resolveModrinth(ReleaseManifestV5.DownloadSource source)
            throws IOException, InterruptedException {
        List<ReleaseManifestV5.DownloadEndpoint> apiEndpoints = source.endpoints().stream()
                .filter(endpoint -> endpoint.purpose().equals("api"))
                .sorted(Comparator.comparingInt(ReleaseManifestV5.DownloadEndpoint::priority))
                .toList();
        ArrayList<URI> result = new ArrayList<>();
        IOException last = null;
        for (ReleaseManifestV5.DownloadEndpoint endpoint : apiEndpoints) {
            URI metadataUri = endpoint.uri().resolve("version/" + Rfc3986.encodePathSegment(source.versionId()));
            try {
                byte[] response = RequiredManifestFetcher.fetch(
                        client, metadataUri, config.requestTimeout(), 2 * 1024 * 1024L,
                        BuildInfo.USER_AGENT, "Modrinth pinned version metadata", logger);
                Map<String, Object> metadata = object(StrictJson.parse(new String(response, java.nio.charset.StandardCharsets.UTF_8)));
                if (!source.projectId().equals(metadata.get("project_id"))) {
                    throw new IOException("Modrinth version 不属于清单锁定 projectId");
                }
                Object files = metadata.get("files");
                if (!(files instanceof List<?> list)) throw new IOException("Modrinth metadata 缺少 files");
                for (Object raw : list) {
                    Map<String, Object> file = object(raw);
                    Object url = file.get("url");
                    Object hashesRaw = file.get("hashes");
                    if (!(url instanceof String text) || !(hashesRaw instanceof Map<?, ?> hashes)
                            || !(hashes.get("sha256") instanceof String)) continue;
                    URI uri = URI.create(text);
                    if (!uri.isAbsolute() || !uri.getScheme().equalsIgnoreCase("https")) continue;
                    result.add(uri);
                }
            } catch (IOException failure) {
                last = failure;
            }
        }
        if (result.isEmpty()) throw new IOException("无法解析锁定的 Modrinth versionId", last);
        return result;
    }

    private URI resolvePublisherPath(String path) {
        String encoded = String.join("/", java.util.Arrays.stream(path.split("/"))
                .map(Rfc3986::encodePathSegment).toList());
        return config.manifestUri().resolve("./" + encoded);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) throws IOException {
        if (!(value instanceof Map<?, ?> map)) throw new IOException("平台 API 返回值不是 JSON 对象");
        return (Map<String, Object>) map;
    }
}
