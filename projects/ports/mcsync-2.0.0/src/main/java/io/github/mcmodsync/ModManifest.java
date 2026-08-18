package io.github.mcmodsync;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

final class ModManifest {
    static final String MAGIC_V1 = "# mcmod-sync-v1";
    static final String MAGIC_V2 = "# mcmod-sync-v2";
    static final String MAGIC_V3 = "# mcmod-sync-v3";
    static final String MAGIC_V4 = "# mcmod-sync-v4";
    // Kept for source compatibility with tests and legacy integrations.
    static final String MAGIC = MAGIC_V2;
    private static final Pattern MD5_PATTERN = Pattern.compile("[0-9a-fA-F]{32}");
    private static final Pattern SHA256_PATTERN = Pattern.compile("[0-9a-fA-F]{64}");
    private static final Set<Character> WINDOWS_FORBIDDEN = Set.of('<', '>', ':', '"', '|', '?', '*');
    private static final DateTimeFormatter GENERATED_VERSION = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");

    private final int format;
    private final String catalogVersion;
    private final List<ManifestEntry> entries;
    private final ManagedClientConfig managedClientConfig;

    private ModManifest(
            int format,
            String catalogVersion,
            List<ManifestEntry> entries,
            ManagedClientConfig managedClientConfig) {
        this.format = format;
        this.catalogVersion = catalogVersion == null ? "" : catalogVersion.strip();
        this.entries = List.copyOf(entries);
        this.managedClientConfig = managedClientConfig;
    }

    static ModManifest fromEntries(List<ManifestEntry> entries) {
        boolean modern = entries.stream().allMatch(entry -> !entry.sha256().isBlank());
        return new ModManifest(modern ? 4 : 2, modern ? generatedCatalogVersion() : "", entries, null);
    }

    static ModManifest fromEntries(String catalogVersion, List<ManifestEntry> entries) {
        return new ModManifest(4, requireCatalogVersion(catalogVersion), entries, null);
    }

    ModManifest withEntries(List<ManifestEntry> replacement) {
        return new ModManifest(format, catalogVersion, replacement, managedClientConfig);
    }

    ModManifest withCatalogVersion(String replacement) {
        return new ModManifest(Math.max(format, 4), requireCatalogVersion(replacement), entries, managedClientConfig);
    }

    ModManifest withManagedClientConfig(ManagedClientConfig replacement) {
        return new ModManifest(Math.max(format, 4), catalogVersion, entries, replacement);
    }

    static ModManifest scan(Path modsDirectory) throws IOException {
        return scan(modsDirectory, new String[0]);
    }

    static ModManifest scan(Path modsDirectory, String... excludedModIds) throws IOException {
        Path normalized = modsDirectory.toAbsolutePath().normalize();
        if (!Files.isDirectory(normalized)) {
            throw new IOException("Mod 目录不存在或不是文件夹: " + normalized);
        }

        List<Path> jars;
        try (var stream = Files.list(normalized)) {
            jars = stream
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".jar"))
                    .sorted(Comparator.comparing(
                            path -> path.getFileName().toString(),
                            String.CASE_INSENSITIVE_ORDER))
                    .toList();
        }
        if (jars.isEmpty()) {
            throw new IOException("目录中没有找到任何 .jar Mod；为防止生成会清空客户端的空清单，操作已取消。");
        }

        Set<String> excluded = new HashSet<>();
        for (String modId : excludedModIds) {
            excluded.add(modId.toLowerCase(Locale.ROOT));
        }
        List<ManifestEntry> entries = new ArrayList<>(jars.size());
        for (Path jar : jars) {
            String fileName = jar.getFileName().toString();
            validateFileName(fileName);
            String modId = ModMetadata.readModId(jar);
            String lowerFileName = fileName.toLowerCase(Locale.ROOT);
            boolean legacySyncToolName = excluded.contains("mcmodsync")
                    && (lowerFileName.equals("mcmodsync.jar")
                            || (lowerFileName.startsWith("mcmodsync-") && lowerFileName.endsWith(".jar"))
                            || lowerFileName.equals("mcsync.jar")
                            || (lowerFileName.startsWith("mcsync-") && lowerFileName.endsWith(".jar")));
            if (excluded.contains(modId) || legacySyncToolName) {
                continue;
            }
            entries.add(new ManifestEntry(
                    Hashing.sha256(jar),
                    Hashing.md5(jar),
                    modId,
                    fileName,
                    ModKind.REQUIRED,
                    Set.of(),
                    ModMetadata.readName(jar),
                    ModMetadata.readVersion(jar),
                    ModMetadata.readDescription(jar)));
        }
        if (entries.isEmpty()) {
            throw new IOException("没有可发布的 .jar Mod；为防止生成空清单，操作已取消。");
        }
        return new ModManifest(4, generatedCatalogVersion(), entries, null);
    }

    static ModManifest parse(String text) {
        if (text == null) {
            throw new IllegalArgumentException("清单内容为空");
        }
        String[] lines = text.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1);
        int format = 0;
        String catalogVersion = "";
        for (String line : lines) {
            String stripped = line.strip();
            int declared = stripped.equals(MAGIC_V1) ? 1
                    : stripped.equals(MAGIC_V2) ? 2
                    : stripped.equals(MAGIC_V3) ? 3
                    : stripped.equals(MAGIC_V4) ? 4 : 0;
            if (declared != 0) {
                if (format != 0 && format != declared) {
                    throw new IllegalArgumentException("清单不能同时声明多个格式版本");
                }
                format = declared;
            }
            if (stripped.startsWith("# catalog-version=")) {
                catalogVersion = stripped.substring("# catalog-version=".length()).strip();
            }
        }
        if (format == 0) {
            throw new IllegalArgumentException("不是受支持的清单：缺少 " + MAGIC_V1 + "、" + MAGIC_V2
                    + "、" + MAGIC_V3 + " 或 " + MAGIC_V4);
        }
        if (format >= 3) {
            requireCatalogVersion(catalogVersion);
        }

        List<ManifestEntry> entries = new ArrayList<>();
        Set<String> names = new HashSet<>();
        for (int index = 0; index < lines.length; index++) {
            String line = lines[index];
            if (line.isBlank() || line.startsWith("#")) {
                continue;
            }
            ManifestEntry entry = switch (format) {
                case 1 -> parseV1(line, index + 1);
                case 2 -> parseV2(line, index + 1);
                case 3 -> parseV3(line, index + 1);
                case 4 -> parseV4(line, index + 1);
                default -> throw new IllegalStateException("unsupported format");
            };
            validateEntryHashes(entry, index + 1, format >= 3);
            validateFileName(entry.fileName());
            String key = entry.fileName().toLowerCase(Locale.ROOT);
            if (!names.add(key)) {
                throw new IllegalArgumentException("清单包含重复文件名（忽略大小写）: " + entry.fileName());
            }
            entries.add(entry);
            if (entries.size() > 10_000) {
                throw new IllegalArgumentException("清单条目超过安全上限 10000");
            }
        }
        if (entries.isEmpty()) {
            throw new IllegalArgumentException("清单不包含任何 Mod；为防止误清空客户端，已拒绝执行");
        }
        Optional<ManagedClientConfig> managed = ManagedClientConfig.fromManifestText(text);
        if (managed.isPresent() && format < 4) {
            throw new IllegalArgumentException("客户端受管配置只能写入 v4 清单");
        }
        return new ModManifest(format, catalogVersion, entries, managed.orElse(null));
    }

    private static ManifestEntry parseV1(String line, int lineNumber) {
        String[] fields = splitColumns(line, 2, lineNumber, "MD5、文件名");
        return new ManifestEntry(fields[0].strip(), "", fields[1]);
    }

    private static ManifestEntry parseV2(String line, int lineNumber) {
        String[] fields = splitColumns(line, 3, lineNumber, "MD5、Mod ID、文件名");
        String modId = parseModId(fields[1], lineNumber);
        return new ManifestEntry(fields[0].strip(), modId, fields[2]);
    }

    private static ManifestEntry parseV3(String line, int lineNumber) {
        String[] fields = splitColumns(
                line,
                9,
                lineNumber,
                "SHA256、MD5、Mod ID、文件名、类型、不兼容平台、名称、版本、描述");
        String modId = parseModId(fields[2], lineNumber);
        Set<ClientPlatform> incompatible = parsePlatforms(unescape(fields[5]), lineNumber);
        return new ManifestEntry(
                fields[0].strip().toLowerCase(Locale.ROOT),
                fields[1].strip().toLowerCase(Locale.ROOT),
                modId,
                unescape(fields[3]),
                ModKind.parse(fields[4]),
                incompatible,
                unescape(fields[6]),
                unescape(fields[7]),
                unescape(fields[8]));
    }

    private static ManifestEntry parseV4(String line, int lineNumber) {
        String[] fields = splitColumns(
                line,
                10,
                lineNumber,
                "SHA256、MD5、Mod ID、文件名、类型、不兼容平台、名称、版本、中文描述、英文描述");
        String modId = parseModId(fields[2], lineNumber);
        Set<ClientPlatform> incompatible = parsePlatforms(unescape(fields[5]), lineNumber);
        return new ManifestEntry(
                fields[0].strip().toLowerCase(Locale.ROOT),
                fields[1].strip().toLowerCase(Locale.ROOT),
                modId,
                unescape(fields[3]),
                ModKind.parse(fields[4]),
                incompatible,
                unescape(fields[6]),
                unescape(fields[7]),
                unescape(fields[8]),
                unescape(fields[9]));
    }

    private static String[] splitColumns(String line, int expected, int lineNumber, String description) {
        String[] fields = line.split("\t", -1);
        if (fields.length != expected) {
            throw new IllegalArgumentException("清单第 " + lineNumber + " 行格式错误，应为 " + description);
        }
        return fields;
    }

    private static String parseModId(String raw, int lineNumber) {
        String value = raw.strip();
        if (value.equals("-")) {
            return "";
        }
        String modId = value.toLowerCase(Locale.ROOT);
        if (!ModMetadata.isValidModId(modId)) {
            throw new IllegalArgumentException("清单第 " + lineNumber + " 行 Mod ID 无效: " + raw);
        }
        return modId;
    }

    private static Set<ClientPlatform> parsePlatforms(String raw, int lineNumber) {
        if (raw.isBlank() || raw.equals("-")) {
            return Set.of();
        }
        EnumSet<ClientPlatform> result = EnumSet.noneOf(ClientPlatform.class);
        for (String part : raw.split(",")) {
            try {
                if (!result.add(ClientPlatform.parse(part))) {
                    throw new IllegalArgumentException("重复平台: " + part);
                }
            } catch (IllegalArgumentException exception) {
                throw new IllegalArgumentException(
                        "清单第 " + lineNumber + " 行不兼容平台无效: " + raw,
                        exception);
            }
        }
        return Set.copyOf(result);
    }

    private static void validateEntryHashes(ManifestEntry entry, int lineNumber, boolean requireSha256) {
        if (!MD5_PATTERN.matcher(entry.md5()).matches()) {
            throw new IllegalArgumentException("清单第 " + lineNumber + " 行 MD5 无效: " + entry.md5());
        }
        if (requireSha256 && !SHA256_PATTERN.matcher(entry.sha256()).matches()) {
            throw new IllegalArgumentException("清单第 " + lineNumber + " 行 SHA256 无效: " + entry.sha256());
        }
    }

    void write(Path output) throws IOException {
        Path normalized = output.toAbsolutePath().normalize();
        Path parent = normalized.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Files.writeString(
                normalized,
                serialize(),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);
    }

    String serialize() {
        if (format < 3) {
            StringBuilder legacy = new StringBuilder();
            legacy.append(format == 1 ? MAGIC_V1 : MAGIC_V2).append('\n');
            legacy.append("# minecraft=1.21.1,1.21.11\n# loader=fabric,neoforge\n");
            for (ManifestEntry entry : entries) {
                legacy.append(entry.md5()).append('\t');
                if (format == 2) {
                    legacy.append(entry.modId().isEmpty() ? "-" : entry.modId()).append('\t');
                }
                legacy.append(entry.fileName()).append('\n');
            }
            return legacy.toString();
        }

        StringBuilder builder = new StringBuilder();
        builder.append(format >= 4 ? MAGIC_V4 : MAGIC_V3).append('\n');
        builder.append("# catalog-version=").append(catalogVersion).append('\n');
        builder.append("# minecraft=1.21.1,1.21.11\n# loader=fabric,neoforge\n");
        if (format >= 4) {
            if (managedClientConfig != null) {
                builder.append(managedClientConfig.serializeManifestComments());
            }
            builder.append("# SHA256\\tMD5\\tMod ID\\t文件名\\t类型\\t不兼容平台\\t名称\\t版本"
                    + "\\t中文描述\\tEnglish description\n");
        } else {
            builder.append("# SHA256\\tMD5\\tMod ID\\t文件名\\t类型\\t不兼容平台\\t名称\\t版本\\t描述\n");
        }
        for (ManifestEntry entry : entries) {
            builder.append(entry.sha256()).append('\t')
                    .append(entry.md5()).append('\t')
                    .append(entry.modId().isEmpty() ? "-" : entry.modId()).append('\t')
                    .append(escape(entry.fileName())).append('\t')
                    .append(entry.kind().id()).append('\t')
                    .append(serializePlatforms(entry.incompatiblePlatforms())).append('\t')
                    .append(escape(entry.displayName())).append('\t')
                    .append(escape(entry.version())).append('\t');
            if (format >= 4) {
                builder.append(escape(entry.descriptionZh())).append('\t')
                        .append(escape(entry.descriptionEn())).append('\n');
            } else {
                String legacyDescription = !entry.descriptionZh().isBlank()
                        ? entry.descriptionZh()
                        : entry.descriptionEn();
                builder.append(escape(legacyDescription)).append('\n');
            }
        }
        return builder.toString();
    }

    String catalogVersion() {
        return catalogVersion;
    }

    boolean supportsRecommendations() {
        return format >= 3;
    }

    Optional<ManagedClientConfig> managedClientConfig() {
        return Optional.ofNullable(managedClientConfig);
    }

    List<ManifestEntry> entries() {
        return entries;
    }

    ModManifest requiredOnly() {
        return withEntries(entries.stream()
                .filter(entry -> entry.kind() == ModKind.REQUIRED)
                .toList());
    }

    void ensureUniqueModIds() {
        Set<String> seen = new HashSet<>();
        for (ManifestEntry entry : entries) {
            if (!entry.modId().isEmpty() && !seen.add(entry.modId())) {
                throw new IllegalArgumentException("清单包含重复 Mod ID: " + entry.modId());
            }
        }
    }

    long entriesWithoutModId() {
        return entries.stream().filter(entry -> entry.modId().isEmpty()).count();
    }

    void verifySnapshot(Path modsDirectory) throws IOException {
        Path normalized = modsDirectory.toAbsolutePath().normalize();
        verifyManagedFiles(normalized);
        Set<String> expected = new HashSet<>();
        for (ManifestEntry entry : entries) {
            expected.add(entry.fileName().toLowerCase(Locale.ROOT));
        }
        try (var stream = Files.list(normalized)) {
            for (Path path : stream
                    .filter(Files::isRegularFile)
                    .filter(item -> item.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".jar"))
                    .toList()) {
                if (!expected.contains(path.getFileName().toString().toLowerCase(Locale.ROOT))) {
                    throw new IOException("本地存在未记录在 mods.txt 中的 Mod: " + path.getFileName());
                }
            }
        }
    }

    void verifyManagedFiles(Path modsDirectory) throws IOException {
        Path normalized = modsDirectory.toAbsolutePath().normalize();
        for (ManifestEntry entry : entries) {
            Path file = normalized.resolve(entry.fileName()).normalize();
            if (!normalized.equals(file.getParent()) || !Files.isRegularFile(file)) {
                throw new IOException("本地清单所列文件不存在: " + entry.fileName());
            }
            verifyFile(entry, file);
        }
    }

    static boolean fileMatches(ManifestEntry entry, Path file) throws IOException {
        if (!Files.isRegularFile(file) || !Hashing.md5(file).equals(entry.md5())) {
            return false;
        }
        return entry.sha256().isBlank() || Hashing.sha256(file).equals(entry.sha256());
    }

    private static void verifyFile(ManifestEntry entry, Path file) throws IOException {
        String actualMd5 = Hashing.md5(file);
        if (!actualMd5.equals(entry.md5())) {
            throw new IOException("本地文件 MD5 不符: " + entry.fileName()
                    + "，期望 " + entry.md5() + "，实际 " + actualMd5);
        }
        if (!entry.sha256().isBlank()) {
            String actualSha256 = Hashing.sha256(file);
            if (!actualSha256.equals(entry.sha256())) {
                throw new IOException("本地文件 SHA256 不符: " + entry.fileName()
                        + "，期望 " + entry.sha256() + "，实际 " + actualSha256);
            }
        }
    }

    private static String serializePlatforms(Set<ClientPlatform> platforms) {
        if (platforms.isEmpty()) {
            return "-";
        }
        return platforms.stream()
                .sorted(Comparator.comparingInt(Enum::ordinal))
                .map(ClientPlatform::id)
                .reduce((left, right) -> left + "," + right)
                .orElse("-");
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    private static String unescape(String value) {
        StringBuilder result = new StringBuilder(value.length());
        boolean escaping = false;
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            if (!escaping) {
                if (current == '\\') {
                    escaping = true;
                } else {
                    result.append(current);
                }
                continue;
            }
            result.append(switch (current) {
                case 't' -> '\t';
                case 'r' -> '\r';
                case 'n' -> '\n';
                case '\\' -> '\\';
                default -> throw new IllegalArgumentException("清单字段包含未知转义: \\" + current);
            });
            escaping = false;
        }
        if (escaping) {
            throw new IllegalArgumentException("清单字段以不完整转义结尾");
        }
        return result.toString();
    }

    private static String requireCatalogVersion(String value) {
        String normalized = value == null ? "" : value.strip();
        if (normalized.isBlank() || normalized.length() > 128
                || normalized.indexOf('\t') >= 0 || normalized.indexOf('\n') >= 0 || normalized.indexOf('\r') >= 0) {
            throw new IllegalArgumentException("v3/v4 清单必须包含有效的 catalog-version（最长 128 字符）");
        }
        return normalized;
    }

    private static String generatedCatalogVersion() {
        return GENERATED_VERSION.format(LocalDateTime.now());
    }

    private static void validateFileName(String fileName) {
        if (fileName == null || fileName.isEmpty() || !fileName.equals(fileName.strip())) {
            throw new IllegalArgumentException("文件名不能为空，也不能以空白开头或结尾: " + fileName);
        }
        if (fileName.equals(".") || fileName.equals("..") || fileName.length() > 240) {
            throw new IllegalArgumentException("不安全的文件名: " + fileName);
        }
        if (!fileName.toLowerCase(Locale.ROOT).endsWith(".jar")) {
            throw new IllegalArgumentException("清单只允许 .jar 文件: " + fileName);
        }
        for (int index = 0; index < fileName.length(); index++) {
            char current = fileName.charAt(index);
            if (current < 32 || current == 127 || current == '/' || current == '\\'
                    || WINDOWS_FORBIDDEN.contains(current)) {
                throw new IllegalArgumentException("文件名包含不允许的字符: " + fileName);
            }
        }
    }
}
