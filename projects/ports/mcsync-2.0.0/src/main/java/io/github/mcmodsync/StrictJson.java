package io.github.mcmodsync;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Minimal strict JSON reader used by the signed MCSync release manifest. */
final class StrictJson {
    private final String source;
    private int index;

    private StrictJson(String source) {
        this.source = source == null ? "" : source;
    }

    static Object parse(String source) {
        StrictJson reader = new StrictJson(source);
        Object value = reader.readValue();
        reader.skipWhitespace();
        if (reader.index != reader.source.length()) {
            throw reader.error("JSON 尾部存在多余内容");
        }
        return value;
    }

    private Object readValue() {
        skipWhitespace();
        if (index >= source.length()) {
            throw error("JSON 意外结束");
        }
        return switch (source.charAt(index)) {
            case '{' -> readObject();
            case '[' -> readArray();
            case '"' -> readString();
            case 't' -> readLiteral("true", Boolean.TRUE);
            case 'f' -> readLiteral("false", Boolean.FALSE);
            case 'n' -> readLiteral("null", null);
            default -> readNumber();
        };
    }

    private Map<String, Object> readObject() {
        expect('{');
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        skipWhitespace();
        if (consume('}')) {
            return Collections.unmodifiableMap(result);
        }
        while (true) {
            skipWhitespace();
            if (index >= source.length() || source.charAt(index) != '"') {
                throw error("JSON 对象键必须是字符串");
            }
            String key = readString();
            skipWhitespace();
            expect(':');
            Object value = readValue();
            if (result.containsKey(key)) {
                throw error("JSON 对象包含重复键: " + key);
            }
            result.put(key, value);
            skipWhitespace();
            if (consume('}')) {
                return Collections.unmodifiableMap(result);
            }
            expect(',');
        }
    }

    private List<Object> readArray() {
        expect('[');
        ArrayList<Object> result = new ArrayList<>();
        skipWhitespace();
        if (consume(']')) {
            return Collections.unmodifiableList(result);
        }
        while (true) {
            result.add(readValue());
            skipWhitespace();
            if (consume(']')) {
                return Collections.unmodifiableList(result);
            }
            expect(',');
        }
    }

    private String readString() {
        expect('"');
        StringBuilder result = new StringBuilder();
        while (index < source.length()) {
            char current = source.charAt(index++);
            if (current == '"') {
                return result.toString();
            }
            if (current == '\\') {
                if (index >= source.length()) {
                    throw error("JSON 转义序列不完整");
                }
                char escaped = source.charAt(index++);
                switch (escaped) {
                    case '"', '\\', '/' -> result.append(escaped);
                    case 'b' -> result.append('\b');
                    case 'f' -> result.append('\f');
                    case 'n' -> result.append('\n');
                    case 'r' -> result.append('\r');
                    case 't' -> result.append('\t');
                    case 'u' -> result.append(readUnicodeEscape());
                    default -> throw error("JSON 包含未知转义字符: " + escaped);
                }
            } else {
                if (current < 0x20) {
                    throw error("JSON 字符串包含控制字符");
                }
                result.append(current);
            }
        }
        throw error("JSON 字符串未闭合");
    }

    private char readUnicodeEscape() {
        if (index + 4 > source.length()) {
            throw error("JSON Unicode 转义不完整");
        }
        int value = 0;
        for (int offset = 0; offset < 4; offset++) {
            int digit = Character.digit(source.charAt(index++), 16);
            if (digit < 0) {
                throw error("JSON Unicode 转义无效");
            }
            value = value * 16 + digit;
        }
        return (char) value;
    }

    private Object readNumber() {
        int start = index;
        if (consume('-') && index >= source.length()) {
            throw error("JSON 数字无效");
        }
        if (consume('0')) {
            if (index < source.length() && Character.isDigit(source.charAt(index))) {
                throw error("JSON 数字不能包含前导零");
            }
        } else {
            readDigits();
        }
        if (consume('.')) {
            readDigits();
        }
        if (index < source.length() && (source.charAt(index) == 'e' || source.charAt(index) == 'E')) {
            index++;
            if (index < source.length() && (source.charAt(index) == '+' || source.charAt(index) == '-')) {
                index++;
            }
            readDigits();
        }
        if (start == index) {
            throw error("JSON 值无效");
        }
        try {
            return new BigDecimal(source.substring(start, index));
        } catch (NumberFormatException exception) {
            throw error("JSON 数字无效");
        }
    }

    private void readDigits() {
        int start = index;
        while (index < source.length() && Character.isDigit(source.charAt(index))) {
            index++;
        }
        if (start == index) {
            throw error("JSON 数字缺少数字");
        }
    }

    private Object readLiteral(String literal, Object value) {
        if (!source.startsWith(literal, index)) {
            throw error("JSON 字面量无效");
        }
        index += literal.length();
        return value;
    }

    private void skipWhitespace() {
        while (index < source.length()) {
            char current = source.charAt(index);
            if (current != ' ' && current != '\n' && current != '\r' && current != '\t') {
                return;
            }
            index++;
        }
    }

    private boolean consume(char expected) {
        if (index < source.length() && source.charAt(index) == expected) {
            index++;
            return true;
        }
        return false;
    }

    private void expect(char expected) {
        if (!consume(expected)) {
            throw error("JSON 需要字符 '" + expected + "'");
        }
    }

    private IllegalArgumentException error(String message) {
        return new IllegalArgumentException(message + " (offset=" + index + ")");
    }
}
