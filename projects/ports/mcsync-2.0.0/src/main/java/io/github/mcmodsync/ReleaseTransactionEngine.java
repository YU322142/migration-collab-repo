package io.github.mcmodsync;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Stages, verifies, commits, and rolls back one complete schema-v5 release. */
final class ReleaseTransactionEngine {
    interface ArtifactProvider {
        byte[] fetch(ReleaseManifestV5.FileEntry entry) throws IOException, InterruptedException;
    }

    record Result(boolean changed, int installed, int removed, int configChanged, Path receipt) {
    }

    private final Path root;
    private final Path state;
    private final FileOperations fileOperations;

    ReleaseTransactionEngine(Path gameDirectory, int fileOperationRetries) {
        this.root = gameDirectory.toAbsolutePath().normalize();
        this.state = root.resolve(".modsync");
        this.fileOperations = new FileOperations(fileOperationRetries);
    }

    Result apply(
            ReleaseManifestV5 manifest,
            String manifestSha256,
            ArtifactProvider provider) throws IOException, InterruptedException {
        Files.createDirectories(state);
        if (Files.exists(state.resolve("RECOVERY_REQUIRED.txt"))) {
            throw new IOException("检测到未完成恢复标记，拒绝开始新的 v5 事务");
        }
        ReleaseSequenceGate sequenceGate = new ReleaseSequenceGate(state);
        ReleaseSequenceGate.Decision gateDecision = sequenceGate.validate(manifest, manifestSha256);
        if (gateDecision.alreadyApplied()) {
            return new Result(false, 0, 0, 0, null);
        }

        ManagedPathPolicy paths = new ManagedPathPolicy(root, manifest.managedScopes());
        ReleaseOwnershipLedger ownership = new ReleaseOwnershipLedger(state);
        Map<String, String> previousOwnership = ownership.read();
        String transactionId = manifest.releaseId() + "-" + UUID.randomUUID();
        Path transaction = state.resolve("transactions").resolve(transactionId);
        Path stage = transaction.resolve("stage");
        Path backup = transaction.resolve("backup");
        Files.createDirectories(stage);
        Files.createDirectories(backup);

        LinkedHashMap<String, byte[]> desired = new LinkedHashMap<>();
        LinkedHashMap<String, String> desiredHashes = new LinkedHashMap<>();
        for (ReleaseManifestV5.FileEntry entry : manifest.files()) {
            if (!appliesToClient(entry.side())) continue;
            paths.resolve(entry.path(), true);
            byte[] bytes = provider.fetch(entry);
            if (bytes.length != entry.size()) throw new IOException("下载文件大小不匹配: " + entry.path());
            String hash = Hashing.sha256(bytes);
            if (!hash.equals(entry.sha256())) throw new IOException("下载文件 SHA256 不匹配: " + entry.path());
            desired.put(entry.path(), bytes);
            desiredHashes.put(entry.path(), hash);
        }

        int configChanged = 0;
        for (ReleaseManifestV5.ConfigOperation operation : manifest.configOperations()) {
            if (!appliesToClientConfig(operation.side()) || !operation.phase().equals("prelaunch")) continue;
            Path target = paths.resolve(operation.path(), true);
            if (operation.operation().equals("file-replace")) {
                if (!desired.containsKey(operation.path())) {
                    throw new IOException("file-replace 缺少同路径文件条目: " + operation.path());
                }
                continue;
            }
            byte[] base = desired.get(operation.path());
            if (base == null) {
                base = Files.isRegularFile(target) ? Files.readAllBytes(target) : emptyDocument(operation.format());
            }
            ConfigMutationEngine.MutationResult mutation = ConfigMutationEngine.apply(base, operation);
            if (mutation.changed()) configChanged++;
            desired.put(operation.path(), mutation.bytes());
            desiredHashes.put(operation.path(), Hashing.sha256(mutation.bytes()));
        }

        LinkedHashSet<String> removals = new LinkedHashSet<>();
        for (Map.Entry<String, String> previous : previousOwnership.entrySet()) {
            if (desired.containsKey(previous.getKey()) || !paths.isManaged(previous.getKey())) continue;
            Path target = paths.resolve(previous.getKey(), true);
            if (Files.isRegularFile(target) && Hashing.sha256(target).equals(previous.getValue())) {
                removals.add(previous.getKey());
            }
        }

        for (Map.Entry<String, byte[]> entry : desired.entrySet()) {
            Path staged = stage.resolve(entry.getKey()).normalize();
            if (!staged.startsWith(stage)) throw new IOException("暂存路径逃逸: " + entry.getKey());
            Files.createDirectories(staged.getParent());
            Files.write(staged, entry.getValue());
            if (!Hashing.sha256(staged).equals(desiredHashes.get(entry.getKey()))) {
                throw new IOException("暂存后复核失败: " + entry.getKey());
            }
        }

        List<BackupEntry> backups = new ArrayList<>();
        boolean commitStarted = false;
        try {
            Set<String> touched = new LinkedHashSet<>(desired.keySet());
            touched.addAll(removals);
            for (String relative : touched) {
                Path target = paths.resolve(relative, true);
                if (Files.exists(target)) {
                    if (!Files.isRegularFile(target)) throw new IOException("目标不是普通文件: " + relative);
                    Path saved = backup.resolve(relative).normalize();
                    Files.createDirectories(saved.getParent());
                    Files.copy(target, saved, StandardCopyOption.COPY_ATTRIBUTES);
                    backups.add(new BackupEntry(relative, true));
                } else {
                    backups.add(new BackupEntry(relative, false));
                }
            }
            commitStarted = true;
            for (String relative : removals) fileOperations.deleteIfExists(paths.resolve(relative, true));
            for (Map.Entry<String, byte[]> entry : desired.entrySet()) {
                Path staged = stage.resolve(entry.getKey());
                Path target = paths.resolve(entry.getKey(), true);
                Files.createDirectories(target.getParent());
                fileOperations.move(staged, target, true);
            }
            for (Map.Entry<String, String> expected : desiredHashes.entrySet()) {
                Path target = paths.resolve(expected.getKey(), true);
                if (!Files.isRegularFile(target) || !Hashing.sha256(target).equals(expected.getValue())) {
                    throw new IOException("事务写后校验失败: " + expected.getKey());
                }
            }
            Path receipt = writeReceipt(transaction, manifest, manifestSha256, desiredHashes, removals);
            ownership.write(manifest.releaseId(), manifest.releaseSequence(), desiredHashes);
            sequenceGate.commit(manifest, manifestSha256);
            return new Result(!desired.isEmpty() || !removals.isEmpty(), desired.size(), removals.size(), configChanged, receipt);
        } catch (Throwable failure) {
            if (commitStarted) {
                try {
                    rollback(paths, backup, backups);
                } catch (Throwable rollbackFailure) {
                    Files.writeString(state.resolve("RECOVERY_REQUIRED.txt"),
                            "MCSync v5 transaction " + transactionId + " rollback failed.\n"
                                    + rollbackFailure + "\n",
                            StandardCharsets.UTF_8);
                    failure.addSuppressed(rollbackFailure);
                }
            }
            if (failure instanceof InterruptedException interrupted) throw interrupted;
            if (failure instanceof IOException io) throw io;
            throw new IOException("MCSync v5 事务失败", failure);
        }
    }

    private void rollback(ManagedPathPolicy paths, Path backup, List<BackupEntry> entries) throws IOException {
        List<BackupEntry> reverse = new ArrayList<>(entries);
        reverse.sort(Comparator.comparing(BackupEntry::relative).reversed());
        for (BackupEntry entry : reverse) {
            Path target = paths.resolve(entry.relative(), true);
            if (entry.existed()) {
                Path saved = backup.resolve(entry.relative());
                Files.createDirectories(target.getParent());
                Files.copy(saved, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.COPY_ATTRIBUTES);
            } else {
                fileOperations.deleteIfExists(target);
            }
        }
    }

    private static Path writeReceipt(
            Path transaction,
            ReleaseManifestV5 manifest,
            String manifestSha256,
            Map<String, String> files,
            Set<String> removals) throws IOException {
        LinkedHashMap<String, Object> receipt = new LinkedHashMap<>();
        receipt.put("schema", 1);
        receipt.put("releaseId", manifest.releaseId());
        receipt.put("releaseSequence", manifest.releaseSequence());
        receipt.put("manifestSha256", manifestSha256);
        receipt.put("committedAt", Instant.now().toString());
        receipt.put("files", new LinkedHashMap<>(files));
        receipt.put("removed", List.copyOf(removals));
        Path result = transaction.resolve("receipt.json");
        Files.writeString(result, StrictJson.stringify(receipt) + "\n", StandardCharsets.UTF_8);
        return result;
    }

    private static byte[] emptyDocument(String format) throws IOException {
        return switch (format) {
            case "json" -> "{}\n".getBytes(StandardCharsets.UTF_8);
            case "toml", "properties" -> new byte[0];
            default -> throw new IOException("缺失配置文件不能用该格式创建: " + format);
        };
    }

    private static boolean appliesToClient(Set<String> side) {
        return side.contains("client") || side.contains("both");
    }

    private static boolean appliesToClientConfig(Set<String> side) {
        return side.contains("client") || side.contains("integrated_server") || side.contains("both");
    }

    private record BackupEntry(String relative, boolean existed) {
    }
}
