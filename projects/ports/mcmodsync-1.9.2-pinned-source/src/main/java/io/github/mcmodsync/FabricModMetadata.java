package io.github.mcmodsync;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

final class FabricModMetadata {
    private static final int MAX_METADATA_BYTES = 1024 * 1024;
    private static final Pattern MOD_ID = Pattern.compile("[a-z][a-z0-9_-]{1,63}");

    private FabricModMetadata() {
    }

    static String readModId(Path jar) {
        String id = readTopLevelString(jar, "id").toLowerCase(Locale.ROOT);
        return MOD_ID.matcher(id).matches() ? id : "";
    }

    static String readVersion(Path jar) {
        return readTopLevelString(jar, "version");
    }

    static String readName(Path jar) {
        return readTopLevelString(jar, "name");
    }

    static String readDescription(Path jar) {
        return readTopLevelString(jar, "description")
                .replace('\r', ' ')
                .replace('\n', ' ')
                .replace('\t', ' ')
                .strip();
    }

    private static String readTopLevelString(Path jar, String field) {
        try (ZipFile zip = new ZipFile(jar.toFile())) {
            ZipEntry entry = zip.getEntry("fabric.mod.json");
            if (entry == null || entry.isDirectory() || entry.getSize() > MAX_METADATA_BYTES) {
                return "";
            }
            byte[] bytes;
            try (InputStream input = zip.getInputStream(entry)) {
                bytes = input.readNBytes(MAX_METADATA_BYTES + 1);
            }
            if (bytes.length > MAX_METADATA_BYTES) {
                return "";
            }
            String value = new JsonReader(new String(bytes, StandardCharsets.UTF_8)).topLevelString(field);
            return value == null ? "" : value.strip();
        } catch (IOException | IllegalArgumentException exception) {
            return "";
        }
    }

    static boolean isValidModId(String value) {
        return value != null && MOD_ID.matcher(value).matches();
    }

    private static final class JsonReader {
        private final String text;
        private int position;

        private JsonReader(String text) {
            this.text = text;
        }

        String topLevelString(String target) {
            skipWhitespace();
            expect('{');
            skipWhitespace();
            if (consume('}')) {
                return null;
            }
            while (true) {
                String key = readString();
                skipWhitespace();
                expect(':');
                skipWhitespace();
                if (key.equals(target) && peek() == '"') {
                    return readString();
                }
                skipValue(0);
                skipWhitespace();
                if (consume('}')) {
                    return null;
                }
                expect(',');
                skipWhitespace();
            }
        }

        private void skipValue(int depth) {
            if (depth > 64) {
                throw new IllegalArgumentException("JSON nesting too deep");
            }
            skipWhitespace();
            char current = peek();
            if (current == '"') {
                readString();
                return;
            }
            if (current == '{') {
                position++;
                skipWhitespace();
                if (consume('}')) {
                    return;
                }
                while (true) {
                    readString();
                    skipWhitespace();
                    expect(':');
                    skipValue(depth + 1);
                    skipWhitespace();
                    if (consume('}')) {
                        return;
                    }
                    expect(',');
                    skipWhitespace();
                }
            }
            if (current == '[') {
                position++;
                skipWhitespace();
                if (consume(']')) {
                    return;
                }
                while (true) {
                    skipValue(depth + 1);
                    skipWhitespace();
                    if (consume(']')) {
                        return;
                    }
                    expect(',');
                    skipWhitespace();
                }
            }
            int start = position;
            while (position < text.length()) {
                current = text.charAt(position);
                if (current == ',' || current == '}' || current == ']' || Character.isWhitespace(current)) {
                    break;
                }
                position++;
            }
            if (position == start) {
                throw new IllegalArgumentException("Invalid JSON value");
            }
        }

        private String readString() {
            skipWhitespace();
            expect('"');
            StringBuilder result = new StringBuilder();
            while (position < text.length()) {
                char current = text.charAt(position++);
                if (current == '"') {
                    return result.toString();
                }
                if (current != '\\') {
                    if (current < 0x20) {
                        throw new IllegalArgumentException("Control character in JSON string");
                    }
                    result.append(current);
                    continue;
                }
                if (position >= text.length()) {
                    throw new IllegalArgumentException("Invalid JSON escape");
                }
                char escaped = text.charAt(position++);
                switch (escaped) {
                    case '"', '\\', '/' -> result.append(escaped);
                    case 'b' -> result.append('\b');
                    case 'f' -> result.append('\f');
                    case 'n' -> result.append('\n');
                    case 'r' -> result.append('\r');
                    case 't' -> result.append('\t');
                    case 'u' -> result.append(readUnicodeEscape());
                    default -> throw new IllegalArgumentException("Invalid JSON escape");
                }
            }
            throw new IllegalArgumentException("Unterminated JSON string");
        }

        private char readUnicodeEscape() {
            if (position + 4 > text.length()) {
                throw new IllegalArgumentException("Invalid unicode escape");
            }
            int value = 0;
            for (int index = 0; index < 4; index++) {
                int digit = Character.digit(text.charAt(position++), 16);
                if (digit < 0) {
                    throw new IllegalArgumentException("Invalid unicode escape");
                }
                value = (value << 4) | digit;
            }
            return (char) value;
        }

        private char peek() {
            if (position >= text.length()) {
                throw new IllegalArgumentException("Unexpected end of JSON");
            }
            return text.charAt(position);
        }

        private void expect(char expected) {
            if (position >= text.length() || text.charAt(position) != expected) {
                throw new IllegalArgumentException("Expected '" + expected + "'");
            }
            position++;
        }

        private boolean consume(char expected) {
            if (position < text.length() && text.charAt(position) == expected) {
                position++;
                return true;
            }
            return false;
        }

        private void skipWhitespace() {
            while (position < text.length() && Character.isWhitespace(text.charAt(position))) {
                position++;
            }
        }
    }
}
