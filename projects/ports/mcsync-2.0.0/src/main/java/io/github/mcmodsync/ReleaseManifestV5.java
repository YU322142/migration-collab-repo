package io.github.mcmodsync;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

record ReleaseManifestV5(
        String releaseId,
        long releaseSequence,
        String minimumMcsyncVersion,
        List<FileEntry> files,
        List<ConfigOperation> configOperations) {

    static final int SCHEMA = 5;
    static final int MAX_MANIFEST_BYTES = 8 * 1024 * 1024;
    private static final Pattern RELEASE_ID = Pattern.compile("[A-Za-z0-9._-]{1,128}");
    private static final Pattern SHA256 = Pattern.compile("[0-9a-fA-F]{64}");
    private static final Set<String> FILE_KINDS = Set.of(
            "mod", "resource-pack", "shader-pack", "kubejs", "config", "default-config", "support");
    private static final Set<String> SIDES = Set.of("client", "server", "both");
    private static final Set<String> CONFIG_OPERATIONS = Set.of("config-set", "config-merge", "file-replace");
    private static final Set<String> CONFIG_FORMATS = Set.of("toml", "json", "properties", "text", "binary");
    private static final Set<String> CONFLICT_POLICIES = Set.of("fail", "keep-local", "replace-if-expected");

    ReleaseManifestV5 {
        files = List.copyOf(files);
        configOperations = List.copyOf(configOperations);
    }

    static ReleaseManifestV5 parse(byte[] bytes) {
        if (bytes == null || bytes.length == 0 || bytes.length > MAX_MANIFEST_BYTES) {
            throw new IllegalArgumentException("MCSync v5 清单大小无效");
        }
        Object parsed = StrictJson.parse(new String(bytes, StandardCharsets.UTF_8));
        Map<String, Object> root = object(parsed, "root");
        if (integer(root, "schema") != SCHEMA) {
            throw new IllegalArgumentException("MCSync 2.0 只接受 schema=5 的结构化清单");
        }
        String releaseId = string(root, "releaseId");
        if (!RELEASE_ID.matcher(releaseId).matches()) {
            throw new IllegalArgumentException("releaseId 格式无效");
        }
        long sequence = integer(root, "releaseSequence");
        if (sequence < 1) {
            throw new IllegalArgumentException("releaseSequence 必须为正整数");
        }
        String minimumVersion = string(root, "minimumMCSyncVersion");
        if (minimumVersion.length() > 64) {
            throw new IllegalArgumentException("minimumMCSyncVersion 过长");
        }

        List<FileEntry> files = new ArrayList<>();
        Set<String> normalizedPaths = new HashSet<>();
        for (Object value : array(root, "files")) {
            Map<String, Object> file = object(value, "files[]");
            String path = safeRelativePath(string(file, "path"));
            if (!normalizedPaths.add(path.toLowerCase(Locale.ROOT))) {
                throw new IllegalArgumentException("清单包含重复文件路径: " + path);
            }
            String hash = string(file, "sha256").toLowerCase(Locale.ROOT);
            if (!SHA256.matcher(hash).matches()) {
                throw new IllegalArgumentException("文件 SHA256 无效: " + path);
            }
            long size = integer(file, "size");
            if (size < 0) {
                throw new IllegalArgumentException("文件大小不能为负数: " + path);
            }
            String kind = oneOf(string(file, "kind"), FILE_KINDS, "文件 kind");
            boolean required = bool(file, "required", true);
            boolean restartRequired = bool(file, "restartRequired", true);
            Set<String> side = stringSet(file, "side", Set.of("client"), SIDES);
            files.add(new FileEntry(path, hash, size, kind, required, restartRequired, side));
        }
        if (files.isEmpty()) {
            throw new IllegalArgumentException("v5 清单至少要包含一个文件");
        }

        List<ConfigOperation> configOperations = new ArrayList<>();
        for (Object value : optionalArray(root, "configOperations")) {
            Map<String, Object> operation = object(value, "configOperations[]");
            String path = safeRelativePath(string(operation, "path"));
            String type = oneOf(string(operation, "operation"), CONFIG_OPERATIONS, "配置 operation");
            String format = oneOf(string(operation, "format"), CONFIG_FORMATS, "配置 format");
            String key = optionalString(operation, "key");
            if (!type.equals("file-replace") && key.isBlank()) {
                throw new IllegalArgumentException(type + " 必须声明 key");
            }
            String conflictPolicy = oneOf(
                    optionalString(operation, "conflictPolicy", "replace-if-expected"),
                    CONFLICT_POLICIES,
                    "配置 conflictPolicy");
            boolean restartRequired = bool(operation, "restartRequired", true);
            Object expected = operation.get("expected");
            Object desired = operation.get("desired");
            if (!operation.containsKey("desired")) {
                throw new IllegalArgumentException("配置操作缺少 desired: " + path + "#" + key);
            }
            configOperations.add(new ConfigOperation(
                    path, type, format, key, expected, desired, conflictPolicy, restartRequired));
        }
        return new ReleaseManifestV5(releaseId, sequence, minimumVersion, files, configOperations);
    }

    record FileEntry(
            String path,
            String sha256,
            long size,
            String kind,
            boolean required,
            boolean restartRequired,
            Set<String> side) {
        FileEntry {
            side = Set.copyOf(side);
        }
    }

    record ConfigOperation(
            String path,
            String operation,
            String format,
            String key,
            Object expected,
            Object desired,
            String conflictPolicy,
            boolean restartRequired) {
    }

    private static String safeRelativePath(String value) {
        String normalized = value.replace('\\', '/');
        if (normalized.isBlank() || normalized.length() > 512 || normalized.startsWith("/")
                || normalized.matches("^[A-Za-z]:.*") || normalized.contains("\u0000")) {
            throw new IllegalArgumentException("清单路径无效: " + value);
        }
        for (String segment : normalized.split("/", -1)) {
            if (segment.isBlank() || segment.equals(".") || segment.equals("..")) {
                throw new IllegalArgumentException("清单路径不安全: " + value);
            }
        }
        return normalized;
    }

    private static Map<String, Object> object(Object value, String field) {
        if (!(value instanceof Map<?, ?> map)) {
            throw new IllegalArgumentException(field + " 必须是对象");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> typed = (Map<String, Object>) map;
        return typed;
    }

    private static List<Object> array(Map<String, Object> object, String field) {
        Object value = object.get(field);
        if (!(value instanceof List<?> list)) {
            throw new IllegalArgumentException(field + " 必须是数组");
        }
        @SuppressWarnings("unchecked")
        List<Object> typed = (List<Object>) list;
        return typed;
    }

    private static List<Object> optionalArray(Map<String, Object> object, String field) {
        return object.containsKey(field) ? array(object, field) : List.of();
    }

    private static String string(Map<String, Object> object, String field) {
        String value = optionalString(object, field);
        if (value.isBlank()) {
            throw new IllegalArgumentException(field + " 不能为空");
        }
        return value;
    }

    private static String optionalString(Map<String, Object> object, String field) {
        return optionalString(object, field, "");
    }

    private static String optionalString(Map<String, Object> object, String field, String fallback) {
        Object value = object.get(field);
        if (value == null) {
            return fallback;
        }
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException(field + " 必须是字符串");
        }
        return text.strip();
    }

    private static long integer(Map<String, Object> object, String field) {
        Object value = object.get(field);
        if (!(value instanceof BigDecimal number)) {
            throw new IllegalArgumentException(field + " 必须是整数");
        }
        try {
            return number.longValueExact();
        } catch (ArithmeticException exception) {
            throw new IllegalArgumentException(field + " 必须是 64 位整数", exception);
        }
    }

    private static boolean bool(Map<String, Object> object, String field, boolean fallback) {
        Object value = object.get(field);
        if (value == null) {
            return fallback;
        }
        if (!(value instanceof Boolean result)) {
            throw new IllegalArgumentException(field + " 必须是布尔值");
        }
        return result;
    }

    private static Set<String> stringSet(
            Map<String, Object> object,
            String field,
            Set<String> fallback,
            Set<String> allowed) {
        if (!object.containsKey(field)) {
            return fallback;
        }
        Set<String> result = new HashSet<>();
        for (Object value : array(object, field)) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException(field + " 只能包含字符串");
            }
            result.add(oneOf(text, allowed, field));
        }
        if (result.isEmpty()) {
            throw new IllegalArgumentException(field + " 不能为空");
        }
        return Set.copyOf(result);
    }

    private static String oneOf(String value, Set<String> allowed, String field) {
        String normalized = value.strip().toLowerCase(Locale.ROOT);
        if (!allowed.contains(normalized)) {
            throw new IllegalArgumentException(field + " 不受支持: " + value);
        }
        return normalized;
    }
}
