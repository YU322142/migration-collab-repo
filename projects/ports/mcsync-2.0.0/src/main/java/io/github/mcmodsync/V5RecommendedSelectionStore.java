package io.github.mcmodsync;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;
import java.util.Set;

/**
 * Keeps schema-v5 recommended-Mod choices separate from the release sequence.
 * A first-time or newly added recommendation creates a pending request consumed
 * by the Minecraft-window UI. Ordinary version/hash/description updates and
 * removals retain the player's existing choices without prompting again.
 */
final class V5RecommendedSelectionStore {
    private static final String STATE_FILE = "recommended-selection-v5.properties";
    private static final String PENDING_FILE = "recommended-selection-v5-pending.json";
    private static final String SELECTED_PREFIX = "selected.";
    private static final String KNOWN_PREFIX = "known.";

    private V5RecommendedSelectionStore() {
    }

    static Resolution resolve(
            ReleaseManifestV5 manifest,
            Path gameDirectory,
            RuntimeEnvironment environment) throws IOException {
        List<ReleaseManifestV5.FileEntry> recommended = manifest.files().stream()
                .filter(ReleaseManifestV5.FileEntry::optionalSelectable)
                .toList();
        if (recommended.isEmpty()) {
            Files.deleteIfExists(pendingPath(gameDirectory));
            return new Resolution(manifest, false, Set.of());
        }

        ClientPlatform platform = ClientPlatform.current(environment);
        String fingerprint = fingerprint(recommended);
        SavedSelection saved = load(statePath(gameDirectory));
        Set<String> compatible = new LinkedHashSet<>();
        for (ReleaseManifestV5.FileEntry entry : recommended) {
            if (!entry.incompatiblePlatforms().contains(platformId(platform))) {
                compatible.add(entry.selectionKey());
            }
        }

        if (environment.mobile() || !InGameRecommendedSelection.supported()) {
            save(statePath(gameDirectory), new SavedSelection(fingerprint, platform, compatible, compatible));
            Files.deleteIfExists(pendingPath(gameDirectory));
            return new Resolution(filter(manifest, compatible, platform), false, Set.copyOf(compatible));
        }

        if (saved != null && saved.platform() == platform) {
            Set<String> selected = new LinkedHashSet<>(saved.selected());
            selected.retainAll(compatible);
            LinkedHashSet<String> newlyAdded = new LinkedHashSet<>(compatible);
            newlyAdded.removeAll(saved.known());
            if (newlyAdded.isEmpty()) {
                // A recommendation's version/hash/description may change without
                // changing the player's opt-in decision. Removed or newly
                // incompatible recommendations are silently pruned here.
                save(statePath(gameDirectory), new SavedSelection(
                        fingerprint, platform, selected, compatible));
                Files.deleteIfExists(pendingPath(gameDirectory));
                return new Resolution(filter(manifest, selected, platform), false, Set.copyOf(selected));
            }
        }

        Set<String> previous = new LinkedHashSet<>();
        if (saved != null && saved.platform() == platform) {
            previous.addAll(saved.selected());
            previous.retainAll(compatible);
        }
        Set<String> defaults = new LinkedHashSet<>(previous);
        if (saved == null || saved.platform() != platform) {
            defaults.addAll(compatible);
        } else {
            LinkedHashSet<String> newlyAdded = new LinkedHashSet<>(compatible);
            newlyAdded.removeAll(saved.known());
            defaults.addAll(newlyAdded); // only newly added recommendations default selected
        }
        writePending(pendingPath(gameDirectory), manifest, fingerprint, platform, recommended, defaults);
        return new Resolution(filter(manifest, previous, platform), true, Set.copyOf(previous));
    }

    static PendingSelection readPending(Path gameDirectory) throws IOException {
        Path path = pendingPath(gameDirectory);
        if (!Files.isRegularFile(path)) return null;
        Map<String, Object> root = object(StrictJson.parse(Files.readString(path, StandardCharsets.UTF_8)));
        String fingerprint = string(root, "catalogFingerprint");
        ClientPlatform platform = ClientPlatform.parse(string(root, "platform"));
        List<PendingMod> mods = new ArrayList<>();
        for (Object raw : array(root.get("mods"))) {
            Map<String, Object> item = object(raw);
            mods.add(new PendingMod(
                    string(item, "key"),
                    string(item, "kind"),
                    string(item, "fileName"),
                    string(item, "displayName"),
                    string(item, "version"),
                    string(item, "descriptionZh"),
                    string(item, "descriptionEn"),
                    Boolean.TRUE.equals(item.get("compatible")),
                    Boolean.TRUE.equals(item.get("selected"))));
        }
        return new PendingSelection(fingerprint, platform, mods);
    }

    static void confirm(Path gameDirectory, PendingSelection pending, Set<String> selected) throws IOException {
        LinkedHashSet<String> allowed = new LinkedHashSet<>();
        for (PendingMod mod : pending.mods()) if (mod.compatible()) allowed.add(mod.key());
        LinkedHashSet<String> accepted = new LinkedHashSet<>(selected);
        accepted.retainAll(allowed);
        save(statePath(gameDirectory), new SavedSelection(
                pending.catalogFingerprint(), pending.platform(), accepted, allowed));
        Files.deleteIfExists(pendingPath(gameDirectory));
    }

    private static ReleaseManifestV5 filter(
            ReleaseManifestV5 manifest,
            Set<String> selected,
            ClientPlatform platform) {
        List<ReleaseManifestV5.FileEntry> effective = new ArrayList<>();
        String platformId = platformId(platform);
        for (ReleaseManifestV5.FileEntry entry : manifest.files()) {
            if (!entry.optionalSelectable()) {
                effective.add(entry);
            } else if (selected.contains(entry.selectionKey())
                    && !entry.incompatiblePlatforms().contains(platformId)) {
                effective.add(entry);
            }
        }
        return manifest.withFiles(effective);
    }

    private static void writePending(
            Path path,
            ReleaseManifestV5 manifest,
            String fingerprint,
            ClientPlatform platform,
            List<ReleaseManifestV5.FileEntry> recommended,
            Set<String> defaults) throws IOException {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("schema", 1);
        root.put("releaseId", manifest.releaseId());
        root.put("releaseSequence", manifest.releaseSequence());
        root.put("catalogFingerprint", fingerprint);
        root.put("platform", platform.id());
        List<Object> mods = new ArrayList<>();
        String platformId = platformId(platform);
        for (ReleaseManifestV5.FileEntry entry : recommended) {
            boolean compatible = !entry.incompatiblePlatforms().contains(platformId);
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("key", entry.selectionKey());
            item.put("kind", entry.kind());
            item.put("fileName", Path.of(entry.path()).getFileName().toString());
            item.put("displayName", entry.displayName().isBlank() ? entry.selectionKey() : entry.displayName());
            item.put("version", entry.version());
            item.put("descriptionZh", entry.descriptionZh());
            item.put("descriptionEn", entry.descriptionEn());
            item.put("compatible", compatible);
            item.put("selected", compatible && defaults.contains(entry.selectionKey()));
            mods.add(item);
        }
        root.put("mods", mods);
        atomicWrite(path, (StrictJson.stringify(root) + "\n").getBytes(StandardCharsets.UTF_8));
    }

    private static String fingerprint(List<ReleaseManifestV5.FileEntry> recommended) {
        StringBuilder value = new StringBuilder();
        recommended.stream().sorted(java.util.Comparator.comparing(ReleaseManifestV5.FileEntry::selectionKey))
                .forEach(entry -> value.append(entry.selectionKey()).append('\t')
                        .append(entry.incompatiblePlatforms().stream().sorted().toList()).append('\n'));
        return Hashing.sha256(value.toString().getBytes(StandardCharsets.UTF_8));
    }

    private static String platformId(ClientPlatform platform) {
        return switch (platform) {
            case WINDOWS -> "windows";
            case MAC -> "macos";
            case LINUX -> "linux";
            case MOBILE -> "android";
        };
    }

    private static SavedSelection load(Path path) {
        if (!Files.isRegularFile(path)) return null;
        Properties properties = new Properties();
        try (InputStream input = Files.newInputStream(path)) {
            properties.load(input);
            String fingerprint = properties.getProperty("catalogFingerprint", "").strip();
            ClientPlatform platform = ClientPlatform.parse(properties.getProperty("platform", ""));
            LinkedHashSet<String> selected = new LinkedHashSet<>();
            LinkedHashSet<String> known = new LinkedHashSet<>();
            for (String name : properties.stringPropertyNames()) {
                if (name.startsWith(SELECTED_PREFIX) && Boolean.parseBoolean(properties.getProperty(name))) {
                    selected.add(decode(name.substring(SELECTED_PREFIX.length())));
                } else if (name.startsWith(KNOWN_PREFIX) && Boolean.parseBoolean(properties.getProperty(name))) {
                    known.add(decode(name.substring(KNOWN_PREFIX.length())));
                }
            }
            if (known.isEmpty()) known.addAll(selected); // compatibility with early 2.0 development state
            return fingerprint.isBlank() ? null : new SavedSelection(fingerprint, platform, selected, known);
        } catch (IOException | IllegalArgumentException failure) {
            return null;
        }
    }

    private static void save(Path path, SavedSelection selection) throws IOException {
        Properties properties = new Properties();
        properties.setProperty("catalogFingerprint", selection.catalogFingerprint());
        properties.setProperty("platform", selection.platform().id());
        for (String key : selection.selected()) {
            properties.setProperty(SELECTED_PREFIX + encode(key), "true");
        }
        for (String key : selection.known()) {
            properties.setProperty(KNOWN_PREFIX + encode(key), "true");
        }
        Files.createDirectories(path.getParent());
        Path temporary = path.resolveSibling("." + path.getFileName() + ".tmp");
        try (OutputStream output = Files.newOutputStream(temporary)) {
            properties.store(output, "MCSync v5 recommended mod selection");
        }
        moveAtomic(temporary, path);
    }

    private static void atomicWrite(Path path, byte[] bytes) throws IOException {
        Files.createDirectories(path.getParent());
        Path temporary = path.resolveSibling("." + path.getFileName() + ".tmp");
        Files.write(temporary, bytes);
        moveAtomic(temporary, path);
    }

    private static void moveAtomic(Path source, Path target) throws IOException {
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (java.nio.file.AtomicMoveNotSupportedException failure) {
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static Path statePath(Path gameDirectory) {
        return gameDirectory.resolve(".modsync").resolve(STATE_FILE);
    }

    static Path pendingPath(Path gameDirectory) {
        return gameDirectory.resolve(".modsync").resolve(PENDING_FILE);
    }

    private static String encode(String value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String decode(String value) {
        return new String(Base64.getUrlDecoder().decode(value), StandardCharsets.UTF_8);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        if (!(value instanceof Map<?, ?> map)) throw new IllegalArgumentException("pending selection object expected");
        return (Map<String, Object>) map;
    }

    @SuppressWarnings("unchecked")
    private static List<Object> array(Object value) {
        if (!(value instanceof List<?> list)) throw new IllegalArgumentException("pending selection array expected");
        return (List<Object>) list;
    }

    private static String string(Map<String, Object> object, String key) {
        Object value = object.get(key);
        return value instanceof String text ? text : "";
    }

    record Resolution(ReleaseManifestV5 effectiveManifest, boolean selectionPending, Set<String> selected) {
        Resolution {
            selected = Set.copyOf(selected);
        }
    }

    record PendingSelection(String catalogFingerprint, ClientPlatform platform, List<PendingMod> mods) {
        PendingSelection {
            mods = List.copyOf(mods);
        }
    }

    record PendingMod(
            String key,
            String kind,
            String fileName,
            String displayName,
            String version,
            String descriptionZh,
            String descriptionEn,
            boolean compatible,
            boolean selected) {
        String typeLabel(DisplayLanguage language) {
            return switch (kind) {
                case "resource-pack" -> language.text("资源包", "Resource pack");
                case "shader-pack" -> language.text("光影包", "Shader pack");
                default -> language.text("推荐模组", "Recommended mod");
            };
        }

        String description(DisplayLanguage language) {
            String preferred = language.chinese() ? descriptionZh : descriptionEn;
            String fallback = language.chinese() ? descriptionEn : descriptionZh;
            return preferred.isBlank() ? fallback : preferred;
        }
    }

    private record SavedSelection(
            String catalogFingerprint,
            ClientPlatform platform,
            Set<String> selected,
            Set<String> known) {
        private SavedSelection {
            selected = Set.copyOf(selected);
            known = Set.copyOf(known);
        }
    }
}
