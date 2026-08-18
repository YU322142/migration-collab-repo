package io.github.mcmodsync;

import java.io.IOException;
import java.net.http.HttpClient;
import java.util.Optional;
import java.util.function.Consumer;

/** Detects schema-v5 manifests while leaving every legacy text manifest on the 1.9 path. */
final class V5ReleaseSync {
    record Loaded(ReleaseManifestV5 manifest, byte[] bytes, String sha256) {
        Loaded {
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    private V5ReleaseSync() {
    }

    static Optional<Loaded> load(ModSyncConfig config, Consumer<String> logger)
            throws IOException, InterruptedException {
        HttpClient client = RequiredManifestFetcher.createClient(config.connectTimeout());
        byte[] bytes = RequiredManifestFetcher.fetch(
                client,
                config.manifestUri(),
                config.requestTimeout(),
                Math.max(config.maxManifestBytes(), ReleaseManifestV5.MAX_MANIFEST_BYTES),
                BuildInfo.USER_AGENT,
                "MCSync manifest",
                logger);
        int first = 0;
        while (first < bytes.length && Character.isWhitespace(bytes[first])) first++;
        if (first >= bytes.length || bytes[first] != '{') return Optional.empty();
        ReleaseManifestV5 manifest;
        try {
            manifest = ReleaseManifestV5.parse(bytes);
        } catch (IllegalArgumentException failure) {
            throw new IOException("MCSync v5 清单无效: " + failure.getMessage(), failure);
        }
        if (compareVersions(BuildInfo.VERSION, manifest.minimumMcsyncVersion()) < 0) {
            throw new IOException("该发布要求 MCSync >= " + manifest.minimumMcsyncVersion()
                    + "，当前为 " + BuildInfo.VERSION);
        }
        return Optional.of(new Loaded(manifest, bytes, Hashing.sha256(bytes)));
    }

    static SyncProbeResult probe(ModSyncConfig config, Loaded loaded) throws IOException {
        boolean changes = new ReleaseTransactionEngine(config.gameDirectory(), config.fileOperationRetries())
                .needsApply(loaded.manifest(), loaded.sha256());
        return new SyncProbeResult(changes
                ? SyncProbeResult.Status.CHANGES_REQUIRED
                : SyncProbeResult.Status.UP_TO_DATE);
    }

    static SyncResult synchronize(
            ModSyncConfig config,
            Loaded loaded,
            Consumer<String> logger,
            SyncObserver observer) throws IOException, InterruptedException {
        observer.phaseChanged("正在暂存并校验 MCSync v5 发布事务……");
        ReleaseTransactionEngine.Result result = new ReleaseTransactionEngine(
                config.gameDirectory(), config.fileOperationRetries())
                .apply(loaded.manifest(), loaded.sha256(), new ReleaseArtifactResolver(config, logger));
        if (!result.changed()) return new SyncResult(SyncResult.Status.UNCHANGED, 0, 0, 0);
        return new SyncResult(SyncResult.Status.UPDATED, result.installed(), result.removed(), 0);
    }

    private static int compareVersions(String left, String right) {
        String[] leftParts = left.split("[.-]");
        String[] rightParts = right.split("[.-]");
        int count = Math.max(leftParts.length, rightParts.length);
        for (int index = 0; index < count; index++) {
            int leftValue = index < leftParts.length ? numeric(leftParts[index]) : 0;
            int rightValue = index < rightParts.length ? numeric(rightParts[index]) : 0;
            int compared = Integer.compare(leftValue, rightValue);
            if (compared != 0) return compared;
        }
        return 0;
    }

    private static int numeric(String value) {
        try {
            return Integer.parseInt(value.replaceAll("\\D.*$", ""));
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }
}
