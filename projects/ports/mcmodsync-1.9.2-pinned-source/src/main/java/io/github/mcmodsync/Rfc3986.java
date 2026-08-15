package io.github.mcmodsync;

import java.nio.charset.StandardCharsets;

final class Rfc3986 {
    private static final char[] HEX = "0123456789ABCDEF".toCharArray();

    private Rfc3986() {
    }

    static String encodePathSegment(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        StringBuilder result = new StringBuilder(bytes.length);
        for (byte item : bytes) {
            int current = item & 0xff;
            if ((current >= 'a' && current <= 'z')
                    || (current >= 'A' && current <= 'Z')
                    || (current >= '0' && current <= '9')
                    || current == '-' || current == '.' || current == '_' || current == '~') {
                result.append((char) current);
            } else {
                result.append('%');
                result.append(HEX[current >>> 4]);
                result.append(HEX[current & 0x0f]);
            }
        }
        return result.toString();
    }
}
