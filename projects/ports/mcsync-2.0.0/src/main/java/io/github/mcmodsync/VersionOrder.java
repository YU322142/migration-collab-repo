package io.github.mcmodsync;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Numeric release ordering shared by legacy upgrade and schema-v5 gates. */
final class VersionOrder {
    private static final Pattern NUMERIC = Pattern.compile("(?<!\\d)(\\d+(?:\\.\\d+){1,3})(?!\\d)");

    private VersionOrder() {
    }

    static int compare(String left, String right) {
        int[] leftParts = parts(left);
        int[] rightParts = parts(right);
        if (leftParts == null || rightParts == null) return 0;
        int length = Math.max(leftParts.length, rightParts.length);
        for (int index = 0; index < length; index++) {
            int compared = Integer.compare(
                    index < leftParts.length ? leftParts[index] : 0,
                    index < rightParts.length ? rightParts[index] : 0);
            if (compared != 0) return compared;
        }
        return 0;
    }

    private static int[] parts(String value) {
        Matcher matcher = NUMERIC.matcher(value == null ? "" : value);
        if (!matcher.find()) return null;
        String[] values = matcher.group(1).split("\\.");
        int[] result = new int[values.length];
        try {
            for (int index = 0; index < values.length; index++) result[index] = Integer.parseInt(values[index]);
            return result;
        } catch (NumberFormatException failure) {
            return null;
        }
    }
}
