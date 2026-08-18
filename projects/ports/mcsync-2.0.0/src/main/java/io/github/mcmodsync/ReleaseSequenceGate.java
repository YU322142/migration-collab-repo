package io.github.mcmodsync;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Properties;
import java.util.regex.Pattern;

/** Monotonic release gate. State is committed only after a complete OTA transaction succeeds. */
final class ReleaseSequenceGate {
    static final String STATE_FILE_NAME = "release-state-v1.properties";
    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
    private final Path stateFile;

    ReleaseSequenceGate(Path stateDirectory) {
        this.stateFile = stateDirectory.resolve(STATE_FILE_NAME).toAbsolutePath().normalize();
    }

    Decision validate(ReleaseManifestV5 manifest, String manifestSha256) throws IOException {
        String hash = normalizeHash(manifestSha256);
        State current = read();
        if (current == null || manifest.releaseSequence() > current.releaseSequence()) {
            return new Decision(true, false, current);
        }
        if (manifest.releaseSequence() < current.releaseSequence()) {
            throw new IOException("MCSync 已阻止清单降级: remote=" + manifest.releaseSequence()
                    + ", installed=" + current.releaseSequence());
        }
        boolean identical = manifest.releaseId().equals(current.releaseId())
                && hash.equals(current.manifestSha256());
        if (!identical) {
            throw new IOException("相同 releaseSequence 对应了不同发布内容，已按防回滚策略阻止");
        }
        return new Decision(false, true, current);
    }

    void commit(ReleaseManifestV5 manifest, String manifestSha256) throws IOException {
        String hash = normalizeHash(manifestSha256);
        validate(manifest, hash);
        Files.createDirectories(stateFile.getParent());
        Path temporary = Files.createTempFile(stateFile.getParent(), ".release-state-", ".tmp");
        boolean moved = false;
        try {
            Properties properties = new Properties();
            properties.setProperty("releaseSequence", Long.toString(manifest.releaseSequence()));
            properties.setProperty("releaseId", manifest.releaseId());
            properties.setProperty("manifestSha256", hash);
            properties.setProperty("mcsyncVersion", BuildInfo.VERSION);
            try (OutputStream output = Files.newOutputStream(temporary)) {
                properties.store(output, "MCSync monotonic release state; do not edit manually");
            }
            try {
                Files.move(temporary, stateFile,
                        StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException exception) {
                Files.move(temporary, stateFile, StandardCopyOption.REPLACE_EXISTING);
            }
            moved = true;
        } finally {
            if (!moved) {
                Files.deleteIfExists(temporary);
            }
        }
    }

    State read() throws IOException {
        if (!Files.isRegularFile(stateFile)) {
            return null;
        }
        Properties properties = new Properties();
        try (InputStream input = Files.newInputStream(stateFile)) {
            properties.load(input);
        }
        try {
            long sequence = Long.parseLong(required(properties, "releaseSequence"));
            if (sequence < 1) {
                throw new IllegalArgumentException("releaseSequence");
            }
            String releaseId = required(properties, "releaseId");
            String hash = normalizeHash(required(properties, "manifestSha256"));
            return new State(sequence, releaseId, hash);
        } catch (IllegalArgumentException exception) {
            throw new IOException("MCSync 本地防降级状态损坏，拒绝在未知状态下继续", exception);
        }
    }

    Path stateFile() {
        return stateFile;
    }

    record Decision(boolean newRelease, boolean alreadyApplied, State current) {
    }

    record State(long releaseSequence, String releaseId, String manifestSha256) {
    }

    private static String required(Properties properties, String key) {
        String value = properties.getProperty(key, "").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException(key);
        }
        return value;
    }

    private static String normalizeHash(String value) {
        String result = value == null ? "" : value.strip().toLowerCase(java.util.Locale.ROOT);
        if (!SHA256.matcher(result).matches()) {
            throw new IllegalArgumentException("manifestSha256 格式无效");
        }
        return result;
    }
}
