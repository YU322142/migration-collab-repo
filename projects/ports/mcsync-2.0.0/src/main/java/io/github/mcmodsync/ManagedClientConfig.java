package io.github.mcmodsync;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Properties;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

/**
 * Server-managed, deliberately small subset of modsync.properties.
 *
 * File-size limits, timeouts, language and retry settings are intentionally
 * local-only and can never be supplied by a catalog.
 */
final class ManagedClientConfig {
    static final String BOOTSTRAP_MOD_ID = "mcmodsync_config";
    static final String BOOTSTRAP_FILE_NAME = "MCModSync-Config.jar";
    static final String BOOTSTRAP_RESOURCE = "mcmodsync/bootstrap.properties";
    static final String MANIFEST_FILE_NAME = "mods-v4.txt";
    private static final String CATALOG_PREFIX = "# client-config.";
    private static final int MAX_BOOTSTRAP_BYTES = 64 * 1024;
    private static final List<String> MANAGED_KEYS = List.of(
            "manifest",
            "mobileManifest",
            "syncResourcePacks",
            "resourcePackManifest",
            "mobileResourcePackManifest",
            "syncServerList",
            "serverListManifest",
            "strict",
            "requireManifest");
    private static final Set<String> URL_KEYS = Set.of(
            "manifest",
            "mobileManifest",
            "resourcePackManifest",
            "mobileResourcePackManifest",
            "serverListManifest");
    private static final Set<String> BOOLEAN_KEYS = Set.of(
            "syncResourcePacks",
            "syncServerList",
            "strict",
            "requireManifest");

    private final Map<String, String> values;

    private ManagedClientConfig(Map<String, String> values) {
        this.values = Map.copyOf(values);
    }

    static ManagedClientConfig fromPropertiesFile(Path path) throws IOException {
        if (!Files.isRegularFile(path)) {
            throw new IOException("找不到用于发布的客户端配置模板: " + path);
        }
        Properties properties = PropertiesFiles.load(path);
        Map<String, String> selected = new LinkedHashMap<>();
        for (String key : MANAGED_KEYS) {
            String value = properties.getProperty(key);
            if (value != null && !value.isBlank()) {
                selected.put(key, value.strip());
            }
        }
        return validated(selected, "配置模板 " + path);
    }

    static Optional<ManagedClientConfig> fromManifestText(String text) {
        Map<String, String> selected = new LinkedHashMap<>();
        for (String line : text.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1)) {
            String stripped = line.strip();
            if (!stripped.startsWith(CATALOG_PREFIX)) {
                continue;
            }
            int separator = stripped.indexOf('=', CATALOG_PREFIX.length());
            if (separator < 0) {
                throw new IllegalArgumentException("客户端配置行缺少 =: " + stripped);
            }
            String key = stripped.substring(CATALOG_PREFIX.length(), separator).strip();
            String value = stripped.substring(separator + 1).strip();
            if (!MANAGED_KEYS.contains(key)) {
                throw new IllegalArgumentException("清单包含不允许远程管理的配置项: " + key);
            }
            if (selected.putIfAbsent(key, value) != null) {
                throw new IllegalArgumentException("清单重复声明客户端配置项: " + key);
            }
        }
        return selected.isEmpty()
                ? Optional.empty()
                : Optional.of(validated(selected, "v4 清单"));
    }

    static boolean installFromBootstrapJar(Path gameDirectory, Consumer<String> logger) throws IOException {
        Path mods = gameDirectory.toAbsolutePath().normalize().resolve("mods");
        Path bootstrap = mods.resolve(BOOTSTRAP_FILE_NAME);
        if (!Files.isRegularFile(bootstrap)) {
            return false;
        }
        Optional<ManagedClientConfig> found = readBootstrap(bootstrap);
        if (found.isEmpty()) {
            throw new IOException("固定配置引导 JAR 缺少 " + BOOTSTRAP_RESOURCE + ": " + bootstrap);
        }
        boolean changed = found.get().apply(gameDirectory);
        DisplayLanguage language = DisplayLanguage.detect(gameDirectory);
        logger.accept(changed
                ? language.text(
                        "已从配置引导 JAR 自动创建或更新 modsync.properties",
                        "Created or updated modsync.properties from the configuration bootstrap JAR")
                : language.text(
                        "配置引导 JAR 与本地 modsync.properties 已一致",
                        "The configuration bootstrap JAR already matches local modsync.properties"));
        return changed;
    }

    static ManifestEntry writeBootstrapJar(Path modsDirectory, ManagedClientConfig config) throws IOException {
        Path normalized = modsDirectory.toAbsolutePath().normalize();
        Files.createDirectories(normalized);
        Path output = normalized.resolve(BOOTSTRAP_FILE_NAME);
        byte[] jarBytes = config.bootstrapJarBytes();
        if (!Files.isRegularFile(output) || !java.util.Arrays.equals(Files.readAllBytes(output), jarBytes)) {
            Path temporary = normalized.resolve("." + BOOTSTRAP_FILE_NAME + "." + UUID.randomUUID() + ".tmp");
            try {
                Files.write(temporary, jarBytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
                moveReplacing(temporary, output);
            } finally {
                Files.deleteIfExists(temporary);
            }
        }
        Optional<ManagedClientConfig> verified = readBootstrap(output);
        if (verified.isEmpty() || !verified.get().equals(config)) {
            throw new IOException("配置引导 JAR 写入后校验失败: " + output);
        }
        return new ManifestEntry(
                Hashing.sha256(output),
                Hashing.md5(output),
                BOOTSTRAP_MOD_ID,
                BOOTSTRAP_FILE_NAME,
                ModKind.REQUIRED,
                Set.of(),
                "MCModSync Client Configuration",
                "1.0.0",
                "MCModSync 客户端配置引导；由发布器自动维护",
                "MCModSync client configuration bootstrap; maintained by the publisher");
    }

    String serializeManifestComments() {
        StringBuilder result = new StringBuilder();
        for (String key : MANAGED_KEYS) {
            String value = values.get(key);
            if (value != null) {
                result.append(CATALOG_PREFIX).append(key).append('=').append(value).append('\n');
            }
        }
        return result.toString();
    }

    boolean apply(Path gameDirectory) throws IOException {
        Path output = gameDirectory.toAbsolutePath().normalize().resolve("modsync.properties");
        Properties properties = Files.isRegularFile(output)
                ? PropertiesFiles.load(output)
                : new Properties();

        boolean changed = false;
        for (String key : MANAGED_KEYS) {
            String desired = values.get(key);
            String current = properties.getProperty(key);
            if (desired == null) {
                if (current != null) {
                    properties.remove(key);
                    changed = true;
                }
            } else if (!desired.equals(current)) {
                properties.setProperty(key, desired);
                changed = true;
            }
        }
        if (!changed) {
            return false;
        }

        Path parent = output.getParent();
        Files.createDirectories(parent);
        Path temporary = parent.resolve("." + output.getFileName() + "." + UUID.randomUUID() + ".tmp");
        try {
            try (OutputStream stream = Files.newOutputStream(
                    temporary, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                properties.store(stream,
                        "MCModSync server-managed keys are refreshed automatically; local-only keys are preserved.");
            }
            moveReplacing(temporary, output);
        } finally {
            Files.deleteIfExists(temporary);
        }
        System.setProperty("modsync.managedConfigChanged", "true");
        return true;
    }

    Map<String, String> values() {
        return values;
    }

    private static ManagedClientConfig validated(Map<String, String> source, String description) {
        Map<String, String> normalized = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : source.entrySet()) {
            if (!MANAGED_KEYS.contains(entry.getKey())) {
                throw new IllegalArgumentException(description + " 包含不允许远程管理的配置项: " + entry.getKey());
            }
            String value = entry.getValue() == null ? "" : entry.getValue().strip();
            if (value.isEmpty() || value.indexOf('\n') >= 0 || value.indexOf('\r') >= 0) {
                throw new IllegalArgumentException(description + " 的配置值无效: " + entry.getKey());
            }
            normalized.put(entry.getKey(), value);
        }
        normalized.putIfAbsent("syncResourcePacks", "false");
        normalized.putIfAbsent("syncServerList", "false");
        normalized.putIfAbsent("strict", "true");
        normalized.putIfAbsent("requireManifest", "true");

        String manifest = normalized.get("manifest");
        if (manifest == null) {
            throw new IllegalArgumentException(description + " 必须提供 manifest");
        }
        URI manifestUri = validateHttpUri(manifest, "manifest", description);
        String path = manifestUri.getPath();
        if (path == null || !path.endsWith("/" + MANIFEST_FILE_NAME)) {
            throw new IllegalArgumentException(description + " 的 manifest 必须指向 " + MANIFEST_FILE_NAME);
        }

        for (String key : URL_KEYS) {
            String value = normalized.get(key);
            if (value != null) {
                validateHttpUri(value, key, description);
            }
        }
        for (String key : BOOLEAN_KEYS) {
            String value = normalized.get(key);
            if (!value.equalsIgnoreCase("true") && !value.equalsIgnoreCase("false")) {
                throw new IllegalArgumentException(description + " 的 " + key + " 必须为 true 或 false");
            }
            normalized.put(key, Boolean.toString(Boolean.parseBoolean(value)));
        }
        if (!Boolean.parseBoolean(normalized.get("requireManifest"))) {
            throw new IllegalArgumentException(description + " 不允许 requireManifest=false");
        }
        if (Boolean.parseBoolean(normalized.get("syncResourcePacks"))
                && !normalized.containsKey("resourcePackManifest")) {
            throw new IllegalArgumentException(description + " 启用资源包同步时必须提供 resourcePackManifest");
        }
        if (Boolean.parseBoolean(normalized.get("syncServerList"))
                && !normalized.containsKey("serverListManifest")) {
            throw new IllegalArgumentException(description + " 启用服务器列表同步时必须提供 serverListManifest");
        }
        return new ManagedClientConfig(normalized);
    }

    private static URI validateHttpUri(String value, String key, String description) {
        try {
            URI uri = URI.create(value);
            if (!uri.isAbsolute()
                    || !(uri.getScheme().equalsIgnoreCase("http") || uri.getScheme().equalsIgnoreCase("https"))
                    || uri.getFragment() != null) {
                throw new IllegalArgumentException();
            }
            return uri;
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(description + " 的 " + key + " 必须是无片段的 HTTP/HTTPS 绝对地址");
        }
    }

    private static Optional<ManagedClientConfig> readBootstrap(Path jar) throws IOException {
        try (ZipFile zip = new ZipFile(jar.toFile())) {
            ZipEntry entry = zip.getEntry(BOOTSTRAP_RESOURCE);
            if (entry == null || entry.isDirectory()) {
                return Optional.empty();
            }
            byte[] bytes;
            try (InputStream input = zip.getInputStream(entry)) {
                bytes = input.readNBytes(MAX_BOOTSTRAP_BYTES + 1);
            }
            if (bytes.length > MAX_BOOTSTRAP_BYTES) {
                throw new IOException("配置引导内容超过安全大小限制: " + jar);
            }
            Properties properties = new Properties();
            properties.load(new java.io.StringReader(new String(bytes, StandardCharsets.UTF_8)));
            Map<String, String> selected = new LinkedHashMap<>();
            for (String name : properties.stringPropertyNames()) {
                if (!MANAGED_KEYS.contains(name)) {
                    throw new IOException("配置引导 JAR 包含不允许的配置项: " + name);
                }
                selected.put(name, properties.getProperty(name));
            }
            return Optional.of(validated(selected, "配置引导 JAR " + jar.getFileName()));
        } catch (IllegalArgumentException exception) {
            throw new IOException("配置引导 JAR 无效: " + jar + ": " + exception.getMessage(), exception);
        }
    }

    private byte[] bootstrapJarBytes() throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(output, StandardCharsets.UTF_8)) {
            putEntry(zip, "fabric.mod.json", ("{\n"
                    + "  \"schemaVersion\": 1,\n"
                    + "  \"id\": \"" + BOOTSTRAP_MOD_ID + "\",\n"
                    + "  \"version\": \"1.0.0\",\n"
                    + "  \"name\": \"MCModSync Client Configuration\",\n"
                    + "  \"description\": \"MCModSync managed client configuration bootstrap\",\n"
                    + "  \"environment\": \"client\"\n"
                    + "}\n").getBytes(StandardCharsets.UTF_8));
            // The bootstrap JAR has metadata but no @Mod class. NeoForge's
            // lowcode loader is the supported metadata-only language loader.
            putEntry(zip, "META-INF/neoforge.mods.toml", ("modLoader=\"lowcodefml\"\n"
                    + "loaderVersion=\"[1,)\"\n"
                    + "license=\"MIT\"\n"
                    + "[[mods]]\n"
                    + "modId=\"" + BOOTSTRAP_MOD_ID + "\"\n"
                    + "version=\"1.0.0\"\n"
                    + "displayName=\"MCModSync Client Configuration\"\n"
                    + "description=\"MCModSync managed client configuration bootstrap\"\n"
                    + "[[dependencies." + BOOTSTRAP_MOD_ID + "]]\n"
                    + "modId=\"neoforge\"\n"
                    + "type=\"required\"\n"
                    + "versionRange=\"[21.1.0,)\"\n"
                    + "ordering=\"NONE\"\n"
                    + "side=\"CLIENT\"\n"
                    + "[[dependencies." + BOOTSTRAP_MOD_ID + "]]\n"
                    + "modId=\"minecraft\"\n"
                    + "type=\"required\"\n"
                    + "versionRange=\"[1.21.1]\"\n"
                    + "ordering=\"NONE\"\n"
                    + "side=\"CLIENT\"\n").getBytes(StandardCharsets.UTF_8));
            StringBuilder properties = new StringBuilder();
            for (String key : MANAGED_KEYS) {
                String value = values.get(key);
                if (value != null) {
                    properties.append(key).append('=').append(value).append('\n');
                }
            }
            putEntry(zip, BOOTSTRAP_RESOURCE, properties.toString().getBytes(StandardCharsets.UTF_8));
        }
        return output.toByteArray();
    }

    private static void putEntry(ZipOutputStream zip, String name, byte[] bytes) throws IOException {
        ZipEntry entry = new ZipEntry(name);
        entry.setTime(0L);
        zip.putNextEntry(entry);
        zip.write(bytes);
        zip.closeEntry();
    }

    private static void moveReplacing(Path source, Path target) throws IOException {
        try {
            Files.move(source, target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof ManagedClientConfig config && values.equals(config.values);
    }

    @Override
    public int hashCode() {
        return values.hashCode();
    }
}
