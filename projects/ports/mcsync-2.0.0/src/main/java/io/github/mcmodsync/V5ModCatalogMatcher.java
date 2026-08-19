package io.github.mcmodsync;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

/** Matches imported v5 mod metadata to the actual current client without reviving deleted mods. */
final class V5ModCatalogMatcher {
    private V5ModCatalogMatcher() {
    }

    record CurrentMod(String path, String modId, String sha256) {
    }

    record MatchResult(
            Map<String, ReleaseManifestV5.FileEntry> byCurrentPath,
            Set<String> deletedImportedPaths,
            Set<String> newCurrentPaths) {
        MatchResult {
            byCurrentPath = Map.copyOf(byCurrentPath);
            deletedImportedPaths = Set.copyOf(deletedImportedPaths);
            newCurrentPaths = Set.copyOf(newCurrentPaths);
        }
    }

    static MatchResult match(List<CurrentMod> current, List<ReleaseManifestV5.FileEntry> imported) {
        Map<String, ReleaseManifestV5.FileEntry> importedByHash =
                uniqueImportedIndex(imported, entry -> normalizeHash(entry.sha256()));
        Map<String, ReleaseManifestV5.FileEntry> importedById =
                uniqueImportedIndex(imported, entry -> normalizeId(entry.modId()));
        Map<String, Integer> currentIdCounts = counts(current.stream()
                .map(item -> normalizeId(item.modId())).toList());

        LinkedHashMap<String, ReleaseManifestV5.FileEntry> matches = new LinkedHashMap<>();
        HashSet<String> usedImportedPaths = new HashSet<>();
        HashSet<String> newCurrent = new HashSet<>();
        for (CurrentMod item : current) {
            String currentPath = normalizePath(item.path());
            // File identity comes from content. A unique modId is only a metadata-migration
            // fallback for an upgraded JAR whose bytes necessarily changed; callers must still
            // re-resolve its download source from the current file fingerprint.
            ReleaseManifestV5.FileEntry match = importedByHash.get(normalizeHash(item.sha256()));
            String id = normalizeId(item.modId());
            if (match == null && !id.isBlank() && currentIdCounts.getOrDefault(id, 0) == 1) {
                match = importedById.get(id);
            }
            if (match == null || !usedImportedPaths.add(normalizePath(match.path()))) {
                newCurrent.add(currentPath);
                continue;
            }
            matches.put(currentPath, match);
        }

        HashSet<String> deleted = new HashSet<>();
        for (ReleaseManifestV5.FileEntry entry : imported) {
            String path = normalizePath(entry.path());
            if (!usedImportedPaths.contains(path)) deleted.add(path);
        }
        return new MatchResult(matches, deleted, newCurrent);
    }

    private static Map<String, ReleaseManifestV5.FileEntry> uniqueImportedIndex(
            List<ReleaseManifestV5.FileEntry> entries,
            Function<ReleaseManifestV5.FileEntry, String> keyFunction) {
        HashMap<String, List<ReleaseManifestV5.FileEntry>> grouped = new HashMap<>();
        for (ReleaseManifestV5.FileEntry entry : entries) {
            String key = keyFunction.apply(entry);
            if (!key.isBlank()) grouped.computeIfAbsent(key, ignored -> new ArrayList<>()).add(entry);
        }
        HashMap<String, ReleaseManifestV5.FileEntry> unique = new HashMap<>();
        grouped.forEach((key, values) -> {
            if (values.size() == 1) unique.put(key, values.getFirst());
        });
        return unique;
    }

    private static Map<String, Integer> counts(List<String> keys) {
        HashMap<String, Integer> counts = new HashMap<>();
        for (String key : keys) {
            if (!key.isBlank()) counts.merge(key, 1, Integer::sum);
        }
        return counts;
    }

    static String normalizePath(String path) {
        return path.replace('\\', '/').strip().toLowerCase(Locale.ROOT);
    }

    private static String normalizeId(String modId) {
        return modId == null ? "" : modId.strip().toLowerCase(Locale.ROOT);
    }

    private static String normalizeHash(String sha256) {
        if (sha256 == null) return "";
        String normalized = sha256.strip().toLowerCase(Locale.ROOT);
        return normalized.matches("[0-9a-f]{64}") ? normalized : "";
    }
}
