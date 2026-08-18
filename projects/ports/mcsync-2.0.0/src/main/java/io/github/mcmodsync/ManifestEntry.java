package io.github.mcmodsync;

import java.util.Locale;
import java.util.Set;

record ManifestEntry(
        String sha256,
        String md5,
        String modId,
        String fileName,
        ModKind kind,
        Set<ClientPlatform> incompatiblePlatforms,
        String displayName,
        String version,
        String descriptionZh,
        String descriptionEn) {

    ManifestEntry {
        sha256 = clean(sha256);
        md5 = clean(md5).toLowerCase(Locale.ROOT);
        modId = clean(modId).toLowerCase(Locale.ROOT);
        fileName = clean(fileName);
        kind = kind == null ? ModKind.REQUIRED : kind;
        incompatiblePlatforms = incompatiblePlatforms == null
                ? Set.of()
                : Set.copyOf(incompatiblePlatforms);
        displayName = fallback(clean(displayName), modId, fileName);
        version = clean(version);
        descriptionZh = cleanMultiline(descriptionZh);
        descriptionEn = cleanMultiline(descriptionEn);
    }

    ManifestEntry(
            String sha256,
            String md5,
            String modId,
            String fileName,
            ModKind kind,
            Set<ClientPlatform> incompatiblePlatforms,
            String displayName,
            String version,
            String legacyDescription) {
        this(
                sha256,
                md5,
                modId,
                fileName,
                kind,
                incompatiblePlatforms,
                displayName,
                version,
                legacyDescriptionZh(legacyDescription),
                legacyDescriptionEn(legacyDescription));
    }

    ManifestEntry(String md5, String modId, String fileName) {
        this("", md5, modId, fileName, ModKind.REQUIRED, Set.of(), modId, "", "", "");
    }

    boolean recommended() {
        return kind == ModKind.RECOMMENDED;
    }

    boolean compatibleWith(ClientPlatform platform) {
        return !incompatiblePlatforms.contains(platform);
    }

    String selectionKey() {
        return modId.isBlank() ? fileName.toLowerCase(Locale.ROOT) : modId;
    }

    String localizedDescription(DisplayLanguage language) {
        String preferred = language == DisplayLanguage.ZH_CN ? descriptionZh : descriptionEn;
        String fallback = language == DisplayLanguage.ZH_CN ? descriptionEn : descriptionZh;
        return preferred.isBlank() ? fallback : preferred;
    }

    private static String clean(String value) {
        return value == null ? "" : value.strip();
    }

    private static String cleanMultiline(String value) {
        return clean(value).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ');
    }

    private static String fallback(String preferred, String modId, String fileName) {
        if (!preferred.isBlank()) {
            return preferred;
        }
        if (!modId.isBlank()) {
            return modId;
        }
        return fileName;
    }

    private static String legacyDescriptionZh(String value) {
        String cleaned = cleanMultiline(value);
        return containsHan(cleaned) ? cleaned : "";
    }

    private static String legacyDescriptionEn(String value) {
        String cleaned = cleanMultiline(value);
        return containsHan(cleaned) ? "" : cleaned;
    }

    private static boolean containsHan(String value) {
        return value.codePoints().anyMatch(codePoint ->
                Character.UnicodeScript.of(codePoint) == Character.UnicodeScript.HAN);
    }
}
