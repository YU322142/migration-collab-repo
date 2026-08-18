package io.github.mcmodsync;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

record ModSyncConfig(
        URI manifestUri,
        URI resourcePackManifestUri,
        URI serverListManifestUri,
        Path gameDirectory,
        Path configurationDirectory,
        boolean syncResourcePacks,
        boolean syncServerList,
        boolean strict,
        boolean requireManifest,
        Duration connectTimeout,
        Duration requestTimeout,
        long maxManifestBytes,
        long maxFileBytes,
        int fileOperationRetries) {

    ModSyncConfig forGameDirectory(Path directory) {
        return new ModSyncConfig(
                manifestUri,
                resourcePackManifestUri,
                serverListManifestUri,
                directory.toAbsolutePath().normalize(),
                configurationDirectory,
                syncResourcePacks,
                syncServerList,
                strict,
                requireManifest,
                connectTimeout,
                requestTimeout,
                maxManifestBytes,
                maxFileBytes,
                fileOperationRetries);
    }

    /**
     * Safe placeholder only. Deployments must configure their own manifests in
     * {@code modsync.properties} or through agent/system properties.
     */
    static final URI DEFAULT_MANIFEST_URI = URI.create("https://example.invalid/mcmodsync/mods-v4.txt");

    /** Default mods manifest used when RuntimeEnvironment detects mobile (Zalith/Pojav/etc.). */
    static final URI DEFAULT_MOBILE_MANIFEST_URI = URI.create("https://example.invalid/mcmodsync/mobile-mods-v4.txt");

    static final URI DEFAULT_RESOURCE_PACK_MANIFEST_URI = URI.create(
            "https://example.invalid/mcmodsync/resourcepacks.txt");

    /** Default resource-pack manifest when RuntimeEnvironment detects mobile. */
    static final URI DEFAULT_MOBILE_RESOURCE_PACK_MANIFEST_URI = URI.create(
            "https://example.invalid/mcmodsync/mobile-resourcepacks.txt");

    static final URI DEFAULT_SERVER_LIST_MANIFEST_URI = URI.create(
            "https://example.invalid/mcmodsync/serverlist.txt");

    private static final Pattern GAME_DIR_ARGUMENT = Pattern.compile(
            "(?:^|\\s)--gameDir(?:=|\\s+)(?:\"([^\"]+)\"|'([^']+)'|(.+?))(?=\\s+--\\S+|$)");

    static ModSyncConfig fromEnvironment(String agentArguments) {
        return fromEnvironment(agentArguments, null);
    }

    static ModSyncConfig fromEnvironment(String agentArguments, Path detectedGameDirectory) {
        Map<String, String> agent = parseAgentArguments(agentArguments);
        Path gameDirectory = determineGameDirectory(agent, detectedGameDirectory);

        Properties fileProperties = new Properties();
        Path propertiesPath = gameDirectory.resolve("modsync.properties");
        if (Files.isRegularFile(propertiesPath)) {
            try {
                fileProperties = PropertiesFiles.load(propertiesPath);
            } catch (IOException exception) {
                throw new IllegalArgumentException("无法读取配置文件: " + propertiesPath, exception);
            }
        }

        boolean mobileRuntime = isMobileRuntime();
        String manifest = resolveManifest(agent, fileProperties, mobileRuntime);
        String resourcePackManifest = resolveResourcePackManifest(agent, fileProperties, mobileRuntime);
        boolean syncResourcePacks = parseBoolean(
                resolve("syncResourcePacks", agent, fileProperties, "true"),
                "syncResourcePacks");
        String serverListManifest = resolve(
                "serverListManifest",
                agent,
                fileProperties,
                DEFAULT_SERVER_LIST_MANIFEST_URI.toASCIIString());
        boolean syncServerList = parseBoolean(
                resolve("syncServerList", agent, fileProperties, "true"),
                "syncServerList");
        boolean strict = parseBoolean(resolve("strict", agent, fileProperties, "true"), "strict");
        boolean requireManifest = parseBoolean(
                resolve("requireManifest", agent, fileProperties, "true"),
                "requireManifest");
        long connectTimeoutSeconds = parseLong(
                resolve("connectTimeoutSeconds", agent, fileProperties, "15"),
                "connectTimeoutSeconds",
                1,
                300);
        long requestTimeoutSeconds = parseLong(
                resolve("requestTimeoutSeconds", agent, fileProperties, "300"),
                "requestTimeoutSeconds",
                5,
                3600);
        long maxFileBytes = parseLong(
                resolve("maxFileBytes", agent, fileProperties, Long.toString(Long.MAX_VALUE)),
                "maxFileBytes",
                1,
                Long.MAX_VALUE);
        int retries = (int) parseLong(
                resolve("fileOperationRetries", agent, fileProperties, "12"),
                "fileOperationRetries",
                1,
                60);

        URI manifestUri = parseHttpUri(manifest, "manifest");
        URI resourcePackManifestUri = parseHttpUri(resourcePackManifest, "resourcePackManifest");
        URI serverListManifestUri = parseHttpUri(serverListManifest, "serverListManifest");

        return new ModSyncConfig(
                manifestUri,
                resourcePackManifestUri,
                serverListManifestUri,
                gameDirectory,
                gameDirectory,
                syncResourcePacks,
                syncServerList,
                strict,
                requireManifest,
                Duration.ofSeconds(connectTimeoutSeconds),
                Duration.ofSeconds(requestTimeoutSeconds),
                1024 * 1024,
                maxFileBytes,
                retries);
    }

    private static boolean isMobileRuntime() {
        if (Boolean.getBoolean("modsync.forceMobile")) {
            return true;
        }
        try {
            return RuntimeEnvironment.detect().mobile();
        } catch (Throwable ignored) {
            return false;
        }
    }

    /**
     * Desktop default stays the PC mods list. Mobile uses the phone list unless the
     * operator explicitly overrides with {@code mobileManifest} or a non-default
     * {@code manifest} when they intentionally want one list on all platforms.
     */
    private static String resolveManifest(
            Map<String, String> agent,
            Properties fileProperties,
            boolean mobileRuntime) {
        boolean manifestExplicit = isExplicit("manifest", agent, fileProperties);
        boolean mobileManifestExplicit = isExplicit("mobileManifest", agent, fileProperties);

        if (mobileRuntime) {
            if (mobileManifestExplicit) {
                return resolve(
                        "mobileManifest",
                        agent,
                        fileProperties,
                        DEFAULT_MOBILE_MANIFEST_URI.toASCIIString());
            }
            if (manifestExplicit) {
                // Explicit desktop-style manifest= still honored (shared list / testing).
                return resolve("manifest", agent, fileProperties, DEFAULT_MANIFEST_URI.toASCIIString());
            }
            return DEFAULT_MOBILE_MANIFEST_URI.toASCIIString();
        }

        return resolve("manifest", agent, fileProperties, DEFAULT_MANIFEST_URI.toASCIIString());
    }

    /**
     * Desktop default stays the PC resource-pack list. Mobile uses the phone
     * resource-pack directory unless overridden by {@code mobileResourcePackManifest}
     * or an explicit {@code resourcePackManifest}.
     */
    private static String resolveResourcePackManifest(
            Map<String, String> agent,
            Properties fileProperties,
            boolean mobileRuntime) {
        boolean resourcePackExplicit = isExplicit("resourcePackManifest", agent, fileProperties);
        boolean mobileResourcePackExplicit = isExplicit(
                "mobileResourcePackManifest", agent, fileProperties);

        if (mobileRuntime) {
            if (mobileResourcePackExplicit) {
                return resolve(
                        "mobileResourcePackManifest",
                        agent,
                        fileProperties,
                        DEFAULT_MOBILE_RESOURCE_PACK_MANIFEST_URI.toASCIIString());
            }
            if (resourcePackExplicit) {
                return resolve(
                        "resourcePackManifest",
                        agent,
                        fileProperties,
                        DEFAULT_RESOURCE_PACK_MANIFEST_URI.toASCIIString());
            }
            return DEFAULT_MOBILE_RESOURCE_PACK_MANIFEST_URI.toASCIIString();
        }

        return resolve(
                "resourcePackManifest",
                agent,
                fileProperties,
                DEFAULT_RESOURCE_PACK_MANIFEST_URI.toASCIIString());
    }

    private static boolean isExplicit(
            String key,
            Map<String, String> agent,
            Properties fileProperties) {
        String agentValue = agent.get(key.toLowerCase(Locale.ROOT));
        if (agentValue != null && !agentValue.isBlank()) {
            return true;
        }
        String systemValue = System.getProperty("modsync." + key);
        if (systemValue != null && !systemValue.isBlank()) {
            return true;
        }
        String fileValue = fileProperties.getProperty(key);
        return fileValue != null && !fileValue.isBlank();
    }

    private static URI parseHttpUri(String value, String name) {
        URI uri;
        try {
            uri = URI.create(value);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(name + " 不是有效网址: " + value, exception);
        }
        if (!uri.isAbsolute()
                || !(uri.getScheme().equalsIgnoreCase("https") || uri.getScheme().equalsIgnoreCase("http"))) {
            throw new IllegalArgumentException(name + " 必须是绝对 HTTP/HTTPS 地址: " + value);
        }
        return uri;
    }

    private static Path determineGameDirectory(Map<String, String> agent, Path detectedGameDirectory) {
        String explicit = agent.get("gamedir");
        // When a loader (or tests) already resolved the real game directory, that
        // wins over a stale modsync.gameDir system property. Agent gamedir= still wins.
        if ((explicit == null || explicit.isBlank()) && detectedGameDirectory != null) {
            return detectedGameDirectory.toAbsolutePath().normalize();
        }
        if (explicit == null || explicit.isBlank()) {
            explicit = System.getProperty("modsync.gameDir");
        }
        if (explicit == null || explicit.isBlank()) {
            String command = System.getProperty("sun.java.command", "");
            Matcher matcher = GAME_DIR_ARGUMENT.matcher(command);
            if (matcher.find()) {
                explicit = matcher.group(1) != null
                        ? matcher.group(1)
                        : matcher.group(2) != null ? matcher.group(2) : matcher.group(3);
            }
        }
        if (explicit == null || explicit.isBlank()) {
            explicit = System.getProperty("user.dir", ".");
        }
        return Path.of(explicit.strip()).toAbsolutePath().normalize();
    }

    static Path determineGameDirectory(String agentArguments, Path detectedGameDirectory) {
        return determineGameDirectory(parseAgentArguments(agentArguments), detectedGameDirectory);
    }

    private static String resolve(
            String key,
            Map<String, String> agent,
            Properties fileProperties,
            String defaultValue) {
        String agentValue = agent.get(key.toLowerCase(Locale.ROOT));
        if (agentValue != null) {
            return agentValue;
        }
        String systemValue = System.getProperty("modsync." + key);
        if (systemValue != null) {
            return systemValue;
        }
        return fileProperties.getProperty(key, defaultValue);
    }

    private static Map<String, String> parseAgentArguments(String arguments) {
        Map<String, String> result = new LinkedHashMap<>();
        if (arguments == null || arguments.isBlank()) {
            return result;
        }
        for (String part : arguments.split(";")) {
            if (part.isBlank()) {
                continue;
            }
            int separator = part.indexOf('=');
            if (separator <= 0 || separator == part.length() - 1) {
                throw new IllegalArgumentException("Agent 参数格式错误，应为 key=value，多个参数用分号分隔: " + part);
            }
            result.put(
                    part.substring(0, separator).strip().toLowerCase(Locale.ROOT),
                    part.substring(separator + 1).strip());
        }
        return result;
    }

    private static boolean parseBoolean(String value, String name) {
        if (value.equalsIgnoreCase("true")) {
            return true;
        }
        if (value.equalsIgnoreCase("false")) {
            return false;
        }
        throw new IllegalArgumentException(name + " 必须是 true 或 false");
    }

    private static long parseLong(String value, String name, long minimum, long maximum) {
        try {
            long parsed = Long.parseLong(value);
            if (parsed < minimum || parsed > maximum) {
                throw new IllegalArgumentException(name + " 必须介于 " + minimum + " 与 " + maximum + " 之间");
            }
            return parsed;
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(name + " 必须是整数: " + value, exception);
        }
    }
}
