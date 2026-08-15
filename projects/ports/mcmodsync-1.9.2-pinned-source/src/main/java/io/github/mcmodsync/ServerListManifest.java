package io.github.mcmodsync;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;
import java.util.regex.Pattern;

record ServerListManifest(String md5) {
    static final String MAGIC = "# mc-serverlist-sync-v1";
    static final String FILE_NAME = "servers.dat";
    private static final Pattern MD5_PATTERN = Pattern.compile("[0-9a-fA-F]{32}");

    ServerListManifest {
        md5 = md5.toLowerCase(Locale.ROOT);
        if (!MD5_PATTERN.matcher(md5).matches()) {
            throw new IllegalArgumentException("服务器列表 MD5 无效: " + md5);
        }
    }

    static ServerListManifest fromFile(Path serversDat) throws IOException {
        Path normalized = serversDat.toAbsolutePath().normalize();
        if (!Files.isRegularFile(normalized)) {
            throw new IOException("servers.dat 不存在: " + normalized);
        }
        if (!normalized.getFileName().toString().equalsIgnoreCase(FILE_NAME)) {
            throw new IOException("服务器列表文件必须命名为 servers.dat: " + normalized);
        }
        return new ServerListManifest(Hashing.md5(normalized));
    }

    static ServerListManifest parse(String text) {
        if (text == null) {
            throw new IllegalArgumentException("服务器列表清单内容为空");
        }
        String[] lines = text.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1);
        boolean magicFound = false;
        String foundMd5 = null;
        for (int index = 0; index < lines.length; index++) {
            String line = lines[index];
            if (line.strip().equals(MAGIC)) {
                magicFound = true;
                continue;
            }
            if (line.isBlank() || line.startsWith("#")) {
                continue;
            }
            int separator = line.indexOf('\t');
            if (separator <= 0 || line.indexOf('\t', separator + 1) >= 0) {
                throw new IllegalArgumentException("服务器列表清单第 " + (index + 1) + " 行格式错误");
            }
            String fileName = line.substring(separator + 1);
            if (!fileName.equals(FILE_NAME)) {
                throw new IllegalArgumentException("服务器列表清单只允许 servers.dat: " + fileName);
            }
            if (foundMd5 != null) {
                throw new IllegalArgumentException("服务器列表清单只能包含一个 servers.dat");
            }
            foundMd5 = line.substring(0, separator).strip();
        }
        if (!magicFound) {
            throw new IllegalArgumentException("不是受支持的服务器列表清单：缺少 " + MAGIC);
        }
        if (foundMd5 == null) {
            throw new IllegalArgumentException("服务器列表清单没有 servers.dat");
        }
        return new ServerListManifest(foundMd5);
    }

    String serialize() {
        return MAGIC + "\n# minecraft=1.21.1,1.21.11\n# MD5\\t文件名\n" + md5 + "\t" + FILE_NAME + "\n";
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
}
