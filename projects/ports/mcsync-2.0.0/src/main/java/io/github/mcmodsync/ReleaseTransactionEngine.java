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

    boolean needsApply(ReleaseManifestV5 manifest, String manifestSha256) throws IOException {
        Files.createDirectories(state);
        ManagedPathPolicy paths = new ManagedPathPolicy(root, manifest.managedScopes());
        ReleaseSequenceGate.Decision decision = new ReleaseSequenceGate(state).validate(manifest, manifestSha256);
        if (decision.newRelease()) return true;
        LinkedHashSet<String> desiredPaths = new LinkedHashSet<>();
        for (ReleaseManifestV5.FileEntry entry : manifest.files()) {
            if (!appliesToClient(entry.side())) continue;
            desiredPaths.add(entry.path());
            Path target = paths.resolve(entry.path(), true);
            if (paths.policyFor(entry.path()).equals("first-install") && Files.exists(target)) continue;
            if (!Files.isRegularFile(target) || Files.size(target) != entry.size()
                    || !Hashing.sha256(target).equals(entry.sha256())) return true;
        }
        for (ReleaseManifestV5.ConfigOperation operation : manifest.configOperations()) {
            if (!appliesToClientConfig(operation.side()) || !operation.phase().equals("prelaunch")) continue;
            Path target = paths.resolve(operation.path(), true);
            if (operation.operation().equals("file-replace")) continue;
            byte[] base = Files.isRegularFile(target) ? Files.readAllBytes(target) : emptyDocument(operation.format());
            if (ConfigMutationEngine.apply(base, operation).changed()) return true;
            desiredPaths.add(operation.path());
        }
        for (Map.Entry<String, String> previous : new ReleaseOwnershipLedger(state).read().entrySet()) {
            if (desiredPaths.contains(previous.getKey()) || !paths.isManaged(previous.getKey())) continue;
            Path target = paths.resolve(previous.getKey(), true);
            if (Files.isRegularFile(target) && Hashing.sha256(target).equals(previous.getValue())) return true;
        }
        return false;
    }

    Result apply(
            ReleaseManifestV5 manifest,
            String manifestSha256,
            ArtifactProvider provider) throws IOException, InterruptedException {
        Files.createDirectories(state);
        recoverPendingTransactions();
        if (Files.exists(state.resolve("RECOVERY_REQUIRED.txt"))) {
            throw new IOException("检测到未完成恢复标记，拒绝开始新的 v5 事务");
        }
        ReleaseSequenceGate sequenceGate = new ReleaseSequenceGate(state);
        ReleaseSequenceGate.Decision gateDecision = sequenceGate.validate(manifest, manifestSha256);
        if (gateDecision.alreadyApplied() && !needsApply(manifest, manifestSha256)) {
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
            Path localTarget = paths.resolve(entry.path(), true);
            if (paths.policyFor(entry.path()).equals("first-install") && Files.exists(localTarget)) {
                continue;
            }
            byte[] bytes;
            if (entry.download().type().equals("manual")) {
                Path local = paths.resolve(entry.path(), true);
                if (!Files.isRegularFile(local) || Files.size(local) != entry.size()
                        || !Hashing.sha256(local).equals(entry.sha256())) {
                    continue;
                }
                bytes = Files.readAllBytes(local);
            } else if (Files.isRegularFile(localTarget) && Files.size(localTarget) == entry.size()
                    && Hashing.sha256(localTarget).equals(entry.sha256())) {
                bytes = Files.readAllBytes(localTarget);
            } else {
                bytes = provider.fetch(entry);
            }
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
                boolean exists = Files.isRegularFile(target);
                if (operation.expectedSha256().equals("absent")) {
                    if (exists) throw new IOException("file-replace 前像应不存在但目标已存在: " + operation.path());
                } else if (!exists || !Hashing.sha256(target).equals(operation.expectedSha256())) {
                    throw new IOException("file-replace 目标前像 SHA256 不匹配: " + operation.path());
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
            if (entry.getKey().toLowerCase(java.util.Locale.ROOT).endsWith(".jar")
                    && ModMetadata.readModId(staged).equals(BuildInfo.TECHNICAL_MOD_ID)) {
                String candidateVersion = ModMetadata.readVersion(staged);
                if (candidateVersion.isBlank()) {
                    throw new IOException("MCSync 自更新候选缺少可读版本元数据");
                }
                if (VersionOrder.compare(candidateVersion, BuildInfo.VERSION) < 0) {
                    throw new IOException("拒绝通过 v5 发布降级 MCSync: " + candidateVersion
                            + " < " + BuildInfo.VERSION);
                }
            }
        }
        addLegacySelfUpdateRemovals(paths, stage, desired.keySet(), removals);

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
                    backups.add(new BackupEntry(relative, true, Hashing.sha256(saved)));
                } else {
                    backups.add(new BackupEntry(relative, false, ""));
                }
            }
            Path journal = writePreparedJournal(transaction, manifest, manifestSha256, backups);
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
            ownership.write(manifest.releaseId(), manifest.releaseSequence(), desiredHashes);
            sequenceGate.commit(manifest, manifestSha256);
            Path receipt = writeReceipt(transaction, manifest, manifestSha256, desiredHashes, removals);
            Files.deleteIfExists(journal);
            return new Result(!desired.isEmpty() || !removals.isEmpty(), desired.size(), removals.size(), configChanged, receipt);
        } catch (Throwable failure) {
            if (commitStarted) {
                try {
                    rollback(paths, backup, backups);
                    Files.deleteIfExists(transaction.resolve("journal.json"));
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

    private void addLegacySelfUpdateRemovals(
            ManagedPathPolicy paths,
            Path stage,
            Set<String> desiredPaths,
            Set<String> removals) throws IOException {
        List<String> selfCandidates = new ArrayList<>();
        for (String relative : desiredPaths) {
            if (!relative.toLowerCase(java.util.Locale.ROOT).endsWith(".jar")) continue;
            Path staged = stage.resolve(relative);
            if (ModMetadata.readModId(staged).equals(BuildInfo.TECHNICAL_MOD_ID)) selfCandidates.add(relative);
        }
        if (selfCandidates.size() > 1) {
            throw new IOException("v5 发布不能包含多个 MCSync 自更新候选");
        }
        if (selfCandidates.isEmpty()) return;
        Path mods = root.resolve("mods");
        if (!Files.isDirectory(mods)) return;
        String desired = selfCandidates.getFirst().replace('\\', '/');
        try (var stream = Files.list(mods)) {
            for (Path existing : stream.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().toLowerCase(java.util.Locale.ROOT).endsWith(".jar"))
                    .toList()) {
                String relative = root.relativize(existing).toString().replace('\\', '/');
                if (relative.equalsIgnoreCase(desired)) continue;
                if (ModMetadata.readModId(existing).equals(BuildInfo.TECHNICAL_MOD_ID)) {
                    paths.resolve(relative, true);
                    removals.add(relative);
                }
            }
        }
    }

    int recoverPendingTransactions() throws IOException {
        Path transactions = state.resolve("transactions");
        if (!Files.isDirectory(transactions)) return 0;
        ManagedPathPolicy paths = new ManagedPathPolicy(root, List.of());
        int recovered = 0;
        try (var stream = Files.list(transactions)) {
            for (Path transaction : stream.filter(Files::isDirectory).sorted().toList()) {
                Path journal = transaction.resolve("journal.json");
                if (!Files.isRegularFile(journal)) continue;
                List<BackupEntry> entries = readPreparedJournal(journal, transaction.resolve("backup"));
                try {
                    rollback(paths, transaction.resolve("backup"), entries);
                    LinkedHashMap<String, Object> receipt = new LinkedHashMap<>();
                    receipt.put("schema", 1);
                    receipt.put("status", "ROLLED_BACK_AFTER_INTERRUPTED_COMMIT");
                    receipt.put("recoveredAt", Instant.now().toString());
                    receipt.put("journalSha256", Hashing.sha256(journal));
                    receipt.put("restored", entries.stream().map(BackupEntry::relative).toList());
                    Files.writeString(transaction.resolve("recovery-receipt.json"),
                            StrictJson.stringify(receipt) + "\n", StandardCharsets.UTF_8);
                    Files.delete(journal);
                    recovered++;
                } catch (Throwable failure) {
                    Files.writeString(state.resolve("RECOVERY_REQUIRED.txt"),
                            "MCSync could not recover interrupted transaction " + transaction.getFileName()
                                    + ".\n" + failure + "\n",
                            StandardCharsets.UTF_8);
                    if (failure instanceof IOException io) throw io;
                    throw new IOException("中断事务自动恢复失败", failure);
                }
            }
        }
        return recovered;
    }

    private void rollback(ManagedPathPolicy paths, Path backup, List<BackupEntry> entries) throws IOException {
        List<BackupEntry> reverse = new ArrayList<>(entries);
        reverse.sort(Comparator.comparing(BackupEntry::relative).reversed());
        for (BackupEntry entry : reverse) {
            Path target = paths.resolve(entry.relative(), true);
            if (entry.existed()) {
                Path saved = backup.resolve(entry.relative());
                if (!Files.isRegularFile(saved) || !Hashing.sha256(saved).equals(entry.backupSha256())) {
                    throw new IOException("事务备份缺失或哈希漂移: " + entry.relative());
                }
                Files.createDirectories(target.getParent());
                Files.copy(saved, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.COPY_ATTRIBUTES);
            } else {
                fileOperations.deleteIfExists(target);
            }
        }
    }

    private static Path writePreparedJournal(
            Path transaction,
            ReleaseManifestV5 manifest,
            String manifestSha256,
            List<BackupEntry> backups) throws IOException {
        LinkedHashMap<String, Object> journal = new LinkedHashMap<>();
        journal.put("schema", 1);
        journal.put("state", "PREPARED");
        journal.put("releaseId", manifest.releaseId());
        journal.put("releaseSequence", manifest.releaseSequence());
        journal.put("manifestSha256", manifestSha256);
        journal.put("createdAt", Instant.now().toString());
        journal.put("backups", backups.stream().map(entry -> Map.of(
                "path", entry.relative(),
                "existed", entry.existed(),
                "sha256", entry.backupSha256())).toList());
        Path result = transaction.resolve("journal.json");
        Files.writeString(result, StrictJson.stringify(journal) + "\n", StandardCharsets.UTF_8);
        return result;
    }

    @SuppressWarnings("unchecked")
    private static List<BackupEntry> readPreparedJournal(Path journal, Path backup) throws IOException {
        Object parsed;
        try {
            parsed = StrictJson.parse(Files.readString(journal, StandardCharsets.UTF_8));
        } catch (RuntimeException failure) {
            throw new IOException("事务日志不是有效 JSON: " + journal, failure);
        }
        if (!(parsed instanceof Map<?, ?> raw)) throw new IOException("事务日志根不是对象");
        Map<String, Object> object = (Map<String, Object>) raw;
        if (!new java.math.BigDecimal("1").equals(object.get("schema"))
                || !"PREPARED".equals(object.get("state"))
                || !(object.get("backups") instanceof List<?> values)) {
            throw new IOException("事务日志 schema/state/backups 无效");
        }
        ArrayList<BackupEntry> result = new ArrayList<>();
        LinkedHashSet<String> seen = new LinkedHashSet<>();
        for (Object value : values) {
            if (!(value instanceof Map<?, ?> entry)) throw new IOException("事务日志备份条目不是对象");
            Object pathRaw = entry.get("path");
            Object existedRaw = entry.get("existed");
            Object hashRaw = entry.get("sha256");
            if (!(pathRaw instanceof String relative) || !(existedRaw instanceof Boolean existed)
                    || !(hashRaw instanceof String hash) || !seen.add(relative.toLowerCase(java.util.Locale.ROOT))) {
                throw new IOException("事务日志备份条目无效或重复");
            }
            Path saved = backup.resolve(relative).normalize();
            if (!saved.startsWith(backup)) throw new IOException("事务日志备份路径逃逸");
            if (existed && (!hash.matches("[0-9a-f]{64}") || !Files.isRegularFile(saved))) {
                throw new IOException("事务日志声明的备份不存在或哈希格式无效: " + relative);
            }
            if (!existed && !hash.isEmpty()) throw new IOException("不存在目标的备份哈希必须为空");
            result.add(new BackupEntry(relative, existed, hash));
        }
        return List.copyOf(result);
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

    private record BackupEntry(String relative, boolean existed, String backupSha256) {
    }
}
