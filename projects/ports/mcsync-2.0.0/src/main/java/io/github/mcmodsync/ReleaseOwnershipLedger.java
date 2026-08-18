package io.github.mcmodsync;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.LinkedHashMap;
import java.util.Map;

/** Hash ledger used to remove only files previously installed and still unmodified. */
final class ReleaseOwnershipLedger {
    private final Path path;

    ReleaseOwnershipLedger(Path stateDirectory) {
        this.path = stateDirectory.resolve("ownership-v5.json");
    }

    Map<String, String> read() throws IOException {
        if (!Files.isRegularFile(path)) return Map.of();
        Object parsed = StrictJson.parse(Files.readString(path, StandardCharsets.UTF_8));
        if (!(parsed instanceof Map<?, ?> root) || !new BigDecimal("1").equals(root.get("schema"))) {
            throw new IOException("MCSync ownership ledger 格式无效: " + path);
        }
        Object files = root.get("files");
        if (!(files instanceof Map<?, ?> values)) throw new IOException("ownership ledger 缺少 files");
        LinkedHashMap<String, String> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : values.entrySet()) {
            if (!(entry.getKey() instanceof String key) || !(entry.getValue() instanceof String hash)
                    || !hash.matches("[0-9a-f]{64}")) {
                throw new IOException("ownership ledger 包含非法记录");
            }
            result.put(key, hash);
        }
        return Map.copyOf(result);
    }

    void write(String releaseId, long sequence, Map<String, String> files) throws IOException {
        LinkedHashMap<String, Object> root = new LinkedHashMap<>();
        root.put("schema", 1);
        root.put("releaseId", releaseId);
        root.put("releaseSequence", sequence);
        root.put("files", new LinkedHashMap<>(files));
        Files.createDirectories(path.getParent());
        Path temporary = Files.createTempFile(path.getParent(), "ownership-", ".tmp");
        Files.writeString(temporary, StrictJson.stringify(root) + "\n", StandardCharsets.UTF_8);
        try {
            Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
