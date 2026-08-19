package io.github.mcmodsync;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Builds the complete immutable release, stable channel, and legacy upgrade gateway layout. */
final class PublisherCloudBundle {
    record Result(
            PublisherProjectV5.Publication publication,
            Path stableManifest,
            Path clientProperties,
            Path serverListManifest) {
    }

    private PublisherCloudBundle() {
    }

    static Result publish(
            Path gameRoot,
            Map<String, Object> project,
            Path outputRoot,
            String baseUrl,
            String stablePath,
            String legacyV4Path,
            String legacyV2Path,
            Path serverListSource,
            String serverListManifestPath,
            boolean legacyGateways,
            Path updaterJar) throws IOException {
        Path output = outputRoot.toAbsolutePath().normalize();
        ensureEmpty(output);
        String base = normalizeBase(baseUrl);
        String stableRelative = validatePath(stablePath, "mods-v5.json");
        String v4Relative = validatePath(legacyV4Path, "mods-v4.txt");
        String v2Relative = validatePath(legacyV2Path, "mods.txt");
        boolean syncServerList = serverListSource != null;
        String serverListRelative = syncServerList
                ? validatePath(serverListManifestPath, "serverlist.txt") : "";
        if (syncServerList) ServerListManifest.fromFile(serverListSource);
        if (legacyGateways) {
            if (updaterJar == null || !Files.isRegularFile(updaterJar)) {
                throw new IOException("生成旧版网关时缺少 MCSync 2.0.0 JAR");
            }
        }

        long sequence = number(project.get("releaseSequence"), "releaseSequence").longValueExact();
        Map<String, Object> remoteProject = withHostedEndpoints(project, base, sequence);
        Path releaseRoot = output.resolve("releases").resolve(Long.toString(sequence));
        PublisherProjectV5.Publication publication = PublisherProjectV5.publish(
                gameRoot, remoteProject, releaseRoot, String.valueOf(project.get("releaseId")) + ".publisher.json");

        Path stable = output.resolve(stableRelative.replace('/', java.io.File.separatorChar));
        Files.createDirectories(stable.getParent());
        Files.copy(publication.manifestPath(), stable, StandardCopyOption.REPLACE_EXISTING);
        String stableUrl = base + "/" + stableRelative;
        Path properties = output.resolve("client-modsync.properties");
        Path serverListManifest = null;
        String serverListUrl = null;
        if (syncServerList) {
            serverListManifest = output.resolve(serverListRelative.replace('/', java.io.File.separatorChar));
            Files.createDirectories(serverListManifest.getParent());
            Files.copy(serverListSource, serverListManifest.getParent().resolve(ServerListManifest.FILE_NAME),
                    StandardCopyOption.REPLACE_EXISTING);
            ServerListManifest.fromFile(serverListSource).write(serverListManifest);
            serverListUrl = base + "/" + serverListRelative;
        }
        writeClientProperties(properties, stableUrl, serverListUrl);
        if (legacyGateways) {
            ManagedClientConfig managed = ManagedClientConfig.fromPropertiesFile(properties);
            buildLegacyDirectory(output.resolve(parent(v4Relative)), updaterJar, managed, true, sequence);
            buildLegacyDirectory(output.resolve(parent(v2Relative)), updaterJar, managed, false, sequence);
        }
        writeGuide(output.resolve("REMOTE-DEPLOYMENT.md"), sequence, stableRelative, stableUrl,
                serverListRelative, legacyGateways);
        return new Result(publication, stable, properties, serverListManifest);
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> withHostedEndpoints(Map<String, Object> source, String baseUrl, long sequence) {
        LinkedHashMap<String, Object> result = new LinkedHashMap<>(source);
        String releaseBase = normalizeBase(baseUrl) + "/releases/" + sequence + "/";
        List<Object> files = ((List<Object>) source.get("files")).stream().map(raw -> {
            Map<String, Object> original = (Map<String, Object>) raw;
            LinkedHashMap<String, Object> file = new LinkedHashMap<>(original);
            Map<String, Object> originalDownload = (Map<String, Object>) original.get("download");
            LinkedHashMap<String, Object> download = new LinkedHashMap<>(originalDownload);
            if ("publisher-hosted".equals(download.get("type"))) {
                download.put("endpoints", List.of(Map.of(
                        "url", releaseBase + encodePath(String.valueOf(file.get("path"))),
                        "role", "official", "purpose", "file", "region", "global",
                        "priority", 100, "thirdParty", false)));
            }
            file.put("download", download);
            return (Object) file;
        }).toList();
        result.put("files", files);
        return result;
    }

    private static void buildLegacyDirectory(
            Path directory,
            Path updater,
            ManagedClientConfig managed,
            boolean v4,
            long releaseSequence) throws IOException {
        Files.createDirectories(directory);
        Files.copy(updater, directory.resolve("MCSync-2.0.0.jar"), StandardCopyOption.REPLACE_EXISTING);
        ManagedClientConfig.writeBootstrapJar(directory, managed);
        ModManifest catalog = ModManifest.scan(directory).withManagedClientConfig(managed)
                .withCatalogVersion(Long.toString(releaseSequence));
        if (v4) catalog.write(directory.resolve("mods-v4.txt"));
        else LegacyUpgradeManifest.write(catalog, directory.resolve("mods.txt"));
    }

    private static void writeClientProperties(Path output, String manifestUrl, String serverListManifestUrl)
            throws IOException {
        Files.writeString(output,
                "# MCSync 2.0 server-managed bootstrap\n"
                        + "manifest=" + manifestUrl + "\n"
                        + "syncResourcePacks=false\n"
                        + "syncServerList=" + (serverListManifestUrl != null) + "\n"
                        + (serverListManifestUrl == null ? ""
                                : "serverListManifest=" + serverListManifestUrl + "\n")
                        + "strict=true\n"
                        + "requireManifest=true\n",
                StandardCharsets.UTF_8);
    }

    private static void writeGuide(
            Path output,
            long sequence,
            String stablePath,
            String stableUrl,
            String serverListPath,
            boolean legacy) throws IOException {
        Files.writeString(output,
                "# MCSync cloud deployment\n\n"
                        + "Release sequence: " + sequence + "\n\n"
                        + "1. Upload `releases/" + sequence + "/` first.\n"
                        + (legacy
                                ? "2. Copy the generated files under `legacy/` to the separately managed legacy download locations.\n"
                                : "2. Legacy gateways were not generated.\n")
                        + "3. Atomically replace `" + stablePath + "` last.\n"
                        + "4. Configure clients with `manifest=" + stableUrl + "`.\n\n"
                        + (serverListPath.isBlank() ? ""
                                : "5. Upload `" + serverListPath + "` and its sibling `servers.dat`.\n\n")
                        + "Do not overwrite immutable release files. Rollback uses a new, larger releaseSequence.\n",
                StandardCharsets.UTF_8);
    }

    private static void ensureEmpty(Path output) throws IOException {
        if (!Files.exists(output)) {
            Files.createDirectories(output);
            return;
        }
        if (!Files.isDirectory(output)) throw new IOException("发布输出不是目录: " + output);
        try (var entries = Files.list(output)) {
            if (entries.findAny().isPresent()) throw new IOException("发布输出目录必须为空: " + output);
        }
    }

    private static String normalizeBase(String value) {
        String base = value == null ? "" : value.strip();
        while (base.endsWith("/")) base = base.substring(0, base.length() - 1);
        URI uri = URI.create(base);
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null || uri.getFragment() != null) {
            throw new IllegalArgumentException("公开根地址必须是无片段的 HTTPS 绝对地址");
        }
        return base;
    }

    private static String validatePath(String value, String name) {
        String path = value == null ? "" : value.strip().replace('\\', '/');
        while (path.startsWith("/")) path = path.substring(1);
        if (path.isBlank() || path.contains("..") || path.contains(":") || !path.endsWith("/" + name)) {
            throw new IllegalArgumentException("云端路径必须安全且以 /" + name + " 结尾: " + value);
        }
        return path;
    }

    private static String parent(String path) throws IOException {
        int separator = path.lastIndexOf('/');
        if (separator < 1) throw new IOException("旧版入口必须放在独立目录: " + path);
        return path.substring(0, separator);
    }

    private static String encodePath(String relative) {
        return String.join("/", Arrays.stream(relative.replace('\\', '/').split("/"))
                .map(Rfc3986::encodePathSegment).toList());
    }

    private static BigDecimal number(Object value, String name) {
        if (!(value instanceof BigDecimal number)) throw new IllegalArgumentException(name + " 必须是整数");
        return number;
    }
}
