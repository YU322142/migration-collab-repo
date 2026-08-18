package io.github.mcmodsync;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

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

    static String stringify(Object value) {
        StringBuilder output = new StringBuilder();
        writeValue(output, value);
        return output.toString();
    }

    private static void writeValue(StringBuilder output, Object value) {
        if (value == null) {
            output.append("null");
        } else if (value instanceof String text) {
            writeString(output, text);
        } else if (value instanceof Boolean bool) {
            output.append(bool);
        } else if (value instanceof BigDecimal number) {
            output.append(number.stripTrailingZeros().toPlainString());
        } else if (value instanceof Byte || value instanceof Short || value instanceof Integer
                || value instanceof Long || value instanceof java.math.BigInteger) {
            output.append(value);
        } else if (value instanceof Float || value instanceof Double) {
            throw new IllegalArgumentException("JSON 浮点输出必须使用 BigDecimal，避免非确定性表示");
        } else if (value instanceof Map<?, ?> map) {
            output.append('{');
            boolean first = true;
            TreeMap<String, Object> sorted = new TreeMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!(entry.getKey() instanceof String key)) {
                    throw new IllegalArgumentException("JSON 对象键必须是字符串");
                }
                sorted.put(key, entry.getValue());
            }
            for (Map.Entry<String, Object> entry : sorted.entrySet()) {
                if (!first) {
                    output.append(',');
                }
                first = false;
                writeString(output, entry.getKey());
                output.append(':');
                writeValue(output, entry.getValue());
            }
            output.append('}');
        } else if (value instanceof Iterable<?> values) {
            output.append('[');
            boolean first = true;
            for (Object item : values) {
                if (!first) {
                    output.append(',');
                }
                first = false;
                writeValue(output, item);
            }
            output.append(']');
        } else {
            throw new IllegalArgumentException("不支持的 JSON 值类型: " + value.getClass().getName());
        }
    }

    private static void writeString(StringBuilder output, String value) {
        output.append('"');
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            switch (current) {
                case '"' -> output.append("\\\"");
                case '\\' -> output.append("\\\\");
                case '\b' -> output.append("\\b");
                case '\f' -> output.append("\\f");
                case '\n' -> output.append("\\n");
                case '\r' -> output.append("\\r");
                case '\t' -> output.append("\\t");
                default -> {
                    if (current < 0x20) {
                        output.append("\\u").append(String.format(java.util.Locale.ROOT, "%04x", (int) current));
                    } else {
                        output.append(current);
                    }
                }
            }
        }
        output.append('"');
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
