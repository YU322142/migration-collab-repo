package io.github.mcmodsync;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Resolves manifest paths inside the game root and rejects state/save traversal. */
final class ManagedPathPolicy {
    private static final Set<String> FORBIDDEN_ROOTS = Set.of(
            "saves", "world", "logs", "crash-reports", "screenshots", "backups",
            "journeymap", "xaero", "natives", "libraries", "versions", "assets");
    private static final Set<String> FORBIDDEN_EXACT = Set.of(
            "ops.json", "whitelist.json", "usercache.json", "banned-ips.json",
            "banned-players.json", "server.properties", "session.lock", "servers.dat");

    private final Path root;
    private final List<ReleaseManifestV5.ManagedScope> scopes;

    ManagedPathPolicy(Path root, List<ReleaseManifestV5.ManagedScope> scopes) throws IOException {
        this.root = root.toAbsolutePath().normalize();
        this.scopes = List.copyOf(scopes);
        Files.createDirectories(this.root);
        rejectLink(this.root);
    }

    Path resolve(String relative, boolean requireDeclaredScope) throws IOException {
        String normalized = relative.replace('\\', '/');
        String lower = normalized.toLowerCase(Locale.ROOT);
        String first = lower.contains("/") ? lower.substring(0, lower.indexOf('/')) : lower;
        if (FORBIDDEN_ROOTS.contains(first) || FORBIDDEN_EXACT.contains(lower)
                || lower.startsWith(".modsync/") || lower.equals(".modsync")) {
            throw new IOException("v5 清单试图管理禁止路径: " + relative);
        }
        if (requireDeclaredScope && !scopes.isEmpty() && scopes.stream().noneMatch(scope -> within(scope.path(), normalized))) {
            throw new IOException("文件不属于任何声明的受管范围: " + relative);
        }
        Path result = root.resolve(normalized).normalize();
        if (!result.startsWith(root)) {
            throw new IOException("文件路径逃逸游戏目录: " + relative);
        }
        Path cursor = root;
        for (Path segment : root.relativize(result)) {
            cursor = cursor.resolve(segment);
            if (Files.exists(cursor, LinkOption.NOFOLLOW_LINKS)) {
                rejectLink(cursor);
            }
        }
        return result;
    }

    boolean isManaged(String relative) {
        return policyFor(relative).equals("managed");
    }

    String policyFor(String relative) {
        return scopes.stream()
                .filter(scope -> within(scope.path(), relative))
                .sorted(java.util.Comparator.comparingInt(
                        (ReleaseManifestV5.ManagedScope scope) -> scope.path().length()).reversed())
                .map(ReleaseManifestV5.ManagedScope::policy)
                .findFirst()
                .orElse("additive");
    }

    private static boolean within(String scope, String path) {
        String normalizedScope = scope.replace('\\', '/').toLowerCase(Locale.ROOT);
        String normalizedPath = path.replace('\\', '/').toLowerCase(Locale.ROOT);
        return normalizedPath.equals(normalizedScope) || normalizedPath.startsWith(normalizedScope + "/");
    }

    private static void rejectLink(Path path) throws IOException {
        if (Files.isSymbolicLink(path)) {
            throw new IOException("受管路径不能经过符号链接或目录联接: " + path);
        }
    }
}
