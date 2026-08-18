package io.github.mcmodsync;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

final class ResourcePackManifest {
    static final String MAGIC = "# mc-resourcepack-sync-v1";
    private static final Pattern MD5_PATTERN = Pattern.compile("[0-9a-fA-F]{32}");
    private static final String WINDOWS_FORBIDDEN = "<>:\"|?*";

    private final List<ResourcePackEntry> entries;

    private ResourcePackManifest(List<ResourcePackEntry> entries) {
        this.entries = List.copyOf(entries);
    }

    static ResourcePackManifest fromFile(Path resourcePack) throws IOException {
        Path normalized = resourcePack.toAbsolutePath().normalize();
        if (!Files.isRegularFile(normalized)) {
            throw new IOException("资源包文件不存在: " + normalized);
        }
        String fileName = normalized.getFileName().toString();
        validateFileName(fileName);
        return new ResourcePackManifest(List.of(new ResourcePackEntry(Hashing.md5(normalized), fileName)));
    }

    static ResourcePackManifest parse(String text) {
        if (text == null) {
            throw new IllegalArgumentException("资源包清单内容为空");
        }
        String[] lines = text.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1);
        boolean magicFound = false;
        for (String line : lines) {
            if (line.strip().equals(MAGIC)) {
                magicFound = true;
                break;
            }
        }
        if (!magicFound) {
            throw new IllegalArgumentException("不是受支持的资源包清单：缺少 " + MAGIC);
        }

        Set<String> names = new HashSet<>();
        java.util.ArrayList<ResourcePackEntry> entries = new java.util.ArrayList<>();
        for (int index = 0; index < lines.length; index++) {
            String line = lines[index];
            if (line.isBlank() || line.startsWith("#")) {
                continue;
            }
            int separator = line.indexOf('\t');
            if (separator <= 0 || separator == line.length() - 1 || line.indexOf('\t', separator + 1) >= 0) {
                throw new IllegalArgumentException("资源包清单第 " + (index + 1) + " 行格式错误，应为 MD5、文件名");
            }
            String md5 = line.substring(0, separator).strip().toLowerCase(Locale.ROOT);
            String fileName = line.substring(separator + 1);
            if (!MD5_PATTERN.matcher(md5).matches()) {
                throw new IllegalArgumentException("资源包清单第 " + (index + 1) + " 行 MD5 无效: " + md5);
            }
            validateFileName(fileName);
            if (!names.add(fileName.toLowerCase(Locale.ROOT))) {
                throw new IllegalArgumentException("资源包清单包含重复文件名: " + fileName);
            }
            entries.add(new ResourcePackEntry(md5, fileName));
            if (entries.size() > 1_000) {
                throw new IllegalArgumentException("资源包清单条目超过安全上限 1000");
            }
        }
        if (entries.isEmpty()) {
            throw new IllegalArgumentException("资源包清单没有任何 .zip 文件");
        }
        return new ResourcePackManifest(entries);
    }

    void write(Path output) throws IOException {
        Path normalized = output.toAbsolutePath().normalize();
        if (normalized.getParent() != null) {
            Files.createDirectories(normalized.getParent());
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
        StringBuilder builder = new StringBuilder();
        builder.append(MAGIC).append('\n');
        builder.append("# minecraft=1.21.1,1.21.11\n");
        builder.append("# MD5\\t文件名\n");
        for (ResourcePackEntry entry : entries) {
            builder.append(entry.md5()).append('\t').append(entry.fileName()).append('\n');
        }
        return builder.toString();
    }

    List<ResourcePackEntry> entries() {
        return entries;
    }

    private static void validateFileName(String fileName) {
        if (fileName == null || fileName.isEmpty() || !fileName.equals(fileName.strip())) {
            throw new IllegalArgumentException("资源包文件名不能为空，也不能以空白开头或结尾");
        }
        if (!fileName.toLowerCase(Locale.ROOT).endsWith(".zip")) {
            throw new IllegalArgumentException("资源包清单只允许 .zip 文件: " + fileName);
        }
        if (fileName.length() > 240 || fileName.equals(".") || fileName.equals("..")) {
            throw new IllegalArgumentException("不安全的资源包文件名: " + fileName);
        }
        for (int index = 0; index < fileName.length(); index++) {
            char current = fileName.charAt(index);
            if (current < 32 || current == 127 || current == '/' || current == '\\'
                    || WINDOWS_FORBIDDEN.indexOf(current) >= 0) {
                throw new IllegalArgumentException("资源包文件名包含不允许的字符: " + fileName);
            }
        }
    }
}
