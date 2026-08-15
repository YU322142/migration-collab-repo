package dev.migration.heightmap_384_to_544_compat;

import java.util.Objects;

public final class HeightmapArrayConverter {
    public static final int LEGACY_HEIGHT = 384;
    public static final int TARGET_HEIGHT = 544;
    public static final int VALUE_COUNT = 256;
    public static final int LEGACY_BITS = 9;
    public static final int TARGET_BITS = 10;
    public static final int LEGACY_WORDS = 37;
    public static final int TARGET_WORDS = 43;

    private HeightmapArrayConverter() {
    }

    public static Conversion convert(int chunkHeight, long[] input) {
        if (chunkHeight != TARGET_HEIGHT) {
            return new Conversion(Status.NOT_APPLICABLE, input, null);
        }
        if (input == null) {
            return new Conversion(Status.REJECTED, null, "input array is null");
        }
        if (input.length == TARGET_WORDS) {
            return new Conversion(Status.ALREADY_CURRENT, input, null);
        }
        if (input.length != LEGACY_WORDS) {
            return new Conversion(
                    Status.REJECTED,
                    input,
                    "unexpected array length " + input.length + "; expected " + LEGACY_WORDS + " or " + TARGET_WORDS
            );
        }
        if (!hasZeroPadding(input, LEGACY_BITS, VALUE_COUNT)) {
            return new Conversion(Status.REJECTED, input, "legacy 9-bit array has non-zero padding bits");
        }

        int[] values = unpackNonSpanning(input, LEGACY_BITS, VALUE_COUNT);
        for (int index = 0; index < values.length; index++) {
            if (values[index] < 0 || values[index] > LEGACY_HEIGHT) {
                return new Conversion(
                        Status.REJECTED,
                        input,
                        "legacy value " + values[index] + " at index " + index + " is outside 0.." + LEGACY_HEIGHT
                );
            }
        }

        long[] output = packNonSpanning(values, TARGET_BITS);
        if (output.length != TARGET_WORDS || !hasZeroPadding(output, TARGET_BITS, VALUE_COUNT)) {
            throw new IllegalStateException("internal 10-bit packing invariant failed");
        }
        return new Conversion(Status.CONVERTED, output, null);
    }

    static int[] unpackNonSpanning(long[] words, int bits, int valueCount) {
        Objects.requireNonNull(words, "words");
        validateBits(bits);
        if (valueCount < 0) {
            throw new IllegalArgumentException("valueCount must be non-negative");
        }
        int valuesPerWord = 64 / bits;
        int expectedWords = wordCount(bits, valueCount);
        if (words.length != expectedWords) {
            throw new IllegalArgumentException(
                    "word length " + words.length + " does not match expected " + expectedWords
            );
        }
        long mask = mask(bits);
        int[] values = new int[valueCount];
        for (int index = 0; index < valueCount; index++) {
            int wordIndex = index / valuesPerWord;
            int bitOffset = (index % valuesPerWord) * bits;
            values[index] = (int) ((words[wordIndex] >>> bitOffset) & mask);
        }
        return values;
    }

    static long[] packNonSpanning(int[] values, int bits) {
        Objects.requireNonNull(values, "values");
        validateBits(bits);
        int valuesPerWord = 64 / bits;
        long valueMask = mask(bits);
        long[] words = new long[wordCount(bits, values.length)];
        for (int index = 0; index < values.length; index++) {
            int value = values[index];
            if (value < 0 || ((long) value & ~valueMask) != 0L) {
                throw new IllegalArgumentException("value " + value + " does not fit in " + bits + " bits");
            }
            int wordIndex = index / valuesPerWord;
            int bitOffset = (index % valuesPerWord) * bits;
            words[wordIndex] |= ((long) value & valueMask) << bitOffset;
        }
        return words;
    }

    static boolean hasZeroPadding(long[] words, int bits, int valueCount) {
        if (words == null || bits < 1 || bits > 32 || valueCount < 0) {
            return false;
        }
        int valuesPerWord = 64 / bits;
        if (words.length != wordCount(bits, valueCount)) {
            return false;
        }
        for (int wordIndex = 0; wordIndex < words.length; wordIndex++) {
            int remainingValues = valueCount - wordIndex * valuesPerWord;
            int valuesInWord = Math.min(valuesPerWord, Math.max(remainingValues, 0));
            int usedBits = valuesInWord * bits;
            long usedMask = mask(usedBits);
            if ((words[wordIndex] & ~usedMask) != 0L) {
                return false;
            }
        }
        return true;
    }

    private static int wordCount(int bits, int valueCount) {
        int valuesPerWord = 64 / bits;
        return (valueCount + valuesPerWord - 1) / valuesPerWord;
    }

    private static long mask(int bits) {
        if (bits == 0) {
            return 0L;
        }
        return bits == 64 ? -1L : (1L << bits) - 1L;
    }

    private static void validateBits(int bits) {
        if (bits < 1 || bits > 32) {
            throw new IllegalArgumentException("bits must be in 1..32");
        }
    }

    public enum Status {
        NOT_APPLICABLE,
        ALREADY_CURRENT,
        CONVERTED,
        REJECTED
    }

    public record Conversion(Status status, long[] data, String diagnostic) {
        public Conversion {
            Objects.requireNonNull(status, "status");
            if (status == Status.REJECTED && (diagnostic == null || diagnostic.isBlank())) {
                throw new IllegalArgumentException("rejected conversions require a diagnostic");
            }
        }
    }
}
