package io.github.mcmodsync;

final class DownloadProgressTracker {
    private final SyncObserver observer;
    private final int fileCount;
    private final long expectedTotalBytes;
    private final long[] downloadedBytes;
    private final long[] declaredBytes;
    private final boolean[] finished;

    DownloadProgressTracker(SyncObserver observer, int fileCount, long expectedTotalBytes) {
        this.observer = observer;
        this.fileCount = fileCount;
        this.expectedTotalBytes = expectedTotalBytes;
        this.downloadedBytes = new long[fileCount];
        this.declaredBytes = new long[fileCount];
        this.finished = new boolean[fileCount];
    }

    synchronized void report(
            String fileName,
            int fileIndex,
            long fileDownloadedBytes,
            long fileTotalBytes,
            boolean fileFinished) {
        int slot = fileIndex - 1;
        downloadedBytes[slot] = Math.max(downloadedBytes[slot], fileDownloadedBytes);
        if (fileTotalBytes > 0) {
            declaredBytes[slot] = fileTotalBytes;
        }
        finished[slot] |= fileFinished;

        long overallDownloaded = -1;
        int totalPermille;
        if (expectedTotalBytes > 0) {
            long sum = 0;
            for (long downloaded : downloadedBytes) {
                if (Long.MAX_VALUE - sum < downloaded) {
                    sum = expectedTotalBytes;
                    break;
                }
                sum += downloaded;
            }
            overallDownloaded = Math.min(expectedTotalBytes, sum);
            totalPermille = (int) Math.round((double) overallDownloaded / expectedTotalBytes * 1000.0);
        } else {
            double completedFileUnits = 0.0;
            for (int index = 0; index < fileCount; index++) {
                if (declaredBytes[index] > 0) {
                    completedFileUnits += Math.min(1.0, (double) downloadedBytes[index] / declaredBytes[index]);
                } else if (finished[index]) {
                    completedFileUnits += 1.0;
                }
            }
            totalPermille = (int) Math.round(completedFileUnits / fileCount * 1000.0);
        }

        observer.downloadProgress(new SyncObserver.DownloadProgress(
                fileName,
                fileIndex,
                fileCount,
                fileDownloadedBytes,
                fileTotalBytes,
                overallDownloaded,
                expectedTotalBytes,
                Math.max(0, Math.min(1000, totalPermille))));
    }
}
