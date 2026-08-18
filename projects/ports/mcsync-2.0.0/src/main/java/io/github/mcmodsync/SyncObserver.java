package io.github.mcmodsync;

import java.io.IOException;
import java.util.List;
import java.util.Set;

interface SyncObserver {
    SyncObserver NONE = new SyncObserver() {
    };

    default RemovalDecision decideServerRemoved(List<String> serverRemoved) throws IOException {
        return RemovalDecision.BACKUP;
    }

    default UnknownModDecision decideUnknownClientMod(String fileName) throws IOException {
        return UnknownModDecision.BACKUP;
    }

    default Set<String> chooseRecommendedMods(RecommendedSelectionRequest request) throws IOException {
        return request.initiallySelected();
    }

    default void beforeDownload(
            List<String> downloads,
            List<String> replacedOldVersions,
            List<String> rejectedUnknownMods,
            List<String> quarantinedServerRemoved,
            List<String> retainedServerRemoved,
            List<String> retainedClientMods) throws IOException {
    }

    default void beforeResourcePackDownload(
            List<String> downloads,
            List<String> backedUpRemoved) throws IOException {
    }

    default void beforeServerListDownload(String fileName) throws IOException {
    }

    default void phaseChanged(String message) {
    }

    default void downloadProgress(DownloadProgress progress) {
    }

    default void afterUpdate(int downloaded, int quarantined, int unchanged) {
    }

    enum RemovalDecision {
        BACKUP,
        KEEP
    }

    enum UnknownModDecision {
        KEEP_CLIENT,
        BACKUP
    }

    record DownloadProgress(
            String fileName,
            int fileIndex,
            int fileCount,
            long fileDownloadedBytes,
            long fileTotalBytes,
            long totalDownloadedBytes,
            long totalBytes,
            int totalPermille) {
    }
}
