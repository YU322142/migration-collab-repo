package io.github.mcmodsync;

import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Applies one schema-validated configuration operation without touching the filesystem. */
final class ConfigMutationEngine {
    private static final Pattern TOML_SECTION = Pattern.compile("^\\s*\\[([A-Za-z0-9_.-]+)]\\s*(?:#.*)?$");
    private static final Pattern TOML_ASSIGNMENT = Pattern.compile("^(\\s*)([A-Za-z0-9_.-]+)(\\s*=\\s*)(.*)$");

    private ConfigMutationEngine() {
    }

    static MutationResult apply(byte[] original, ReleaseManifestV5.ConfigOperation operation) {
        Objects.requireNonNull(original, "original");
        Objects.requireNonNull(operation, "operation");
        if (operation.operation().equals("file-replace")) {
            throw new IllegalArgumentException("file-replace 由文件事务层应用，不属于结构化配置编辑器");
        }
        String text = decodeUtf8(original);
        return switch (operation.format()) {
            case "json" -> mutateJson(text, operation);
            case "toml" -> mutateToml(text, operation);
            case "properties" -> mutateProperties(text, operation);
            default -> throw new IllegalArgumentException("不支持的结构化配置格式: " + operation.format());
        };
    }

    record MutationResult(byte[] bytes, boolean changed, String outcome, Object previousValue) {
        MutationResult {
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    private static MutationResult mutateJson(String text, ReleaseManifestV5.ConfigOperation operation) {
        Object parsed = StrictJson.parse(text);
        if (!(parsed instanceof Map<?, ?> rootMap)) {
            throw new IllegalArgumentException("JSON 配置根必须是对象");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> root = deepMutableMap((Map<String, Object>) rootMap);
        List<String> segments = keySegments(operation.key());
        Map<String, Object> parent = root;
        for (int index = 0; index < segments.size() - 1; index++) {
            String segment = segments.get(index);
            Object child = parent.get(segment);
            if (child == null) {
                if (!operation.missingPolicy().equals("create")) {
                    return missing(operation, text.getBytes(StandardCharsets.UTF_8));
                }
                LinkedHashMap<String, Object> created = new LinkedHashMap<>();
                parent.put(segment, created);
                parent = created;
            } else if (child instanceof Map<?, ?> map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> typed = (Map<String, Object>) map;
                parent = typed;
            } else {
                throw new IllegalArgumentException("JSON 键路径穿过非对象值: " + operation.key());
            }
        }
        String leaf = segments.getLast();
        boolean present = parent.containsKey(leaf);
        Object previous = parent.get(leaf);
        if (!present && !operation.missingPolicy().equals("create")) {
            return missing(operation, text.getBytes(StandardCharsets.UTF_8));
        }
        Decision decision = decide(previous, present, operation);
        if (!decision.apply()) {
            return new MutationResult(text.getBytes(StandardCharsets.UTF_8), false, decision.outcome(), previous);
        }
        Object desired = deepMutable(operation.desired());
        if (operation.operation().equals("config-merge")) {
            if (!(desired instanceof Map<?, ?> desiredMap)) {
                throw new IllegalArgumentException("JSON config-merge 的 desired 必须是对象");
            }
            if (present && !(previous instanceof Map<?, ?>)) {
                throw new IllegalArgumentException("JSON config-merge 目标当前不是对象");
            }
            Map<String, Object> merged = present
                    ? deepMutableMap(castMap(previous))
                    : new LinkedHashMap<>();
            deepMerge(merged, castMap(desiredMap));
            desired = merged;
        }
        parent.put(leaf, desired);
        String serialized = StrictJson.stringify(root) + "\n";
        return new MutationResult(
                serialized.getBytes(StandardCharsets.UTF_8),
                !semanticEquals(previous, desired) || !present,
                "applied",
                previous);
    }

    private static MutationResult mutateToml(String text, ReleaseManifestV5.ConfigOperation operation) {
        if (operation.operation().equals("config-merge")) {
            throw new IllegalArgumentException("TOML 对象合并必须拆成多个 config-set，避免隐式覆盖");
        }
        TextLines document = TextLines.parse(text);
        List<String> segments = keySegments(operation.key());
        String wantedKey = segments.getLast();
        String wantedSection = String.join(".", segments.subList(0, segments.size() - 1));
        String section = "";
        int sectionEnd = document.lines().size();
        int sectionHeader = -1;
        int foundLine = -1;
        Object previous = null;
        for (int index = 0; index < document.lines().size(); index++) {
            String line = document.lines().get(index);
            Matcher sectionMatcher = TOML_SECTION.matcher(line);
            if (sectionMatcher.matches()) {
                if (section.equals(wantedSection) && sectionEnd == document.lines().size()) {
                    sectionEnd = index;
                }
                section = sectionMatcher.group(1);
                if (section.equals(wantedSection)) {
                    sectionHeader = index;
                }
                continue;
            }
            Matcher assignment = TOML_ASSIGNMENT.matcher(line);
            if (!assignment.matches() || !section.equals(wantedSection)) {
                continue;
            }
            if (assignment.group(2).equals(wantedKey)) {
                if (foundLine >= 0) {
                    throw new IllegalArgumentException("TOML 配置包含重复目标键: " + operation.key());
                }
                foundLine = index;
                String valueText = splitTomlComment(assignment.group(4))[0].strip();
                previous = parseScalar(valueText, operation.valueType(), "TOML");
            }
        }
        boolean present = foundLine >= 0;
        if (!present && !operation.missingPolicy().equals("create")) {
            return missing(operation, text.getBytes(StandardCharsets.UTF_8));
        }
        Decision decision = decide(previous, present, operation);
        if (!decision.apply()) {
            return new MutationResult(text.getBytes(StandardCharsets.UTF_8), false, decision.outcome(), previous);
        }
        String desired = renderScalar(operation.desired(), operation.valueType(), "TOML");
        if (present) {
            Matcher assignment = TOML_ASSIGNMENT.matcher(document.lines().get(foundLine));
            if (!assignment.matches()) {
                throw new IllegalStateException("TOML 目标行在事务中发生漂移");
            }
            String[] valueAndComment = splitTomlComment(assignment.group(4));
            String suffix = valueAndComment[1];
            document.lines().set(foundLine,
                    assignment.group(1) + wantedKey + assignment.group(3) + desired + suffix);
        } else if (wantedSection.isEmpty()) {
            document.lines().add(0, wantedKey + " = " + desired);
        } else if (sectionHeader >= 0) {
            int insertAt = sectionEnd == document.lines().size() ? document.lines().size() : sectionEnd;
            document.lines().add(insertAt, wantedKey + " = " + desired);
        } else {
            if (!document.lines().isEmpty() && !document.lines().getLast().isBlank()) {
                document.lines().add("");
            }
            document.lines().add("[" + wantedSection + "]");
            document.lines().add(wantedKey + " = " + desired);
        }
        byte[] result = document.render().getBytes(StandardCharsets.UTF_8);
        return new MutationResult(result, !semanticEquals(previous, operation.desired()) || !present, "applied", previous);
    }

    private static MutationResult mutateProperties(String text, ReleaseManifestV5.ConfigOperation operation) {
        if (operation.operation().equals("config-merge")) {
            throw new IllegalArgumentException("properties 合并必须拆成多个 config-set");
        }
        TextLines document = TextLines.parse(text);
        int foundLine = -1;
        Object previous = null;
        for (int index = 0; index < document.lines().size(); index++) {
            String line = document.lines().get(index);
            if (line.endsWith("\\") && !line.endsWith("\\\\")) {
                throw new IllegalArgumentException("properties 续行暂不支持键级安全编辑");
            }
            String stripped = line.stripLeading();
            if (stripped.isEmpty() || stripped.startsWith("#") || stripped.startsWith("!")) {
                continue;
            }
            int separator = propertySeparator(line);
            String key = (separator < 0 ? line : line.substring(0, separator)).strip();
            if (!key.equals(operation.key())) {
                continue;
            }
            if (foundLine >= 0) {
                throw new IllegalArgumentException("properties 配置包含重复目标键: " + operation.key());
            }
            foundLine = index;
            String value = separator < 0 ? "" : line.substring(separator + 1).strip();
            previous = parseScalar(value, operation.valueType(), "properties");
        }
        boolean present = foundLine >= 0;
        if (!present && !operation.missingPolicy().equals("create")) {
            return missing(operation, text.getBytes(StandardCharsets.UTF_8));
        }
        Decision decision = decide(previous, present, operation);
        if (!decision.apply()) {
            return new MutationResult(text.getBytes(StandardCharsets.UTF_8), false, decision.outcome(), previous);
        }
        String desired = renderScalar(operation.desired(), operation.valueType(), "properties");
        String replacement = operation.key() + "=" + desired;
        if (present) {
            document.lines().set(foundLine, replacement);
        } else {
            document.lines().add(replacement);
        }
        return new MutationResult(
                document.render().getBytes(StandardCharsets.UTF_8),
                !semanticEquals(previous, operation.desired()) || !present,
                "applied",
                previous);
    }

    private static MutationResult missing(ReleaseManifestV5.ConfigOperation operation, byte[] original) {
        return switch (operation.missingPolicy()) {
            case "skip" -> new MutationResult(original, false, "skipped-missing", null);
            case "block" -> throw new IllegalArgumentException("受控配置键不存在: " + operation.path() + "#" + operation.key());
            default -> throw new IllegalStateException("未知 missingPolicy: " + operation.missingPolicy());
        };
    }

    private static Decision decide(
            Object previous,
            boolean present,
            ReleaseManifestV5.ConfigOperation operation) {
        if (!present) {
            return new Decision(true, "created");
        }
        if (operation.operation().equals("config-set") && semanticEquals(previous, operation.desired())) {
            return new Decision(false, "already-desired");
        }
        if (operation.operation().equals("config-merge")
                && previous instanceof Map<?, ?> previousMap
                && operation.desired() instanceof Map<?, ?> desiredMap
                && containsDesired(castMap(previousMap), castMap(desiredMap))) {
            return new Decision(false, "already-desired");
        }
        if (expectedMatches(previous, operation.expected())) {
            return new Decision(true, "matched-expected");
        }
        return switch (operation.conflictPolicy()) {
            case "force" -> new Decision(true, "forced");
            case "keep-local" -> new Decision(false, "kept-local");
            case "report" -> new Decision(false, "reported-conflict");
            case "block", "replace-if-expected" -> throw new IllegalArgumentException(
                    "配置值与 expected 不匹配: " + operation.path() + "#" + operation.key());
            default -> throw new IllegalStateException("未知 conflictPolicy: " + operation.conflictPolicy());
        };
    }

    private static boolean expectedMatches(Object current, Object expected) {
        if (expected instanceof List<?> values) {
            return values.stream().anyMatch(value -> semanticEquals(current, value));
        }
        return semanticEquals(current, expected);
    }

    private static boolean semanticEquals(Object left, Object right) {
        if (left instanceof BigDecimal leftNumber && right instanceof BigDecimal rightNumber) {
            return leftNumber.compareTo(rightNumber) == 0;
        }
        return Objects.equals(left, right);
    }

    private static boolean containsDesired(Map<String, Object> current, Map<String, Object> desired) {
        for (Map.Entry<String, Object> entry : desired.entrySet()) {
            Object actual = current.get(entry.getKey());
            if (actual instanceof Map<?, ?> actualMap && entry.getValue() instanceof Map<?, ?> wantedMap) {
                if (!containsDesired(castMap(actualMap), castMap(wantedMap))) return false;
            } else if (!semanticEquals(actual, entry.getValue())) {
                return false;
            }
        }
        return true;
    }

    private static Object parseScalar(String text, String type, String format) {
        try {
            return switch (type) {
                case "boolean" -> {
                    if (text.equalsIgnoreCase("true")) yield Boolean.TRUE;
                    if (text.equalsIgnoreCase("false")) yield Boolean.FALSE;
                    throw new IllegalArgumentException();
                }
                case "integer" -> new BigDecimal(text).setScale(0, java.math.RoundingMode.UNNECESSARY);
                case "decimal" -> new BigDecimal(text);
                case "string" -> parseStringScalar(text, format);
                case "array", "object" -> StrictJson.parse(text);
                default -> throw new IllegalArgumentException("不支持的配置值类型: " + type);
            };
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException(format + " 配置值不能按 " + type + " 解析: " + text, exception);
        }
    }

    private static String parseStringScalar(String text, String format) {
        if (format.equals("properties")) {
            return text;
        }
        if (text.startsWith("\"") && text.endsWith("\"")) {
            Object parsed = StrictJson.parse(text);
            if (parsed instanceof String value) {
                return value;
            }
        }
        if (text.startsWith("'") && text.endsWith("'") && text.length() >= 2) {
            return text.substring(1, text.length() - 1);
        }
        throw new IllegalArgumentException("字符串必须使用引号");
    }

    private static String renderScalar(Object value, String type, String format) {
        if (!ReleaseManifestV5ValueTypes.matches(value, type)) {
            throw new IllegalArgumentException("目标配置值与 valueType 不匹配");
        }
        return switch (type) {
            case "boolean" -> value.toString();
            case "integer", "decimal" -> ((BigDecimal) value).stripTrailingZeros().toPlainString();
            case "string" -> format.equals("properties")
                    ? escapeProperty((String) value)
                    : StrictJson.stringify(value);
            case "array", "object" -> StrictJson.stringify(value);
            default -> throw new IllegalArgumentException("不支持的配置值类型: " + type);
        };
    }

    private static String escapeProperty(String value) {
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r");
    }

    private static List<String> keySegments(String key) {
        List<String> result = List.of(key.split("\\.", -1));
        if (result.isEmpty() || result.stream().anyMatch(segment -> segment.isBlank()
                || !segment.matches("[A-Za-z0-9_-]+"))) {
            throw new IllegalArgumentException("配置 key 路径无效: " + key);
        }
        return result;
    }

    private static String[] splitTomlComment(String value) {
        boolean quoted = false;
        boolean escaped = false;
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            if (current == '"' && !escaped) {
                quoted = !quoted;
            }
            if (current == '#' && !quoted) {
                int start = index;
                while (start > 0 && Character.isWhitespace(value.charAt(start - 1))) {
                    start--;
                }
                return new String[]{value.substring(0, start), value.substring(start)};
            }
            escaped = current == '\\' && !escaped;
            if (current != '\\') {
                escaped = false;
            }
        }
        return new String[]{value, ""};
    }

    private static int propertySeparator(String line) {
        boolean escaped = false;
        for (int index = 0; index < line.length(); index++) {
            char current = line.charAt(index);
            if (!escaped && (current == '=' || current == ':')) {
                return index;
            }
            escaped = current == '\\' && !escaped;
            if (current != '\\') {
                escaped = false;
            }
        }
        return -1;
    }

    private static String decodeUtf8(byte[] bytes) {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException exception) {
            throw new IllegalArgumentException("配置文件不是有效 UTF-8", exception);
        }
    }

    private static Map<String, Object> deepMutableMap(Map<String, Object> source) {
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(key, deepMutable(value)));
        return result;
    }

    private static Object deepMutable(Object value) {
        if (value instanceof Map<?, ?> map) {
            return deepMutableMap(castMap(map));
        }
        if (value instanceof List<?> list) {
            return new ArrayList<>(list.stream().map(ConfigMutationEngine::deepMutable).toList());
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> castMap(Object value) {
        return (Map<String, Object>) value;
    }

    private static void deepMerge(Map<String, Object> target, Map<String, Object> desired) {
        desired.forEach((key, value) -> {
            Object current = target.get(key);
            if (current instanceof Map<?, ?> currentMap && value instanceof Map<?, ?> desiredMap) {
                deepMerge(castMap(currentMap), castMap(desiredMap));
            } else {
                target.put(key, deepMutable(value));
            }
        });
    }

    private record Decision(boolean apply, String outcome) {
    }

    private record TextLines(List<String> lines, String newline, boolean terminalNewline) {
        static TextLines parse(String text) {
            String newline = text.contains("\r\n") ? "\r\n" : "\n";
            boolean terminal = text.endsWith("\n");
            String normalized = text.replace("\r\n", "\n");
            ArrayList<String> lines = new ArrayList<>(List.of(normalized.split("\n", -1)));
            if (terminal && !lines.isEmpty() && lines.getLast().isEmpty()) {
                lines.removeLast();
            }
            return new TextLines(lines, newline, terminal);
        }

        String render() {
            String result = String.join(newline, lines);
            return terminalNewline ? result + newline : result;
        }
    }

    /** Shared package-local type predicate without exposing manifest parser internals. */
    private static final class ReleaseManifestV5ValueTypes {
        static boolean matches(Object value, String type) {
            if (value == null) return true;
            return switch (type) {
                case "boolean" -> value instanceof Boolean;
                case "integer" -> value instanceof BigDecimal number && number.scale() <= 0;
                case "decimal" -> value instanceof BigDecimal;
                case "string", "binary" -> value instanceof String;
                case "array" -> value instanceof List<?>;
                case "object" -> value instanceof Map<?, ?>;
                default -> false;
            };
        }
    }
}
