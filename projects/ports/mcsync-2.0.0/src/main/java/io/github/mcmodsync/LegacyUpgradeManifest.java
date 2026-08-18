package io.github.mcmodsync;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Generates the permanent v2 gateway understood by the 1.6.x and 1.7
 * updaters. It contains only the current updater and its managed-config
 * bootstrap. Old managed mods can therefore be moved aside safely before the
 * upgraded client switches to the separately published complete v4 catalog.
 */
final class LegacyUpgradeManifest {
    static final String DEFAULT_FILE_NAME = "mods.txt";
    static final String MINIMUM_V4_READER_VERSION = "1.8.0";
    private static final Pattern NUMERIC_VERSION = Pattern.compile("(\\d+(?:\\.\\d+)+)");

    private LegacyUpgradeManifest() {
    }

    static String serialize(ModManifest catalog) {
        ManifestEntry updater = catalog.entries().stream()
                .filter(entry -> entry.modId().equals("mcmodsync"))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "升级清单必须包含当前 MCModSync JAR（Mod ID: mcmodsync）"));
        String targetVersion = versionOf(updater);
        if (targetVersion.isBlank()
                || compareVersions(targetVersion, MINIMUM_V4_READER_VERSION) < 0) {
            throw new IllegalArgumentException(
                    "升级清单中的 MCModSync 必须为 " + MINIMUM_V4_READER_VERSION
                            + " 或更高版本，当前识别为: "
                            + (targetVersion.isBlank() ? "未知" : targetVersion));
        }
        ManifestEntry bootstrap = catalog.entries().stream()
                .filter(entry -> entry.modId().equals(ManagedClientConfig.BOOTSTRAP_MOD_ID))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "升级清单必须包含配置引导 JAR（Mod ID: "
                                + ManagedClientConfig.BOOTSTRAP_MOD_ID + "）"));
        if (!bootstrap.fileName().equals(ManagedClientConfig.BOOTSTRAP_FILE_NAME)) {
            throw new IllegalArgumentException(
                    "配置引导 JAR 必须使用固定文件名 " + ManagedClientConfig.BOOTSTRAP_FILE_NAME);
        }

        StringBuilder builder = new StringBuilder();
        builder.append(ModManifest.MAGIC_V2).append('\n');
        builder.append("# legacy-upgrade-gateway=true\n");
        builder.append("# upgrade-components-only=true\n");
        builder.append("# target-sync-version=").append(targetVersion).append('\n');
        builder.append("# This mods.txt remains the permanent legacy upgrade gateway.\n");
        builder.append("# Old managed mods may be moved to backup during this transition.\n");
        builder.append("# Current clients restore the complete set from mods-v4.txt.\n");
        catalog.managedClientConfig().ifPresent(config ->
                builder.append(config.serializeManifestComments()));
        builder.append("# minecraft=1.21.1,1.21.11\n# loader=fabric,neoforge\n");
        for (ManifestEntry entry : List.of(updater, bootstrap)) {
            builder.append(entry.md5()).append('\t')
                    .append(entry.modId().isBlank() ? "-" : entry.modId()).append('\t')
                    .append(entry.fileName()).append('\n');
        }
        return builder.toString();
    }

    static void write(ModManifest catalog, Path output) throws IOException {
        Path normalized = output.toAbsolutePath().normalize();
        Path parent = normalized.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Files.writeString(
                normalized,
                serialize(catalog),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);
    }

    private static String versionOf(ManifestEntry updater) {
        Matcher metadata = NUMERIC_VERSION.matcher(updater.version());
        if (metadata.find()) {
            return metadata.group(1);
        }
        Matcher fileName = NUMERIC_VERSION.matcher(updater.fileName());
        return fileName.find() ? fileName.group(1) : "";
    }

    private static int compareVersions(String left, String right) {
        int[] leftParts = numericParts(left);
        int[] rightParts = numericParts(right);
        int length = Math.max(leftParts.length, rightParts.length);
        for (int index = 0; index < length; index++) {
            int leftPart = index < leftParts.length ? leftParts[index] : 0;
            int rightPart = index < rightParts.length ? rightParts[index] : 0;
            int compared = Integer.compare(leftPart, rightPart);
            if (compared != 0) {
                return compared;
            }
        }
        return 0;
    }

    private static int[] numericParts(String version) {
        String[] parts = version.split("\\.");
        int[] result = new int[parts.length];
        for (int index = 0; index < parts.length; index++) {
            result[index] = Integer.parseInt(parts[index]);
        }
        return result;
    }
}
