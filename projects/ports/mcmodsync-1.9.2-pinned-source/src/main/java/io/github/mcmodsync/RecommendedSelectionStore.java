package io.github.mcmodsync;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;

final class RecommendedSelectionStore {
    private static final String FILE_NAME = "recommended-selection.properties";
    private static final String SELECTED_PREFIX = "selected.";
    private static final Map<String, Set<String>> SESSION_SELECTIONS = new ConcurrentHashMap<>();

    private RecommendedSelectionStore() {
    }

    static Resolution resolve(
            ModManifest manifest,
            Path gameDirectory,
            Map<String, Path> localByName,
            URI manifestUri,
            RuntimeEnvironment environment,
            SyncObserver observer,
            Consumer<String> logger) throws IOException {
        List<ManifestEntry> recommended = manifest.entries().stream()
                .filter(ManifestEntry::recommended)
                .toList();
        if (recommended.isEmpty()) {
            return new Resolution(manifest, Set.of(), false, "", gameDirectory);
        }

        ClientPlatform platform = ClientPlatform.current(environment);
        DisplayLanguage language = DisplayLanguage.detect(gameDirectory);
        Path statePath = statePath(gameDirectory);
        SavedSelection saved = load(statePath);
        boolean sameCatalog = saved != null
                && saved.catalogVersion().equals(manifest.catalogVersion())
                && saved.platform() == platform
                && saved.mobile() == environment.mobile();
        if (saved != null && !saved.catalogVersion().equals(manifest.catalogVersion())) {
            logger.accept(language.text(
                    "推荐清单版本更新: ",
                    "Recommended catalog version updated: ")
                    + saved.catalogVersion() + " -> " + manifest.catalogVersion());
        } else if (saved == null) {
            logger.accept(language.text(
                    "首次读取推荐清单，版本: ",
                    "First recommended catalog, version: ") + manifest.catalogVersion());
        }

        Set<String> compatibleDefaults = new LinkedHashSet<>();
        for (ManifestEntry entry : recommended) {
            if (entry.compatibleWith(platform)) {
                compatibleDefaults.add(entry.selectionKey());
            }
        }

        Set<String> selected;
        boolean mobileCompleted;
        if (sameCatalog) {
            selected = new LinkedHashSet<>(saved.selected());
            mobileCompleted = saved.mobileCompleted();
            if (!environment.mobile()) {
                SESSION_SELECTIONS.put(
                        sessionKey(manifestUri, manifest.catalogVersion(), platform),
                        Set.copyOf(selected));
            }
        } else if (!environment.mobile()) {
            String sessionKey = sessionKey(manifestUri, manifest.catalogVersion(), platform);
            Set<String> session = SESSION_SELECTIONS.get(sessionKey);
            if (session != null) {
                selected = new LinkedHashSet<>(session);
            } else {
                RecommendedSelectionRequest request = new RecommendedSelectionRequest(
                        saved == null ? "" : saved.catalogVersion(),
                        manifest.catalogVersion(),
                        platform,
                        recommended,
                        compatibleDefaults);
                selected = new LinkedHashSet<>(observer.chooseRecommendedMods(request));
                SESSION_SELECTIONS.put(sessionKey, Set.copyOf(selected));
            }
            selected.retainAll(compatibleDefaults);
            mobileCompleted = false;
            save(statePath, new SavedSelection(
                    manifest.catalogVersion(), platform, false, false, selected));
        } else {
            selected = new LinkedHashSet<>(compatibleDefaults);
            mobileCompleted = false;
            save(statePath, new SavedSelection(
                    manifest.catalogVersion(), platform, true, false, selected));
            logger.accept(language.text(
                    "手机端推荐清单将自动处理一次，共 ",
                    "The mobile recommended catalog will be processed once; ")
                    + selected.size()
                    + language.text(" 个兼容推荐模组", " compatible recommended mod(s)"));
        }

        // A stale/tampered saved state can never override cloud incompatibility.
        selected.retainAll(compatibleDefaults);

        List<ManifestEntry> effective = new ArrayList<>();
        Set<String> excluded = new HashSet<>();
        for (ManifestEntry entry : manifest.entries()) {
            if (!entry.recommended()) {
                effective.add(entry);
                continue;
            }
            String selectionKey = entry.selectionKey();
            if (!selected.contains(selectionKey) || !entry.compatibleWith(platform)) {
                excluded.add(selectionKey);
                continue;
            }
            if (environment.mobile() && mobileCompleted) {
                Path local = localByName.get(entry.fileName().toLowerCase(java.util.Locale.ROOT));
                boolean matches;
                try {
                    matches = local != null && ModManifest.fileMatches(entry, local);
                } catch (IOException exception) {
                    matches = false;
                }
                if (!matches) {
                    excluded.add(selectionKey);
                    logManualMobileInstall(entry, manifestUri, gameDirectory, language, logger);
                    continue;
                }
            }
            effective.add(entry);
        }

        boolean mobileNeedsCompletion = environment.mobile() && !mobileCompleted;
        return new Resolution(
                manifest.withEntries(effective),
                Set.copyOf(excluded),
                mobileNeedsCompletion,
                manifest.catalogVersion(),
                gameDirectory);
    }

    private static void logManualMobileInstall(
            ManifestEntry entry,
            URI manifestUri,
            Path gameDirectory,
            DisplayLanguage language,
            Consumer<String> logger) {
        URI download = manifestUri.resolve("./" + Rfc3986.encodePathSegment(entry.fileName()));
        logger.accept(language.text(
                "手机端推荐模组已被删除或校验失败，不会再次自动下载: ",
                "A mobile recommended mod was deleted or failed verification and will not be downloaded again: ")
                + entry.displayName() + " (" + entry.fileName() + ")");
        logger.accept(language.text("手动下载地址: ", "Manual download: ") + download);
        logger.accept(language.text(
                "手动安装方式: 下载后校验 SHA256=",
                "Manual installation: verify SHA256=")
                + entry.sha256()
                + language.text("，再将文件放入 ", ", then place the file in ")
                + gameDirectory.resolve("mods"));
    }

    static void markMobileCompleted(Resolution resolution) throws IOException {
        if (!resolution.mobileNeedsCompletion()) {
            return;
        }
        Path path = statePath(resolution.gameDirectory());
        SavedSelection current = load(path);
        if (current == null || !current.mobile()
                || !current.catalogVersion().equals(resolution.catalogVersion())) {
            return;
        }
        save(path, new SavedSelection(
                current.catalogVersion(),
                current.platform(),
                true,
                true,
                current.selected()));
    }

    private static SavedSelection load(Path path) {
        if (!Files.isRegularFile(path)) {
            return null;
        }
        Properties properties = new Properties();
        try (InputStream input = Files.newInputStream(path)) {
            properties.load(input);
            String version = properties.getProperty("catalogVersion", "").strip();
            ClientPlatform platform = ClientPlatform.parse(properties.getProperty("platform", ""));
            boolean mobile = Boolean.parseBoolean(properties.getProperty("mobile", "false"));
            boolean completed = Boolean.parseBoolean(properties.getProperty("mobileCompleted", "false"));
            Set<String> selected = new LinkedHashSet<>();
            for (String name : properties.stringPropertyNames()) {
                if (name.startsWith(SELECTED_PREFIX)
                        && Boolean.parseBoolean(properties.getProperty(name))) {
                    selected.add(decodeKey(name.substring(SELECTED_PREFIX.length())));
                }
            }
            if (version.isBlank()) {
                return null;
            }
            return new SavedSelection(version, platform, mobile, completed, selected);
        } catch (IOException | IllegalArgumentException exception) {
            return null;
        }
    }

    private static void save(Path path, SavedSelection selection) throws IOException {
        Files.createDirectories(path.getParent());
        Properties properties = new Properties();
        properties.setProperty("catalogVersion", selection.catalogVersion());
        properties.setProperty("platform", selection.platform().id());
        properties.setProperty("mobile", Boolean.toString(selection.mobile()));
        properties.setProperty("mobileCompleted", Boolean.toString(selection.mobileCompleted()));
        for (String key : selection.selected()) {
            properties.setProperty(SELECTED_PREFIX + encodeKey(key), "true");
        }
        Path temporary = path.resolveSibling("." + path.getFileName() + ".tmp");
        try (OutputStream output = Files.newOutputStream(temporary)) {
            properties.store(output, "MCModSync recommended mod selection");
        }
        try {
            Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (java.nio.file.AtomicMoveNotSupportedException exception) {
            Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static Path statePath(Path gameDirectory) {
        return gameDirectory.resolve(".modsync").resolve(FILE_NAME);
    }

    private static String sessionKey(URI manifestUri, String version, ClientPlatform platform) {
        return manifestUri.toASCIIString() + "\n" + version + "\n" + platform.id();
    }

    private static String encodeKey(String value) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String decodeKey(String value) {
        return new String(Base64.getUrlDecoder().decode(value), StandardCharsets.UTF_8);
    }

    static void resetSessionForTests() {
        SESSION_SELECTIONS.clear();
    }

    record Resolution(
            ModManifest effectiveManifest,
            Set<String> excludedRecommendedKeys,
            boolean mobileNeedsCompletion,
            String catalogVersion,
            Path gameDirectory) {
    }

    private record SavedSelection(
            String catalogVersion,
            ClientPlatform platform,
            boolean mobile,
            boolean mobileCompleted,
            Set<String> selected) {
        private SavedSelection {
            selected = Set.copyOf(selected);
        }
    }
}
