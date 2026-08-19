package io.github.mcmodsync;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Exact-file platform matching used only for JARs under {@code mods/}. */
final class PublisherModAutoMatcher {
    private static final String CURSEFORGE_KEY_PROPERTY = "mcsync.curseforgeApiKey";
    private static final String CURSEFORGE_KEY_ENVIRONMENT = "MCSYNC_CURSEFORGE_API_KEY";
    private final HttpClient client;

    PublisherModAutoMatcher() {
        client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).build();
    }

    record Match(Map<String, Object> download, String detail, String displayName, String descriptionEn) {
        Match {
            download = Map.copyOf(download);
            displayName = displayName == null ? "" : displayName.strip();
            descriptionEn = descriptionEn == null ? "" : descriptionEn.strip();
        }

        Match(Map<String, Object> download, String detail) {
            this(download, detail, "", "");
        }
    }

    private record Signature(String sha512, long curseForgeFingerprint) {
    }

    Match match(Path jar) {
        return matchAll(List.of(jar)).getOrDefault(jar, local("未匹配，使用本地文件"));
    }

    Map<Path, Match> matchAll(List<Path> jars) {
        LinkedHashMap<Path, Signature> readable = new LinkedHashMap<>();
        LinkedHashMap<Path, Match> result = new LinkedHashMap<>();
        for (Path jar : jars) {
            if (!Files.isRegularFile(jar) || !jar.getFileName().toString().toLowerCase().endsWith(".jar")) {
                result.put(jar, local("不是可匹配的 Mod JAR"));
                continue;
            }
            try {
                byte[] bytes = Files.readAllBytes(jar);
                readable.put(jar, new Signature(
                        digest("SHA-512", bytes), curseForgeFingerprint(bytes)));
            } catch (IOException failure) {
                result.put(jar, local("读取失败，使用本地文件"));
            }
        }
        batchModrinth(readable, result);
        batchCurseForge(readable, result);
        enrichPlatformMetadata(result);
        for (Path jar : readable.keySet()) {
            result.putIfAbsent(jar, local("未在 Modrinth/CurseForge 精确匹配，使用本地文件"));
        }
        return result;
    }

    private void enrichPlatformMetadata(Map<Path, Match> result) {
        Map<String, PlatformMetadata> cache = new LinkedHashMap<>();
        for (Map.Entry<Path, Match> item : new ArrayList<>(result.entrySet())) {
            Match match = item.getValue();
            String type = text(match.download().get("type"));
            String projectId = text(match.download().get("projectId"));
            if (projectId.isBlank() || !(type.equals("modrinth") || type.equals("curseforge"))) continue;
            String key = type + ":" + projectId;
            PlatformMetadata metadata = cache.computeIfAbsent(key, ignored -> fetchMetadata(type, projectId));
            if (metadata == null) continue;
            result.put(item.getKey(), new Match(
                    match.download(), match.detail(), metadata.displayName(), metadata.descriptionEn()));
        }
    }

    private PlatformMetadata fetchMetadata(String type, String projectId) {
        if (type.equals("modrinth")) {
            for (URI base : List.of(
                    DownloadEndpointPresets.MODRINTH_MCIMIRROR,
                    DownloadEndpointPresets.MODRINTH_OFFICIAL)) {
                try {
                    Object parsed = getJson(base.resolve("project/" + Rfc3986.encodePathSegment(projectId)), false);
                    if (!(parsed instanceof Map<?, ?> raw)) continue;
                    Map<String, Object> project = castMap(raw);
                    return new PlatformMetadata(
                            text(project.get("title")), englishText(project.get("description")));
                } catch (Exception ignored) {
                }
            }
            return null;
        }
        for (URI base : List.of(
                DownloadEndpointPresets.CURSEFORGE_MCIMIRROR,
                DownloadEndpointPresets.CURSEFORGE_OFFICIAL)) {
            URI uri = base.resolve("mods/" + Rfc3986.encodePathSegment(projectId));
            try {
                Object parsed = getJson(uri, "api.curseforge.com".equalsIgnoreCase(uri.getHost()));
                if (!(parsed instanceof Map<?, ?> root) || !(root.get("data") instanceof Map<?, ?> raw)) continue;
                Map<String, Object> project = castMap(raw);
                return new PlatformMetadata(text(project.get("name")), englishText(project.get("summary")));
            } catch (Exception ignored) {
            }
        }
        return null;
    }

    private void batchModrinth(Map<Path, Signature> jars, Map<Path, Match> result) {
        LinkedHashMap<String, Path> hashes = new LinkedHashMap<>();
        for (Map.Entry<Path, Signature> entry : jars.entrySet()) {
            hashes.put(entry.getValue().sha512(), entry.getKey());
        }
        String body = StrictJson.stringify(Map.of("hashes", new ArrayList<>(hashes.keySet()), "algorithm", "sha512"));
        for (URI base : List.of(DownloadEndpointPresets.MODRINTH_MCIMIRROR, DownloadEndpointPresets.MODRINTH_OFFICIAL)) {
            try {
                Object parsed = postJson(base.resolve("version_files"), body, false);
                if (!(parsed instanceof Map<?, ?> response)) continue;
                for (Map.Entry<?, ?> item : response.entrySet()) {
                    Path path = hashes.get(String.valueOf(item.getKey()));
                    if (path == null || result.containsKey(path) || !(item.getValue() instanceof Map<?, ?> raw)) continue;
                    Map<String, Object> object = castMap(raw);
                    String projectId = text(object.get("project_id"));
                    String versionId = text(object.get("id"));
                    if (projectId.isBlank() || versionId.isBlank()) continue;
                    LinkedHashMap<String, Object> source = new LinkedHashMap<>();
                    source.put("type", "modrinth");
                    source.put("projectId", projectId);
                    source.put("versionId", versionId);
                    source.put("distributionPolicy", "upstream-only");
                    source.put("endpoints", endpointJson(DownloadEndpointPresets.forPlatform("modrinth", true)));
                    result.put(path, new Match(source, "Modrinth 精确 SHA-512 匹配 " + projectId + "/" + versionId));
                }
                if (result.keySet().containsAll(jars.keySet())) return;
            } catch (Exception ignored) {
            }
        }
    }

    private void batchCurseForge(Map<Path, Signature> jars, Map<Path, Match> result) {
        LinkedHashMap<Long, Path> fingerprints = new LinkedHashMap<>();
        for (Map.Entry<Path, Signature> entry : jars.entrySet()) {
            if (!result.containsKey(entry.getKey())) {
                fingerprints.put(entry.getValue().curseForgeFingerprint(), entry.getKey());
            }
        }
        if (fingerprints.isEmpty()) return;
        String body = StrictJson.stringify(Map.of("fingerprints", fingerprints.keySet().stream()
                .map(BigDecimal::valueOf).toList()));
        for (URI base : List.of(DownloadEndpointPresets.CURSEFORGE_MCIMIRROR, DownloadEndpointPresets.CURSEFORGE_OFFICIAL)) {
            URI uri = base.resolve("fingerprints");
            try {
                Object parsed = postJson(uri, body, "api.curseforge.com".equalsIgnoreCase(uri.getHost()));
                if (!(parsed instanceof Map<?, ?> root) || !(root.get("data") instanceof Map<?, ?> data)
                        || !(data.get("exactMatches") instanceof List<?> matches)) continue;
                for (Object value : matches) {
                    if (!(value instanceof Map<?, ?> matchRaw)) continue;
                    Map<String, Object> match = castMap(matchRaw);
                    long projectId = integer(match.get("id"));
                    Map<String, Object> file = match.get("file") instanceof Map<?, ?> map ? castMap(map) : match;
                    long fileId = integer(file.get("id"));
                    long fingerprint = integer(file.get("fileFingerprint"));
                    Path path = fingerprints.get(fingerprint);
                    if (path == null || projectId < 1 || fileId < 1) continue;
                    LinkedHashMap<String, Object> source = new LinkedHashMap<>();
                    source.put("type", "curseforge");
                    source.put("projectId", Long.toString(projectId));
                    source.put("fileId", BigDecimal.valueOf(fileId));
                    source.put("distributionPolicy", "upstream-only");
                    source.put("endpoints", endpointJson(DownloadEndpointPresets.forPlatform("curseforge", true)));
                    result.put(path, new Match(source, "CurseForge 精确 fingerprint 匹配 " + projectId + "/" + fileId));
                }
                if (fingerprints.values().stream().allMatch(result::containsKey)) return;
            } catch (Exception ignored) {
            }
        }
    }

    private Object postJson(URI uri, String body, boolean curseForgeKey) throws IOException, InterruptedException {
        HttpRequest.Builder request = request(uri).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body));
        addCurseForgeKey(request, curseForgeKey);
        return responseJson(client.send(request.build(), HttpResponse.BodyHandlers.ofString()));
    }

    private Object getJson(URI uri, boolean curseForgeKey) throws IOException, InterruptedException {
        HttpRequest.Builder builder = request(uri).GET();
        addCurseForgeKey(builder, curseForgeKey);
        return responseJson(client.send(builder.build(), HttpResponse.BodyHandlers.ofString()));
    }

    private static HttpRequest.Builder request(URI uri) {
        return HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(15))
                .header("Accept", "application/json").header("User-Agent", BuildInfo.USER_AGENT);
    }

    private static void addCurseForgeKey(HttpRequest.Builder request, boolean needed) throws IOException {
        if (!needed) return;
        String key = System.getProperty(CURSEFORGE_KEY_PROPERTY, "").strip();
        if (key.isEmpty()) key = System.getenv().getOrDefault(CURSEFORGE_KEY_ENVIRONMENT, "").strip();
        if (key.isEmpty()) throw new IOException("CurseForge API key 未配置");
        request.header("x-api-key", key);
    }

    private static Object responseJson(HttpResponse<String> response) throws IOException {
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IOException("平台 API HTTP " + response.statusCode());
        }
        return StrictJson.parse(response.body());
    }

    static boolean isModArtifact(String path, String kind) {
        String normalized = path.replace('\\', '/').toLowerCase();
        return "mod".equals(kind) && normalized.startsWith("mods/") && normalized.endsWith(".jar")
                && normalized.indexOf('/', 5) < 0;
    }

    static Map<String, Object> localDownload() {
        return Map.of("type", "publisher-hosted", "distributionPolicy", "redistributable");
    }

    private static Match local(String detail) {
        return new Match(localDownload(), detail);
    }

    static long curseForgeFingerprint(byte[] input) {
        byte[] normalized = new byte[input.length];
        int size = 0;
        for (byte value : input) {
            if (value != 9 && value != 10 && value != 13 && value != 32) normalized[size++] = value;
        }
        int hash = 1;
        int seed = 1;
        int m = 0x5bd1e995;
        hash = seed ^ size;
        int index = 0;
        int remaining = size;
        while (remaining >= 4) {
            int k = (normalized[index] & 0xff) | ((normalized[index + 1] & 0xff) << 8)
                    | ((normalized[index + 2] & 0xff) << 16) | ((normalized[index + 3] & 0xff) << 24);
            k *= m;
            k ^= k >>> 24;
            k *= m;
            hash *= m;
            hash ^= k;
            index += 4;
            remaining -= 4;
        }
        if (remaining == 3) hash ^= (normalized[index + 2] & 0xff) << 16;
        if (remaining >= 2) hash ^= (normalized[index + 1] & 0xff) << 8;
        if (remaining >= 1) {
            hash ^= normalized[index] & 0xff;
            hash *= m;
        }
        hash ^= hash >>> 13;
        hash *= m;
        hash ^= hash >>> 15;
        return Integer.toUnsignedLong(hash);
    }

    private static String digest(String algorithm, byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance(algorithm).digest(bytes));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static List<Map<String, Object>> endpointJson(List<ReleaseManifestV5.DownloadEndpoint> endpoints) {
        ArrayList<Map<String, Object>> result = new ArrayList<>();
        for (ReleaseManifestV5.DownloadEndpoint endpoint : endpoints) {
            LinkedHashMap<String, Object> item = new LinkedHashMap<>();
            item.put("url", endpoint.uri().toASCIIString());
            item.put("role", endpoint.role());
            item.put("purpose", endpoint.purpose());
            item.put("region", endpoint.region());
            item.put("priority", BigDecimal.valueOf(endpoint.priority()));
            item.put("thirdParty", endpoint.thirdParty());
            result.add(item);
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> castMap(Map<?, ?> value) {
        return (Map<String, Object>) value;
    }

    private static String text(Object value) {
        return value instanceof String text ? text : "";
    }

    private static String englishText(Object value) {
        String text = text(value).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').strip();
        boolean containsHan = text.codePoints().anyMatch(codePoint ->
                Character.UnicodeScript.of(codePoint) == Character.UnicodeScript.HAN);
        return containsHan ? "" : text;
    }

    private static long integer(Object value) {
        if (value instanceof BigDecimal number) return number.longValue();
        if (value instanceof Number number) return number.longValue();
        return -1;
    }

    private record PlatformMetadata(String displayName, String descriptionEn) {
    }
}
