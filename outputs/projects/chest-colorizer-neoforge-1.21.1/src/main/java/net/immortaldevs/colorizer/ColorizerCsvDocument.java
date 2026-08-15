package net.immortaldevs.colorizer;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import javax.annotation.Nullable;

final class ColorizerCsvDocument {
    private final List<Line> lines;
    private final String newline;
    private boolean trailingNewline;

    private ColorizerCsvDocument(List<Line> lines, String newline, boolean trailingNewline) {
        this.lines = lines;
        this.newline = newline;
        this.trailingNewline = trailingNewline;
    }

    static ColorizerCsvDocument empty() {
        return new ColorizerCsvDocument(new ArrayList<>(), System.lineSeparator(), false);
    }

    static ColorizerCsvDocument parse(String data) {
        if (data.isEmpty()) {
            return empty();
        }
        String newline = data.contains("\r\n") ? "\r\n" : "\n";
        boolean trailingNewline = data.endsWith("\n") || data.endsWith("\r");
        String normalized = data.replace("\r\n", "\n").replace('\r', '\n');
        String[] rawLines = normalized.split("\n", -1);
        int count = trailingNewline ? rawLines.length - 1 : rawLines.length;
        List<Line> lines = new ArrayList<>(Math.max(count, 0));

        for (int index = 0; index < count; index++) {
            lines.add(parseLine(rawLines[index]));
        }
        return new ColorizerCsvDocument(lines, newline, trailingNewline);
    }

    @Nullable
    BlockColor getColor(String worldName, int x, int y, int z) {
        Key wanted = new Key(worldName, x, y, z);
        BlockColor result = null;
        for (Line line : lines) {
            if (line instanceof RecordLine record && record.key.equals(wanted)) {
                result = record.color;
            }
        }
        return result;
    }

    void setColor(String worldName, int x, int y, int z, BlockColor color) {
        Key wanted = new Key(worldName, x, y, z);
        boolean wasEmpty = lines.isEmpty();
        int lastMatch = -1;
        for (int index = 0; index < lines.size(); index++) {
            if (lines.get(index) instanceof RecordLine record && record.key.equals(wanted)) {
                lastMatch = index;
            }
        }

        RecordLine replacement = new RecordLine(wanted, color, encode(wanted, color));
        if (lastMatch >= 0) {
            lines.set(lastMatch, replacement);
        } else {
            lines.add(replacement);
        }
        if (wasEmpty) {
            trailingNewline = true;
        }
    }

    void removeColor(String worldName, int x, int y, int z) {
        Key wanted = new Key(worldName, x, y, z);
        lines.removeIf(line -> line instanceof RecordLine record && record.key.equals(wanted));
    }

    String serialize() {
        StringBuilder output = new StringBuilder();
        for (int index = 0; index < lines.size(); index++) {
            if (index > 0) {
                output.append(newline);
            }
            output.append(lines.get(index).raw());
        }
        if (trailingNewline && !lines.isEmpty()) {
            output.append(newline);
        }
        return output.toString();
    }

    int validRecordCount() {
        int count = 0;
        for (Line line : lines) {
            if (line instanceof RecordLine) {
                count++;
            }
        }
        return count;
    }

    int preservedLineCount() {
        return lines.size() - validRecordCount();
    }

    private static Line parseLine(String raw) {
        String[] parts = raw.split(";", -1);
        if (parts.length != 5) {
            return new RawLine(raw);
        }

        try {
            int x = Integer.parseInt(parts[1]);
            int y = Integer.parseInt(parts[2]);
            int z = Integer.parseInt(parts[3]);
            BlockColor color = BlockColor.fromName(parts[4]);
            if (color == null) {
                return new RawLine(raw);
            }
            return new RecordLine(new Key(parts[0], x, y, z), color, raw);
        } catch (NumberFormatException ignored) {
            return new RawLine(raw);
        }
    }

    private static String encode(Key key, BlockColor color) {
        return key.worldName + ";" + key.x + ";" + key.y + ";" + key.z + ";" + color.getName();
    }

    private sealed interface Line permits RawLine, RecordLine {
        String raw();
    }

    private record RawLine(String raw) implements Line {
    }

    private record RecordLine(Key key, BlockColor color, String raw) implements Line {
    }

    private record Key(String worldName, int x, int y, int z) {
        private Key {
            Objects.requireNonNull(worldName, "worldName");
        }
    }
}
