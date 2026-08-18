package io.github.mcmodsync;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Materializes a reviewed publisher project into a deterministic schema-v5 release directory. */
final class PublisherProjectV5 {
    private static final Set<String> ROOT_KEYS = Set.of(
            "schema", "releaseId", "releaseSequence", "minimumMCSyncVersion",
            "managedScopes", "files", "configOperations");
    private static final Set<String> FILE_KEYS = Set.of(
            "path", "kind", "required", "restartRequired", "side", "download");

    private PublisherProjectV5() {
    }

    record Publication(ReleaseManifestV5 manifest, Path manifestPath, Path reportPath, int hostedFiles) {
    }

    static Publication publish(Path gameRoot, Path projectFile, Path outputDirectory) throws IOException {
        Path root = gameRoot.toAbsolutePath().normalize();
        Path project = projectFile.toAbsolutePath().normalize();
        Path output = outputDirectory.toAbsolutePath().normalize();
        if (!Files.isDirectory(root)) throw new IOException("发布源游戏目录不存在: " + root);
        if (!Files.isRegularFile(project)) throw new IOException("v5 发布项目不存在: " + project);
        if (Files.exists(output) && (!Files.isDirectory(output) || hasEntries(output))) {
            throw new IOException("发布输出目录必须不存在或为空，避免混入旧版本文件: " + output);
        }
        Files.createDirectories(output);

        Map<String, Object> source = object(StrictJson.parse(Files.readString(project, StandardCharsets.UTF_8)), "root");
        requireKeys(source.keySet(), ROOT_KEYS, "project root");
        if (!new BigDecimal("1").equals(source.get("schema"))) {
            throw new IOException("发布项目 schema 必须为 1");
        }
        LinkedHashMap<String, Object> manifestJson = new LinkedHashMap<>();
        manifestJson.put("schema", ReleaseManifestV5.SCHEMA);
        manifestJson.put("releaseId", source.get("releaseId"));
        manifestJson.put("releaseSequence", source.get("releaseSequence"));
        manifestJson.put("minimumMCSyncVersion", source.getOrDefault("minimumMCSyncVersion", BuildInfo.VERSION));
        manifestJson.put("managedScopes", source.getOrDefault("managedScopes", List.of()));

        ManagedPathPolicy pathPolicy = new ManagedPathPolicy(root, List.of());
        List<Object> files = array(source.get("files"), "files");
        ArrayList<Object> generatedFiles = new ArrayList<>();
        LinkedHashMap<String, Path> localFiles = new LinkedHashMap<>();
        for (Object raw : files) {
            Map<String, Object> file = object(raw, "files[]");
            requireKeys(file.keySet(), FILE_KEYS, "files[]");
            Object relativeRaw = file.get("path");
            if (!(relativeRaw instanceof String relative)) throw new IOException("files[].path 必须是字符串");
            Path local = pathPolicy.resolve(relative, false);
            if (!Files.isRegularFile(local, LinkOption.NOFOLLOW_LINKS)) {
                throw new IOException("发布项目中的文件不存在或不是普通文件: " + relative);
            }
            LinkedHashMap<String, Object> generated = new LinkedHashMap<>(file);
            generated.put("sha256", Hashing.sha256(local));
            generated.put("size", Files.size(local));
            generatedFiles.add(generated);
            localFiles.put(relative, local);
        }
        manifestJson.put("files", generatedFiles);
        manifestJson.put("configOperations", source.getOrDefault("configOperations", List.of()));
        ReleaseManifestV5 manifest;
        try {
            manifest = ReleaseManifestV5.parse(
                    (StrictJson.stringify(manifestJson) + "\n").getBytes(StandardCharsets.UTF_8));
        } catch (IllegalArgumentException failure) {
            throw new IOException("发布项目无法生成有效 v5 清单: " + failure.getMessage(), failure);
        }

        int hosted = 0;
        for (ReleaseManifestV5.FileEntry file : manifest.files()) {
            if (!file.download().type().equals("publisher-hosted")) continue;
            Path destination = output.resolve(file.path()).normalize();
            if (!destination.startsWith(output)) throw new IOException("发布目标路径逃逸: " + file.path());
            Files.createDirectories(destination.getParent());
            Files.copy(localFiles.get(file.path()), destination, StandardCopyOption.COPY_ATTRIBUTES);
            if (!Hashing.sha256(destination).equals(file.sha256())) {
                throw new IOException("发布复制后哈希不一致: " + file.path());
            }
            hosted++;
        }
        Path manifestPath = output.resolve("manifest-v5.json");
        Files.write(manifestPath, manifest.serialize());
        LinkedHashMap<String, Object> report = new LinkedHashMap<>();
        report.put("schema", 1);
        report.put("status", "PASS");
        report.put("generatedAt", Instant.now().toString());
        report.put("sourceRoot", root.toString());
        report.put("project", project.toString());
        report.put("releaseId", manifest.releaseId());
        report.put("releaseSequence", manifest.releaseSequence());
        report.put("manifestSha256", Hashing.sha256(manifestPath));
        report.put("fileCount", manifest.files().size());
        report.put("publisherHostedFileCount", hosted);
        report.put("downloadSourceTypes", manifest.files().stream()
                .map(file -> file.download().type()).collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new)));
        Path reportPath = output.resolve("publication-report.json");
        Files.writeString(reportPath, StrictJson.stringify(report) + "\n", StandardCharsets.UTF_8);
        return new Publication(manifest, manifestPath, reportPath, hosted);
    }

    static void writeTemplate(Path output) throws IOException {
        String template = """
                {
                  "schema": 1,
                  "releaseId": "motiquies-2.0.0-ota.1",
                  "releaseSequence": 2000001,
                  "minimumMCSyncVersion": "2.0.0",
                  "managedScopes": [
                    {"path":"mods","policy":"managed"},
                    {"path":"resourcepacks","policy":"managed"},
                    {"path":"shaderpacks","policy":"managed"},
                    {"path":"kubejs","policy":"managed"},
                    {"path":"config","policy":"additive"},
                    {"path":"defaultconfigs","policy":"additive"}
                  ],
                  "files": [
                    {
                      "path":"mods/our-adapted-mod.jar",
                      "kind":"mod","required":true,"restartRequired":true,"side":["client"],
                      "download":{"type":"publisher-hosted","distributionPolicy":"redistributable"}
                    },
                    {
                      "path":"mods/upstream-mod.jar",
                      "kind":"mod","required":true,"restartRequired":true,"side":["client"],
                      "download":{
                        "type":"modrinth","projectId":"PROJECT_ID","versionId":"VERSION_ID",
                        "distributionPolicy":"upstream-only",
                        "endpoints":[
                          {"url":"https://mod.mcimirror.top/modrinth/v2/","role":"mirror","purpose":"api","region":"cn","priority":10,"thirdParty":true},
                          {"url":"https://api.modrinth.com/v2/","role":"official","purpose":"api","region":"global","priority":100}
                        ]
                      }
                    }
                  ],
                  "configOperations": []
                }
                """;
        Files.createDirectories(output.toAbsolutePath().normalize().getParent());
        Files.writeString(output, template, StandardCharsets.UTF_8);
    }

    private static boolean hasEntries(Path directory) throws IOException {
        try (var stream = Files.list(directory)) {
            return stream.findAny().isPresent();
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value, String where) throws IOException {
        if (!(value instanceof Map<?, ?> map)) throw new IOException(where + " 必须是 JSON 对象");
        return (Map<String, Object>) map;
    }

    @SuppressWarnings("unchecked")
    private static List<Object> array(Object value, String where) throws IOException {
        if (!(value instanceof List<?> list)) throw new IOException(where + " 必须是 JSON 数组");
        return (List<Object>) list;
    }

    private static void requireKeys(Set<String> actual, Set<String> allowed, String where) throws IOException {
        Set<String> unknown = new LinkedHashSet<>(actual);
        unknown.removeAll(allowed);
        if (!unknown.isEmpty()) throw new IOException(where + " 包含未知字段: " + unknown);
    }
}
