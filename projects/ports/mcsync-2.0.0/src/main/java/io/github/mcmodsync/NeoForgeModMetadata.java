package io.github.mcmodsync;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * Reads the small, stable metadata subset used by NeoForge 1.21.x.
 *
 * NeoForge metadata is TOML rather than JSON.  MCModSync deliberately parses
 * only the first [[mods]] table and the four display fields it needs; it does
 * not attempt to be a general TOML implementation.  The input is bounded and
 * quoted values are parsed with a small state machine so comments and tabs in
 * descriptions cannot change the resulting fields.
 */
final class NeoForgeModMetadata {
    private static final int MAX_METADATA_BYTES = 1024 * 1024;
    private static final String ENTRY_NAME = "META-INF/neoforge.mods.toml";

    private NeoForgeModMetadata() {
    }

    static String readModId(Path jar) {
        return readField(jar, "modId").toLowerCase(Locale.ROOT);
    }

    static String readVersion(Path jar) {
        String value = readField(jar, "version");
        if (value.equals("${file.jarVersion}")) {
            return jarVersion(jar);
        }
        return value;
    }

    static String readName(Path jar) {
        String value = readField(jar, "displayName");
        if (value.isBlank()) {
            value = readModId(jar);
        }
        return value;
    }

    static String readDescription(Path jar) {
        return normalize(readField(jar, "description"));
    }

    static boolean isNetworkOptional(Path jar) {
        String value = readField(jar, "displayTest").strip().toUpperCase(Locale.ROOT);
        return value.equals("IGNORE_ALL_VERSION") || value.equals("IGNORE_SERVER_VERSION");
    }

    private static String readField(Path jar, String field) {
        try (ZipFile zip = new ZipFile(jar.toFile())) {
            ZipEntry entry = zip.getEntry(ENTRY_NAME);
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
            return new TomlModsReader(new String(bytes, StandardCharsets.UTF_8)).read(field);
        } catch (IOException | IllegalArgumentException exception) {
            return "";
        }
    }

    private static String jarVersion(Path jar) {
        try (JarFile archive = new JarFile(jar.toFile())) {
            Attributes attributes = archive.getManifest() == null
                    ? null
                    : archive.getManifest().getMainAttributes();
            if (attributes == null) {
                return "";
            }
            String value = attributes.getValue(Attributes.Name.IMPLEMENTATION_VERSION);
            return value == null ? "" : value.strip();
        } catch (IOException exception) {
            return "";
        }
    }

    private static String normalize(String value) {
        return value.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').strip();
    }

    private static final class TomlModsReader {
        private final String text;
        private final Map<String, String> fields = new LinkedHashMap<>();
        private boolean inMods;
        private boolean finished;

        private TomlModsReader(String text) {
            this.text = text;
        }

        String read(String field) {
            parse();
            return fields.getOrDefault(field, "").strip();
        }

        private void parse() {
            String[] lines = text.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1);
            for (int index = 0; index < lines.length && !finished; index++) {
                String line = lines[index];
                String stripped = line.strip();
                if (stripped.equals("[[mods]]")) {
                    if (inMods) {
                        finished = true;
                    } else {
                        inMods = true;
                    }
                    continue;
                }
                if (!inMods || stripped.isEmpty() || stripped.startsWith("#")) {
                    continue;
                }
                // Any following table marks the end of the first mod record.
                if (stripped.startsWith("[") && !stripped.startsWith("[[mods]]")) {
                    finished = true;
                    continue;
                }
                int equals = findEqualsOutsideQuotes(line);
                if (equals < 0) {
                    continue;
                }
                String key = line.substring(0, equals).strip();
                if (!key.equals("modId") && !key.equals("version")
                        && !key.equals("displayName") && !key.equals("description")
                        && !key.equals("displayTest")) {
                    continue;
                }
                String raw = line.substring(equals + 1).strip();
                ParsedValue value = parseValue(raw, lines, index);
                fields.putIfAbsent(key, value.value());
                index = value.lastLine();
            }
        }

        private static int findEqualsOutsideQuotes(String line) {
            char quote = 0;
            boolean escaped = false;
            for (int index = 0; index < line.length(); index++) {
                char current = line.charAt(index);
                if (quote == '"' && escaped) {
                    escaped = false;
                    continue;
                }
                if (quote == '"' && current == '\\') {
                    escaped = true;
                    continue;
                }
                if ((current == '\'' || current == '"') && (quote == 0 || quote == current)) {
                    quote = quote == 0 ? current : 0;
                } else if (current == '=' && quote == 0) {
                    return index;
                }
            }
            return -1;
        }

        private static ParsedValue parseValue(String raw, String[] lines, int lineNumber) {
            if (raw.startsWith("'''") || raw.startsWith("\"\"\"")) {
                String delimiter = raw.substring(0, 3);
                String remainder = raw.substring(3);
                StringBuilder value = new StringBuilder();
                int closing = remainder.indexOf(delimiter);
                if (closing >= 0) {
                    return new ParsedValue(remainder.substring(0, closing), lineNumber);
                }
                value.append(remainder);
                for (int index = lineNumber + 1; index < lines.length; index++) {
                    value.append('\n');
                    int end = lines[index].indexOf(delimiter);
                    if (end >= 0) {
                        value.append(lines[index], 0, end);
                        return new ParsedValue(value.toString(), index);
                    }
                    value.append(lines[index]);
                }
                throw new IllegalArgumentException("Unterminated TOML multiline string");
            }
            if (raw.startsWith("\"") || raw.startsWith("'")) {
                char quote = raw.charAt(0);
                int end = findClosingQuote(raw, quote);
                if (end < 0) {
                    throw new IllegalArgumentException("Unterminated TOML string");
                }
                String value = raw.substring(1, end);
                return new ParsedValue(quote == '"' ? unescape(value) : value, lineNumber);
            }
            int comment = findCommentOutsideQuotes(raw);
            return new ParsedValue((comment < 0 ? raw : raw.substring(0, comment)).strip(), lineNumber);
        }

        private static int findClosingQuote(String value, char quote) {
            boolean escaped = false;
            for (int index = 1; index < value.length(); index++) {
                char current = value.charAt(index);
                if (quote == '"' && escaped) {
                    escaped = false;
                } else if (quote == '"' && current == '\\') {
                    escaped = true;
                } else if (current == quote) {
                    return index;
                }
            }
            return -1;
        }

        private static int findCommentOutsideQuotes(String value) {
            char quote = 0;
            boolean escaped = false;
            for (int index = 0; index < value.length(); index++) {
                char current = value.charAt(index);
                if (quote == '"' && escaped) {
                    escaped = false;
                } else if (quote == '"' && current == '\\') {
                    escaped = true;
                } else if ((current == '\'' || current == '"') && (quote == 0 || quote == current)) {
                    quote = quote == 0 ? current : 0;
                } else if (current == '#' && quote == 0) {
                    return index;
                }
            }
            return -1;
        }

        private static String unescape(String value) {
            StringBuilder result = new StringBuilder(value.length());
            boolean escaped = false;
            for (int index = 0; index < value.length(); index++) {
                char current = value.charAt(index);
                if (!escaped) {
                    if (current == '\\') {
                        escaped = true;
                    } else {
                        result.append(current);
                    }
                    continue;
                }
                escaped = false;
                switch (current) {
                    case 'n' -> result.append('\n');
                    case 'r' -> result.append('\r');
                    case 't' -> result.append('\t');
                    case '"' -> result.append('"');
                    case '\\' -> result.append('\\');
                    default -> result.append(current);
                }
            }
            if (escaped) {
                result.append('\\');
            }
            return result.toString();
        }

        private record ParsedValue(String value, int lastLine) {
        }
    }
}
