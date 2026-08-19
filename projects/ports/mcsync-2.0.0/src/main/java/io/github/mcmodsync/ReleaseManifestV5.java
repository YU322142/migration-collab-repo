package io.github.mcmodsync;

import java.math.BigDecimal;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

record ReleaseManifestV5(
        String releaseId,
        long releaseSequence,
        String minimumMcsyncVersion,
        List<ManagedScope> managedScopes,
        List<FileEntry> files,
        List<ConfigOperation> configOperations) {

    static final int SCHEMA = 5;
    static final int MAX_MANIFEST_BYTES = 8 * 1024 * 1024;
    private static final Pattern RELEASE_ID = Pattern.compile("[A-Za-z0-9._-]{1,128}");
    private static final Pattern SHA256 = Pattern.compile("[0-9a-fA-F]{64}");
    private static final Set<String> FILE_KINDS = Set.of(
            "mod", "resource-pack", "shader-pack", "kubejs", "config", "default-config", "support");
    private static final Set<String> SIDES = Set.of("client", "server", "both");
    private static final Set<String> DOWNLOAD_SOURCE_TYPES = Set.of(
            "publisher-hosted", "direct", "modrinth", "curseforge", "manual");
    private static final Set<String> DISTRIBUTION_POLICIES = Set.of(
            "redistributable", "upstream-only", "manual");
    private static final Set<String> ENDPOINT_ROLES = Set.of("official", "mirror");
    private static final Set<String> ENDPOINT_PURPOSES = Set.of("file", "api");
    private static final Set<String> ENDPOINT_REGIONS = Set.of("global", "cn");
    private static final Set<String> CONFIG_OPERATIONS = Set.of("config-set", "config-merge", "file-replace");
    private static final Set<String> CONFIG_FORMATS = Set.of(
            "toml", "json", "json5", "properties", "snbt", "text", "binary");
    private static final Set<String> VALUE_TYPES = Set.of(
            "boolean", "integer", "decimal", "string", "array", "object", "binary");
    private static final Set<String> MISSING_POLICIES = Set.of("create", "skip", "block");
    private static final Set<String> CONFLICT_POLICIES = Set.of(
            "block", "keep-local", "report", "force", "replace-if-expected");
    private static final Set<String> CONFIG_SIDES = Set.of(
            "client", "integrated_server", "dedicated_server", "both");
    private static final Set<String> APPLY_PHASES = Set.of("prelaunch", "first-install");
    private static final Set<String> SCOPE_POLICIES = Set.of("managed", "additive", "first-install");

    ReleaseManifestV5 {
        managedScopes = List.copyOf(managedScopes);
        files = List.copyOf(files);
        configOperations = List.copyOf(configOperations);
    }

    static ReleaseManifestV5 parse(byte[] bytes) {
        if (bytes == null || bytes.length == 0 || bytes.length > MAX_MANIFEST_BYTES) {
            throw new IllegalArgumentException("MCSync v5 清单大小无效");
        }
        Object parsed = StrictJson.parse(new String(bytes, StandardCharsets.UTF_8));
        Map<String, Object> root = object(parsed, "root");
        requireOnlyKeys(root, "root", Set.of(
                "schema", "releaseId", "releaseSequence", "minimumMCSyncVersion",
                "managedScopes", "files", "configOperations"));
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

        List<ManagedScope> managedScopes = new ArrayList<>();
        Set<String> normalizedScopes = new HashSet<>();
        for (Object value : optionalArray(root, "managedScopes")) {
            Map<String, Object> scope = object(value, "managedScopes[]");
            requireOnlyKeys(scope, "managedScopes[]", Set.of("path", "policy"));
            String path = safeRelativePath(string(scope, "path"));
            if (!normalizedScopes.add(path.toLowerCase(Locale.ROOT))) {
                throw new IllegalArgumentException("清单包含重复受管范围: " + path);
            }
            String policy = oneOf(string(scope, "policy"), SCOPE_POLICIES, "managedScopes.policy");
            managedScopes.add(new ManagedScope(path, policy));
        }

        List<FileEntry> files = new ArrayList<>();
        Set<String> normalizedPaths = new HashSet<>();
        for (Object value : array(root, "files")) {
            Map<String, Object> file = object(value, "files[]");
            requireOnlyKeys(file, "files[]", Set.of(
                    "path", "sha256", "size", "kind", "required", "restartRequired", "side", "download",
                    "modId", "displayName", "version", "descriptionZh", "descriptionEn",
                    "incompatiblePlatforms"));
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
            if (!required && !Set.of("mod", "resource-pack", "shader-pack").contains(kind)) {
                throw new IllegalArgumentException("只有 Mod、资源包和光影包可以设为可选: " + path);
            }
            boolean restartRequired = bool(file, "restartRequired", true);
            Set<String> side = stringSet(file, "side", Set.of("client"), SIDES);
            String modId = optionalString(file, "modId");
            String displayName = optionalString(file, "displayName");
            String version = optionalString(file, "version");
            String descriptionZh = optionalString(file, "descriptionZh");
            String descriptionEn = optionalString(file, "descriptionEn");
            Set<String> incompatiblePlatforms = stringSet(
                    file, "incompatiblePlatforms", Set.of(), Set.of("windows", "linux", "macos", "android"));
            DownloadSource source = parseDownloadSource(file.get("download"), path, kind);
            if (required && source.type().equals("manual")) {
                throw new IllegalArgumentException("必须文件不能使用 manual 下载源: " + path);
            }
            files.add(new FileEntry(
                    path, hash, size, kind, required, restartRequired, side, source,
                    modId, displayName, version, descriptionZh, descriptionEn, incompatiblePlatforms));
        }
        if (files.isEmpty()) {
            throw new IllegalArgumentException("v5 清单至少要包含一个文件");
        }

        List<ConfigOperation> configOperations = new ArrayList<>();
        Set<String> configTargets = new HashSet<>();
        for (Object value : optionalArray(root, "configOperations")) {
            Map<String, Object> operation = object(value, "configOperations[]");
            requireOnlyKeys(operation, "configOperations[]", Set.of(
                    "path", "op", "format", "key", "valueType", "expected", "desired",
                    "expectedSha256", "missingPolicy", "conflictPolicy", "side", "phase", "restartRequired"));
            String path = safeRelativePath(string(operation, "path"));
            String type = oneOf(string(operation, "op"), CONFIG_OPERATIONS, "配置 op");
            String format = oneOf(string(operation, "format"), CONFIG_FORMATS, "配置 format");
            String key = optionalString(operation, "key");
            if (!type.equals("file-replace") && key.isBlank()) {
                throw new IllegalArgumentException(type + " 必须声明 key");
            }
            if (!type.equals("file-replace")) SensitiveDataPolicy.rejectSensitiveConfigKey(key);
            String configTarget = (path + "#" + (type.equals("file-replace") ? "<file>" : key))
                    .toLowerCase(Locale.ROOT);
            if (!configTargets.add(configTarget)) {
                throw new IllegalArgumentException("清单包含重复配置操作目标: " + path + "#" + key);
            }
            String expectedSha256 = optionalString(operation, "expectedSha256").toLowerCase(Locale.ROOT);
            String valueType = oneOf(
                    optionalString(operation, "valueType", type.equals("file-replace") ? "binary" : "string"),
                    VALUE_TYPES,
                    "配置 valueType");
            String missingPolicy = oneOf(
                    optionalString(operation, "missingPolicy", "block"),
                    MISSING_POLICIES,
                    "配置 missingPolicy");
            String conflictPolicy = oneOf(
                    optionalString(operation, "conflictPolicy", "block"),
                    CONFLICT_POLICIES,
                    "配置 conflictPolicy");
            Set<String> side = stringSet(operation, "side", Set.of("both"), CONFIG_SIDES);
            String phase = oneOf(
                    optionalString(operation, "phase", "prelaunch"),
                    APPLY_PHASES,
                    "配置 phase");
            boolean restartRequired = bool(operation, "restartRequired", true);
            Object expected = operation.get("expected");
            Object desired = operation.get("desired");
            if (!operation.containsKey("desired")) {
                throw new IllegalArgumentException("配置操作缺少 desired: " + path + "#" + key);
            }
            validateConfigOperation(type, format, valueType, expected, desired, expectedSha256, path, key);
            configOperations.add(new ConfigOperation(
                    path, type, format, key, valueType, expected, desired, expectedSha256, missingPolicy,
                    conflictPolicy, side, phase, restartRequired));
        }
        return new ReleaseManifestV5(
                releaseId, sequence, minimumVersion, managedScopes, files, configOperations);
    }

    byte[] serialize() {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("schema", SCHEMA);
        root.put("releaseId", releaseId);
        root.put("releaseSequence", releaseSequence);
        root.put("minimumMCSyncVersion", minimumMcsyncVersion);
        root.put("managedScopes", managedScopes.stream().map(scope -> Map.of(
                "path", scope.path(),
                "policy", scope.policy())).toList());
        root.put("files", files.stream().map(ReleaseManifestV5::fileJson).toList());
        root.put("configOperations", configOperations.stream().map(ReleaseManifestV5::configJson).toList());
        return (StrictJson.stringify(root) + "\n").getBytes(StandardCharsets.UTF_8);
    }

    record ManagedScope(String path, String policy) {
    }

    record FileEntry(
            String path,
            String sha256,
            long size,
            String kind,
            boolean required,
            boolean restartRequired,
            Set<String> side,
            DownloadSource download,
            String modId,
            String displayName,
            String version,
            String descriptionZh,
            String descriptionEn,
            Set<String> incompatiblePlatforms) {
        FileEntry {
            side = Set.copyOf(side);
            incompatiblePlatforms = Set.copyOf(incompatiblePlatforms);
        }

        FileEntry(
                String path,
                String sha256,
                long size,
                String kind,
                boolean required,
                boolean restartRequired,
                Set<String> side,
                DownloadSource download) {
            this(path, sha256, size, kind, required, restartRequired, side, download,
                    "", "", "", "", "", Set.of());
        }

        boolean recommendedMod() {
            return kind.equals("mod") && !required;
        }

        boolean optionalSelectable() {
            return !required && Set.of("mod", "resource-pack", "shader-pack").contains(kind);
        }

        String selectionKey() {
            return kind.equals("mod") && !modId.isBlank()
                    ? modId.toLowerCase(Locale.ROOT)
                    : path.toLowerCase(Locale.ROOT);
        }
    }

    ReleaseManifestV5 withFiles(List<FileEntry> selectedFiles) {
        return new ReleaseManifestV5(
                releaseId, releaseSequence, minimumMcsyncVersion, managedScopes, selectedFiles, configOperations);
    }

    record DownloadSource(
            String type,
            String projectId,
            String versionId,
            Long fileId,
            String distributionPolicy,
            List<DownloadEndpoint> endpoints) {
        DownloadSource {
            endpoints = List.copyOf(endpoints);
        }
    }

    record DownloadEndpoint(
            URI uri,
            String role,
            String purpose,
            String region,
            int priority,
            boolean thirdParty) {
    }

    record ConfigOperation(
            String path,
            String operation,
            String format,
            String key,
            String valueType,
            Object expected,
            Object desired,
            String expectedSha256,
            String missingPolicy,
            String conflictPolicy,
            Set<String> side,
            String phase,
            boolean restartRequired) {
        ConfigOperation {
            side = Set.copyOf(side);
        }
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

    private static DownloadSource parseDownloadSource(Object raw, String path, String kind) {
        if (raw == null) {
            return new DownloadSource("publisher-hosted", "", "", null, "redistributable", List.of());
        }
        Map<String, Object> source = object(raw, "download");
        requireOnlyKeys(source, "download", Set.of(
                "type", "projectId", "versionId", "fileId", "distributionPolicy", "endpoints"));
        String type = oneOf(string(source, "type"), DOWNLOAD_SOURCE_TYPES, "download.type");
        String projectId = optionalString(source, "projectId");
        String versionId = optionalString(source, "versionId");
        Long fileId = optionalInteger(source, "fileId");
        String distributionPolicy = oneOf(
                optionalString(source, "distributionPolicy", defaultDistributionPolicy(type)),
                DISTRIBUTION_POLICIES,
                "download.distributionPolicy");
        boolean modArtifact = PublisherModAutoMatcher.isModArtifact(path, kind);
        if (!modArtifact && !type.equals("publisher-hosted")) {
            throw new IllegalArgumentException(
                    "只有 mods 目录中的 Mod JAR 可以使用模组站、direct 或 manual 下载源: " + path);
        }
        if (!modArtifact && !distributionPolicy.equals("redistributable")) {
            throw new IllegalArgumentException("非 Mod 文件固定作为本地发布文件，不接受分发政策选择: " + path);
        }
        List<DownloadEndpoint> endpoints = new ArrayList<>();
        for (Object value : optionalArray(source, "endpoints")) {
            Map<String, Object> endpoint = object(value, "download.endpoints[]");
            requireOnlyKeys(endpoint, "download.endpoints[]", Set.of(
                    "url", "role", "purpose", "region", "priority", "thirdParty"));
            URI uri = secureUri(string(endpoint, "url"));
            String role = oneOf(string(endpoint, "role"), ENDPOINT_ROLES, "download.endpoint.role");
            String purpose = oneOf(
                    optionalString(endpoint, "purpose", "file"),
                    ENDPOINT_PURPOSES,
                    "download.endpoint.purpose");
            String region = oneOf(
                    optionalString(endpoint, "region", "global"),
                    ENDPOINT_REGIONS,
                    "download.endpoint.region");
            long rawPriority = optionalInteger(endpoint, "priority", 100L);
            if (rawPriority < 0 || rawPriority > 10_000) {
                throw new IllegalArgumentException("download.endpoint.priority 超出范围");
            }
            boolean thirdParty = bool(endpoint, "thirdParty", false);
            if (role.equals("official") && thirdParty) {
                throw new IllegalArgumentException("official 端点不能标记为 thirdParty");
            }
            if (role.equals("mirror") && !thirdParty) {
                throw new IllegalArgumentException("mirror 端点必须显式属于第三方传输");
            }
            endpoints.add(new DownloadEndpoint(uri, role, purpose, region, (int) rawPriority, thirdParty));
        }

        switch (type) {
            case "publisher-hosted" -> {
                if (!distributionPolicy.equals("redistributable")) {
                    throw new IllegalArgumentException(
                            "publisher-hosted 只允许用于可再分发文件，禁止托管 upstream-only 文件: " + path);
                }
            }
            case "direct" -> {
                rejectManualPolicy(distributionPolicy, type, path);
                requireFileEndpoint(endpoints, type, path);
            }
            case "modrinth" -> {
                rejectManualPolicy(distributionPolicy, type, path);
                requireIdentifier(projectId, "Modrinth projectId", path);
                requireIdentifier(versionId, "Modrinth versionId", path);
            }
            case "curseforge" -> {
                rejectManualPolicy(distributionPolicy, type, path);
                requireIdentifier(projectId, "CurseForge modId", path);
                if (fileId == null || fileId < 1) {
                    throw new IllegalArgumentException("CurseForge 文件缺少有效 fileId: " + path);
                }
            }
            case "manual" -> {
                if (!distributionPolicy.equals("manual")) {
                    throw new IllegalArgumentException("manual 下载源必须使用 manual 分发策略: " + path);
                }
                if (!endpoints.isEmpty()) {
                    throw new IllegalArgumentException("manual 下载源不能声明自动下载端点: " + path);
                }
            }
            default -> throw new IllegalArgumentException("未知下载源: " + type);
        }
        return new DownloadSource(type, projectId, versionId, fileId, distributionPolicy, endpoints);
    }

    private static Map<String, Object> fileJson(FileEntry file) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("path", file.path());
        result.put("sha256", file.sha256());
        result.put("size", file.size());
        result.put("kind", file.kind());
        result.put("required", file.required());
        result.put("restartRequired", file.restartRequired());
        result.put("side", file.side().stream().sorted().toList());
        putIfNotBlank(result, "modId", file.modId());
        putIfNotBlank(result, "displayName", file.displayName());
        putIfNotBlank(result, "version", file.version());
        putIfNotBlank(result, "descriptionZh", file.descriptionZh());
        putIfNotBlank(result, "descriptionEn", file.descriptionEn());
        if (!file.incompatiblePlatforms().isEmpty()) {
            result.put("incompatiblePlatforms", file.incompatiblePlatforms().stream().sorted().toList());
        }
        DownloadSource source = file.download();
        Map<String, Object> download = new LinkedHashMap<>();
        download.put("type", source.type());
        download.put("distributionPolicy", source.distributionPolicy());
        if (!source.projectId().isBlank()) {
            download.put("projectId", source.projectId());
        }
        if (!source.versionId().isBlank()) {
            download.put("versionId", source.versionId());
        }
        if (source.fileId() != null) {
            download.put("fileId", source.fileId());
        }
        if (!source.endpoints().isEmpty()) {
            download.put("endpoints", source.endpoints().stream().map(endpoint -> Map.of(
                    "url", endpoint.uri().toASCIIString(),
                    "role", endpoint.role(),
                    "purpose", endpoint.purpose(),
                    "region", endpoint.region(),
                    "priority", endpoint.priority(),
                    "thirdParty", endpoint.thirdParty())).toList());
        }
        result.put("download", download);
        return result;
    }

    private static void putIfNotBlank(Map<String, Object> target, String key, String value) {
        if (value != null && !value.isBlank()) target.put(key, value);
    }

    private static Map<String, Object> configJson(ConfigOperation operation) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("path", operation.path());
        result.put("op", operation.operation());
        result.put("format", operation.format());
        if (!operation.key().isBlank()) {
            result.put("key", operation.key());
        }
        result.put("valueType", operation.valueType());
        result.put("expected", operation.expected());
        result.put("desired", operation.desired());
        if (!operation.expectedSha256().isBlank()) result.put("expectedSha256", operation.expectedSha256());
        result.put("missingPolicy", operation.missingPolicy());
        result.put("conflictPolicy", operation.conflictPolicy());
        result.put("side", operation.side().stream().sorted().toList());
        result.put("phase", operation.phase());
        result.put("restartRequired", operation.restartRequired());
        return result;
    }

    private static void validateConfigOperation(
            String operation,
            String format,
            String valueType,
            Object expected,
            Object desired,
            String expectedSha256,
            String path,
            String key) {
        if (!operation.equals("file-replace") && Set.of("json5", "snbt", "text", "binary").contains(format)) {
            throw new IllegalArgumentException(
                    format + " 暂不支持可靠键级编辑，只能使用带前像约束的 file-replace: " + path);
        }
        if (operation.equals("file-replace") && !key.isBlank()) {
            throw new IllegalArgumentException("file-replace 不能声明结构化 key: " + path);
        }
        if (operation.equals("file-replace")
                && !(expectedSha256.equals("absent") || SHA256.matcher(expectedSha256).matches())) {
            throw new IllegalArgumentException("file-replace 必须声明 64 位 expectedSha256 或 absent: " + path);
        }
        if (!operation.equals("file-replace") && !expectedSha256.isBlank()) {
            throw new IllegalArgumentException("只有 file-replace 可以声明 expectedSha256: " + path);
        }
        if (!operation.equals("file-replace") && !matchesValueType(desired, valueType)) {
            throw new IllegalArgumentException("配置 desired 与 valueType 不匹配: " + path + "#" + key);
        }
        if (expected instanceof List<?> values) {
            for (Object value : values) {
                if (!matchesValueType(value, valueType)) {
                    throw new IllegalArgumentException("配置 expected 与 valueType 不匹配: " + path + "#" + key);
                }
            }
        } else if (expected != null && !matchesValueType(expected, valueType)) {
            throw new IllegalArgumentException("配置 expected 与 valueType 不匹配: " + path + "#" + key);
        }
    }

    private static boolean matchesValueType(Object value, String valueType) {
        if (value == null) {
            return true;
        }
        return switch (valueType) {
            case "boolean" -> value instanceof Boolean;
            case "integer" -> value instanceof BigDecimal number && number.scale() <= 0;
            case "decimal" -> value instanceof BigDecimal;
            case "string", "binary" -> value instanceof String;
            case "array" -> value instanceof List<?>;
            case "object" -> value instanceof Map<?, ?>;
            default -> false;
        };
    }

    private static String defaultDistributionPolicy(String type) {
        return switch (type) {
            case "publisher-hosted" -> "redistributable";
            case "manual" -> "manual";
            default -> "upstream-only";
        };
    }

    private static void rejectManualPolicy(String policy, String type, String path) {
        if (policy.equals("manual")) {
            throw new IllegalArgumentException(type + " 下载源不能使用 manual 分发策略: " + path);
        }
    }

    private static void requireFileEndpoint(List<DownloadEndpoint> endpoints, String type, String path) {
        if (endpoints.stream().noneMatch(endpoint -> endpoint.purpose().equals("file"))) {
            throw new IllegalArgumentException(type + " 下载源缺少文件端点: " + path);
        }
    }

    private static void requireIdentifier(String value, String field, String path) {
        if (value.isBlank() || value.length() > 128 || !value.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException(field + " 无效: " + path);
        }
    }

    private static URI secureUri(String value) {
        if (value.length() > 2048) {
            throw new IllegalArgumentException("下载 URL 过长");
        }
        URI uri;
        try {
            uri = URI.create(value);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("下载 URL 无效", exception);
        }
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                || uri.getUserInfo() != null || uri.getFragment() != null) {
            throw new IllegalArgumentException("下载端点必须是无凭据、无片段的 HTTPS URL: " + value);
        }
        return uri;
    }

    private static Map<String, Object> object(Object value, String field) {
        if (!(value instanceof Map<?, ?> map)) {
            throw new IllegalArgumentException(field + " 必须是对象");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> typed = (Map<String, Object>) map;
        return typed;
    }

    private static void requireOnlyKeys(Map<String, Object> object, String field, Set<String> allowed) {
        for (String key : object.keySet()) {
            if (!allowed.contains(key)) {
                throw new IllegalArgumentException(field + " 包含未知字段: " + key);
            }
        }
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

    private static Long optionalInteger(Map<String, Object> object, String field) {
        if (!object.containsKey(field) || object.get(field) == null) {
            return null;
        }
        return integer(object, field);
    }

    private static long optionalInteger(Map<String, Object> object, String field, long fallback) {
        Long value = optionalInteger(object, field);
        return value == null ? fallback : value;
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
