package io.github.mcmodsync;

record SyncResult(Status status, int downloaded, int quarantined, int unchanged) {
    enum Status {
        UNCHANGED,
        UPDATED,
        SKIPPED_OFFLINE
    }
}
