package io.github.mcmodsync;

import java.io.IOException;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.function.Consumer;

final class ModSyncCoordinator {
    private ModSyncCoordinator() {
    }

    static SyncProbeResult probe(ModSyncConfig config, Consumer<String> logger)
            throws IOException, InterruptedException {
        return probe(config, logger, SyncObserver.NONE);
    }

    static SyncProbeResult probe(ModSyncConfig config, Consumer<String> logger, SyncObserver observer)
            throws IOException, InterruptedException {
        Optional<V5ReleaseSync.Loaded> v5 = V5ReleaseSync.load(config, logger);
        if (v5.isPresent()) {
            boolean changed = false;
            for (BakaXLLayout.Target target : BakaXLLayout.syncTargets(config.gameDirectory())) {
                ModSyncConfig targetConfig = config.forGameDirectory(target.gameDirectory());
                changed |= V5ReleaseSync.probe(targetConfig, v5.get(), logger, observer).status()
                        == SyncProbeResult.Status.CHANGES_REQUIRED;
                if (config.syncServerList()) {
                    changed |= new ServerListSyncEngine(targetConfig, logger).probeWithoutChanges().status()
                            == SyncProbeResult.Status.CHANGES_REQUIRED;
                }
            }
            return new SyncProbeResult(changed
                    ? SyncProbeResult.Status.CHANGES_REQUIRED
                    : SyncProbeResult.Status.UP_TO_DATE);
        }
        DisplayLanguage language = DisplayLanguage.detect(config.gameDirectory());
        boolean skippedOffline = false;
        List<BakaXLLayout.Target> targets = BakaXLLayout.syncTargets(config.gameDirectory());
        for (int index = 0; index < targets.size(); index++) {
            BakaXLLayout.Target target = targets.get(index);
            String targetLabel = localizeTargetLabel(target.label(), language);
            logger.accept(language.text("检查同步目标 [", "Checking sync target [")
                    + (index + 1) + "/" + targets.size() + "] "
                    + targetLabel + ": " + target.gameDirectory());
            SyncProbeResult result = new ModSyncEngine(
                    config.forGameDirectory(target.gameDirectory()),
                    prefixedLogger(logger, targetLabel),
                    forwardingObserver(observer, targetLabel + " / Mod", index + 1, targets.size()))
                    .probeWithoutJarChanges();
            if (result.status() == SyncProbeResult.Status.CHANGES_REQUIRED) {
                return result;
            }
            if (result.status() == SyncProbeResult.Status.SKIPPED_OFFLINE) {
                skippedOffline = true;
            }
            if (config.syncResourcePacks()) {
                logger.accept(language.text("检查资源包同步目标 [", "Checking resource-pack sync target [")
                        + (index + 1) + "/" + targets.size() + "] "
                        + targetLabel + ": " + target.gameDirectory());
                SyncProbeResult resourceResult = new ResourcePackSyncEngine(
                        config.forGameDirectory(target.gameDirectory()),
                        prefixedLogger(logger, targetLabel + language.text(" / 资源包", " / Resource packs")))
                        .probeWithoutChanges();
                if (resourceResult.status() == SyncProbeResult.Status.CHANGES_REQUIRED) {
                    return resourceResult;
                }
                if (resourceResult.status() == SyncProbeResult.Status.SKIPPED_OFFLINE) {
                    skippedOffline = true;
                }
            }
            if (config.syncServerList()) {
                logger.accept(language.text("检查服务器列表同步目标 [", "Checking server-list sync target [")
                        + (index + 1) + "/" + targets.size() + "] "
                        + targetLabel + ": " + target.gameDirectory());
                SyncProbeResult serverListResult = new ServerListSyncEngine(
                        config.forGameDirectory(target.gameDirectory()),
                        prefixedLogger(logger, targetLabel + language.text(" / 服务器列表", " / Server list")))
                        .probeWithoutChanges();
                if (serverListResult.status() == SyncProbeResult.Status.CHANGES_REQUIRED) {
                    return serverListResult;
                }
                if (serverListResult.status() == SyncProbeResult.Status.SKIPPED_OFFLINE) {
                    skippedOffline = true;
                }
            }
        }
        return new SyncProbeResult(skippedOffline
                ? SyncProbeResult.Status.SKIPPED_OFFLINE
                : SyncProbeResult.Status.UP_TO_DATE);
    }

    static SyncResult synchronize(
            ModSyncConfig config,
            Consumer<String> logger,
            SyncObserver observer) throws IOException, InterruptedException {
        Optional<V5ReleaseSync.Loaded> v5 = V5ReleaseSync.load(config, logger);
        if (v5.isPresent()) {
            int installed = 0;
            int removed = 0;
            boolean changed = false;
            for (BakaXLLayout.Target target : BakaXLLayout.syncTargets(config.gameDirectory())) {
                ModSyncConfig targetConfig = config.forGameDirectory(target.gameDirectory());
                SyncResult result = V5ReleaseSync.synchronize(
                        targetConfig, v5.get(), logger, observer);
                installed += result.downloaded();
                removed += result.quarantined();
                changed |= result.status() == SyncResult.Status.UPDATED;
                if (config.syncServerList()) {
                    SyncResult serverList = new ServerListSyncEngine(targetConfig, logger, observer).synchronize();
                    installed += serverList.downloaded();
                    removed += serverList.quarantined();
                    changed |= serverList.status() == SyncResult.Status.UPDATED;
                }
            }
            if (changed) {
                observer.afterUpdate(installed, removed, 0);
                return new SyncResult(SyncResult.Status.UPDATED, installed, removed, 0);
            }
            return new SyncResult(SyncResult.Status.UNCHANGED, 0, 0, 0);
        }
        DisplayLanguage language = DisplayLanguage.detect(config.gameDirectory());
        int downloaded = 0;
        int quarantined = 0;
        int unchanged = 0;
        boolean updated = false;
        boolean skippedOffline = false;
        List<BakaXLLayout.Target> targets = BakaXLLayout.syncTargets(config.gameDirectory());
        int unitsPerTarget = 1
                + (config.syncResourcePacks() ? 1 : 0)
                + (config.syncServerList() ? 1 : 0);
        int unitCount = targets.size() * unitsPerTarget;

        for (int index = 0; index < targets.size(); index++) {
            BakaXLLayout.Target target = targets.get(index);
            String targetLabel = localizeTargetLabel(target.label(), language);
            int nextUnit = index * unitsPerTarget + 1;
            logger.accept(language.text("同步目标 [", "Sync target [")
                    + (index + 1) + "/" + targets.size() + "] "
                    + targetLabel + ": " + target.gameDirectory());
            SyncObserver forwarding = forwardingObserver(
                    observer,
                    targetLabel + " / Mod",
                    nextUnit++,
                    unitCount);
            SyncResult result = new ModSyncEngine(
                    config.forGameDirectory(target.gameDirectory()),
                    prefixedLogger(logger, targetLabel),
                    forwarding).synchronize();
            downloaded += result.downloaded();
            quarantined += result.quarantined();
            unchanged += result.unchanged();
            updated |= result.status() == SyncResult.Status.UPDATED;
            skippedOffline |= result.status() == SyncResult.Status.SKIPPED_OFFLINE;

            if (config.syncResourcePacks()) {
                logger.accept(language.text("资源包同步目标 [", "Resource-pack sync target [")
                        + (index + 1) + "/" + targets.size() + "] "
                        + targetLabel + ": " + target.gameDirectory());
                SyncObserver resourceForwarding = forwardingObserver(
                        observer,
                        targetLabel + language.text(" / 资源包", " / Resource packs"),
                        nextUnit++,
                        unitCount);
                SyncResult resourceResult = new ResourcePackSyncEngine(
                        config.forGameDirectory(target.gameDirectory()),
                        prefixedLogger(logger, targetLabel + language.text(" / 资源包", " / Resource packs")),
                        resourceForwarding).synchronize();
                downloaded += resourceResult.downloaded();
                quarantined += resourceResult.quarantined();
                unchanged += resourceResult.unchanged();
                updated |= resourceResult.status() == SyncResult.Status.UPDATED;
                skippedOffline |= resourceResult.status() == SyncResult.Status.SKIPPED_OFFLINE;
            }

            if (config.syncServerList()) {
                logger.accept(language.text("服务器列表同步目标 [", "Server-list sync target [")
                        + (index + 1) + "/" + targets.size() + "] "
                        + targetLabel + ": " + target.gameDirectory());
                SyncObserver serverListForwarding = forwardingObserver(
                        observer,
                        targetLabel + language.text(" / 服务器列表", " / Server list"),
                        nextUnit,
                        unitCount);
                SyncResult serverListResult = new ServerListSyncEngine(
                        config.forGameDirectory(target.gameDirectory()),
                        prefixedLogger(logger, targetLabel + language.text(" / 服务器列表", " / Server list")),
                        serverListForwarding).synchronize();
                downloaded += serverListResult.downloaded();
                quarantined += serverListResult.quarantined();
                unchanged += serverListResult.unchanged();
                updated |= serverListResult.status() == SyncResult.Status.UPDATED;
                skippedOffline |= serverListResult.status() == SyncResult.Status.SKIPPED_OFFLINE;
            }
        }

        if (updated) {
            observer.afterUpdate(downloaded, quarantined, unchanged);
            return new SyncResult(SyncResult.Status.UPDATED, downloaded, quarantined, unchanged);
        }
        return new SyncResult(
                skippedOffline ? SyncResult.Status.SKIPPED_OFFLINE : SyncResult.Status.UNCHANGED,
                downloaded,
                quarantined,
                unchanged);
    }

    private static Consumer<String> prefixedLogger(Consumer<String> logger, String label) {
        return message -> logger.accept("[" + label + "] " + message);
    }

    private static String localizeTargetLabel(String label, DisplayLanguage language) {
        if (language.chinese()) {
            return label;
        }
        return switch (label) {
            case "游戏目录" -> "Game directory";
            case "BakaXL 运行副本" -> "BakaXL runtime copy";
            case "BakaXL 持久实例" -> "BakaXL persistent instance";
            default -> label;
        };
    }

    private static SyncObserver forwardingObserver(
            SyncObserver delegate,
            String label,
            int targetIndex,
            int targetCount) {
        return new SyncObserver() {
            @Override
            public RemovalDecision decideServerRemoved(List<String> serverRemoved) throws IOException {
                return delegate.decideServerRemoved(serverRemoved);
            }

            @Override
            public UnknownModDecision decideUnknownClientMod(String fileName) throws IOException {
                return delegate.decideUnknownClientMod(fileName);
            }

            @Override
            public Set<String> chooseRecommendedMods(RecommendedSelectionRequest request) throws IOException {
                return delegate.chooseRecommendedMods(request);
            }

            @Override
            public void beforeDownload(
                    List<String> downloads,
                    List<String> replacedOldVersions,
                    List<String> rejectedUnknownMods,
                    List<String> quarantinedServerRemoved,
                    List<String> retainedServerRemoved,
                    List<String> retainedClientMods) throws IOException {
                delegate.beforeDownload(
                        downloads,
                        replacedOldVersions,
                        rejectedUnknownMods,
                        quarantinedServerRemoved,
                        retainedServerRemoved,
                        retainedClientMods);
            }

            @Override
            public void phaseChanged(String message) {
                delegate.phaseChanged("[" + label + "] " + message);
            }

            @Override
            public void beforeResourcePackDownload(
                    List<String> downloads,
                    List<String> backedUpRemoved) throws IOException {
                delegate.beforeResourcePackDownload(downloads, backedUpRemoved);
            }

            @Override
            public void beforeServerListDownload(String fileName) throws IOException {
                delegate.beforeServerListDownload(fileName);
            }

            @Override
            public void downloadProgress(DownloadProgress progress) {
                int overallPermille = ((targetIndex - 1) * 1000 + progress.totalPermille()) / targetCount;
                long overallDownloadedBytes = targetCount == 1 ? progress.totalDownloadedBytes() : -1;
                long overallBytes = targetCount == 1 ? progress.totalBytes() : -1;
                delegate.downloadProgress(new DownloadProgress(
                        progress.fileName(),
                        progress.fileIndex(),
                        progress.fileCount(),
                        progress.fileDownloadedBytes(),
                        progress.fileTotalBytes(),
                        overallDownloadedBytes,
                        overallBytes,
                        overallPermille));
            }

            // Completion is emitted once by the coordinator after every
            // BakaXL target has committed successfully.
            @Override
            public void afterUpdate(int downloaded, int quarantined, int unchanged) {
            }
        };
    }
}
