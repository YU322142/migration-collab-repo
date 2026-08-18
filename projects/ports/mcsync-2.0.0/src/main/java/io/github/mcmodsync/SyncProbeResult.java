package io.github.mcmodsync;

record SyncProbeResult(Status status) {
    enum Status {
        UP_TO_DATE,
        CHANGES_REQUIRED,
        SKIPPED_OFFLINE
    }
}
