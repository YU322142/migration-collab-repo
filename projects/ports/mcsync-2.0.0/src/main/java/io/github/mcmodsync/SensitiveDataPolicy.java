package io.github.mcmodsync;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/** Prevents release manifests and hosted config snapshots from becoming credential distribution channels. */
final class SensitiveDataPolicy {
    private static final Set<String> SENSITIVE_SEGMENTS = Set.of(
            "token", "password", "passwd", "secret", "credential", "credentials",
            "apikey", "api_key", "accesskey", "access_key", "privatekey", "private_key",
            "authtoken", "auth_token");
    private static final Pattern JSON_KEY = Pattern.compile(
            "(?i)\\\"(?:token|password|passwd|secret|credential|credentials|api[_-]?key|access[_-]?key|private[_-]?key|auth[_-]?token)\\\"\\s*:");
    private static final Pattern TEXT_KEY = Pattern.compile(
            "(?im)^\\s*(?:token|password|passwd|secret|credential|credentials|api[_-]?key|access[_-]?key|private[_-]?key|auth[_-]?token)\\s*[=:]");

    private SensitiveDataPolicy() {
    }

    static void rejectSensitiveConfigKey(String key) {
        if (key == null || key.isBlank()) return;
        for (String segment : key.toLowerCase(Locale.ROOT).split("[._-]")) {
            if (SENSITIVE_SEGMENTS.contains(segment)
                    || segment.endsWith("token") || segment.endsWith("password")
                    || segment.endsWith("secret") || segment.endsWith("credential")
                    || segment.endsWith("apikey")) {
                throw new IllegalArgumentException("凭据键禁止通过 MCSync OTA 管理: " + key);
            }
        }
        String normalized = key.toLowerCase(Locale.ROOT).replace('-', '_');
        if (SENSITIVE_SEGMENTS.contains(normalized)) {
            throw new IllegalArgumentException("凭据键禁止通过 MCSync OTA 管理: " + key);
        }
    }

    static boolean looksLikeCredentialDocument(byte[] bytes) {
        if (bytes.length == 0 || bytes.length > 4 * 1024 * 1024) return false;
        String text = new String(bytes, StandardCharsets.UTF_8);
        return JSON_KEY.matcher(text).find() || TEXT_KEY.matcher(text).find();
    }
}
