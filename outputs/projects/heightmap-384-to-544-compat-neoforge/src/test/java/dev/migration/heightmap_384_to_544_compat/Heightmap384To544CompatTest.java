package dev.migration.heightmap_384_to_544_compat;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class Heightmap384To544CompatTest {
    private static final String RUNTIME_HEIGHTMAP =
            "net/minecraft/world/level/levelgen/Heightmap.class";
    private static final String RUNTIME_CHUNK_ACCESS =
            "net/minecraft/world/level/chunk/ChunkAccess.class";
    private static final String MIXIN_CLASS =
            "dev/migration/heightmap_384_to_544_compat/mixin/ChunkAccessMixin.class";
    private static final String MIXIN_RESOURCE = "heightmap_384_to_544_compat.mixins.json";
    private static final String MOD_METADATA = "META-INF/neoforge.mods.toml";

    private Heightmap384To544CompatTest() {
    }

    public static void main(String[] args) throws Exception {
        verifyPackUnpackRoundTrips();
        verifyLegacyToCurrentSemanticEquality();
        verifyEveryLegacyValueAndWordBoundary();
        verifyIdempotenceAndScope();
        verifyMalformedInputsFailClosed();
        verifyRuntimeBytecodeContract();
        verifyCompiledMixinContract();
        verifyBothSideMetadata();
        System.out.println("Heightmap 384-to-544 codec, runtime bytecode, mixin, and BOTH-side metadata tests passed");
    }

    private static void verifyPackUnpackRoundTrips() {
        int[] values = new int[HeightmapArrayConverter.VALUE_COUNT];
        for (int index = 0; index < values.length; index++) {
            values[index] = (index * 149 + 17) % (HeightmapArrayConverter.LEGACY_HEIGHT + 1);
        }
        for (int bits : List.of(HeightmapArrayConverter.LEGACY_BITS, HeightmapArrayConverter.TARGET_BITS)) {
            long[] packed = HeightmapArrayConverter.packNonSpanning(values, bits);
            int[] unpacked = HeightmapArrayConverter.unpackNonSpanning(packed, bits, values.length);
            assertArrayEquals(values, unpacked, bits + "-bit pack/unpack round-trip");
            assertTrue(
                    HeightmapArrayConverter.hasZeroPadding(packed, bits, values.length),
                    bits + "-bit output padding must be zero"
            );
        }
    }

    private static void verifyLegacyToCurrentSemanticEquality() {
        int[] values = new int[HeightmapArrayConverter.VALUE_COUNT];
        for (int index = 0; index < values.length; index++) {
            values[index] = switch (index % 6) {
                case 0 -> 0;
                case 1 -> 1;
                case 2 -> 383;
                case 3 -> 384;
                default -> index % 385;
            };
        }
        long[] legacy = HeightmapArrayConverter.packNonSpanning(values, HeightmapArrayConverter.LEGACY_BITS);
        HeightmapArrayConverter.Conversion conversion =
                HeightmapArrayConverter.convert(HeightmapArrayConverter.TARGET_HEIGHT, legacy);
        assertEquals(HeightmapArrayConverter.Status.CONVERTED, conversion.status(), "37-long input must convert");
        assertEquals(HeightmapArrayConverter.TARGET_WORDS, conversion.data().length, "converted word count");
        assertArrayEquals(
                values,
                HeightmapArrayConverter.unpackNonSpanning(
                        conversion.data(),
                        HeightmapArrayConverter.TARGET_BITS,
                        HeightmapArrayConverter.VALUE_COUNT
                ),
                "37-to-43 conversion must preserve all semantic values"
        );
        assertTrue(
                HeightmapArrayConverter.hasZeroPadding(
                        conversion.data(),
                        HeightmapArrayConverter.TARGET_BITS,
                        HeightmapArrayConverter.VALUE_COUNT
                ),
                "converted padding must be zero"
        );
    }

    private static void verifyEveryLegacyValueAndWordBoundary() {
        int[] boundaryPositions = {0, 5, 6, 7, 11, 12, 13, 251, 252, 255};
        for (int value = 0; value <= HeightmapArrayConverter.LEGACY_HEIGHT; value++) {
            int[] values = new int[HeightmapArrayConverter.VALUE_COUNT];
            Arrays.fill(values, value);
            for (int position : boundaryPositions) {
                values[position] = HeightmapArrayConverter.LEGACY_HEIGHT - value;
            }
            long[] legacy = HeightmapArrayConverter.packNonSpanning(values, HeightmapArrayConverter.LEGACY_BITS);
            HeightmapArrayConverter.Conversion conversion =
                    HeightmapArrayConverter.convert(HeightmapArrayConverter.TARGET_HEIGHT, legacy);
            assertEquals(HeightmapArrayConverter.Status.CONVERTED, conversion.status(), "valid value " + value);
            int[] actual = HeightmapArrayConverter.unpackNonSpanning(
                    conversion.data(),
                    HeightmapArrayConverter.TARGET_BITS,
                    HeightmapArrayConverter.VALUE_COUNT
            );
            assertArrayEquals(values, actual, "semantic value " + value + " at storage boundaries");
        }
    }

    private static void verifyIdempotenceAndScope() {
        int[] values = new int[HeightmapArrayConverter.VALUE_COUNT];
        Arrays.fill(values, 384);
        long[] legacy = HeightmapArrayConverter.packNonSpanning(values, HeightmapArrayConverter.LEGACY_BITS);
        HeightmapArrayConverter.Conversion converted =
                HeightmapArrayConverter.convert(HeightmapArrayConverter.TARGET_HEIGHT, legacy);
        HeightmapArrayConverter.Conversion second =
                HeightmapArrayConverter.convert(HeightmapArrayConverter.TARGET_HEIGHT, converted.data());
        assertEquals(HeightmapArrayConverter.Status.ALREADY_CURRENT, second.status(), "43-long array is idempotent");
        assertSame(converted.data(), second.data(), "idempotent path must return the original 43-long object");

        for (int unrelatedHeight : List.of(384, 320, 512, 640)) {
            HeightmapArrayConverter.Conversion untouched = HeightmapArrayConverter.convert(unrelatedHeight, legacy);
            assertEquals(HeightmapArrayConverter.Status.NOT_APPLICABLE, untouched.status(), "height " + unrelatedHeight);
            assertSame(legacy, untouched.data(), "unrelated dimension height must be untouched");
        }
    }

    private static void verifyMalformedInputsFailClosed() {
        for (int length : List.of(0, 1, 36, 38, 42, 44)) {
            long[] input = new long[length];
            HeightmapArrayConverter.Conversion conversion =
                    HeightmapArrayConverter.convert(HeightmapArrayConverter.TARGET_HEIGHT, input);
            assertEquals(HeightmapArrayConverter.Status.REJECTED, conversion.status(), "unexpected length " + length);
            assertSame(input, conversion.data(), "unexpected length must fall back with original object");
            assertTrue(conversion.diagnostic().contains("length"), "unexpected length diagnostic");
        }

        HeightmapArrayConverter.Conversion nullInput =
                HeightmapArrayConverter.convert(HeightmapArrayConverter.TARGET_HEIGHT, null);
        assertEquals(HeightmapArrayConverter.Status.REJECTED, nullInput.status(), "null input");
        assertSame(null, nullInput.data(), "null input remains null");

        int[] validValues = new int[HeightmapArrayConverter.VALUE_COUNT];
        long[] dirtyFullWordPadding =
                HeightmapArrayConverter.packNonSpanning(validValues, HeightmapArrayConverter.LEGACY_BITS);
        dirtyFullWordPadding[0] |= Long.MIN_VALUE;
        assertRejectedSame(dirtyFullWordPadding, "full-word padding");

        long[] dirtyFinalWordPadding =
                HeightmapArrayConverter.packNonSpanning(validValues, HeightmapArrayConverter.LEGACY_BITS);
        dirtyFinalWordPadding[HeightmapArrayConverter.LEGACY_WORDS - 1] |= 1L << 36;
        assertRejectedSame(dirtyFinalWordPadding, "final-word padding");

        int[] outOfRange = new int[HeightmapArrayConverter.VALUE_COUNT];
        outOfRange[255] = HeightmapArrayConverter.LEGACY_HEIGHT + 1;
        long[] invalidValue = HeightmapArrayConverter.packNonSpanning(outOfRange, HeightmapArrayConverter.LEGACY_BITS);
        assertRejectedSame(invalidValue, "out-of-range legacy value");
    }

    private static void assertRejectedSame(long[] input, String label) {
        HeightmapArrayConverter.Conversion conversion =
                HeightmapArrayConverter.convert(HeightmapArrayConverter.TARGET_HEIGHT, input);
        assertEquals(HeightmapArrayConverter.Status.REJECTED, conversion.status(), label);
        assertSame(input, conversion.data(), label + " must fall back with original object");
        assertTrue(conversion.diagnostic() != null && !conversion.diagnostic().isBlank(), label + " diagnostic");
    }

    private static void verifyRuntimeBytecodeContract() throws IOException {
        Path runtimeJar = requiredPath("runtimeMinecraftJar");
        ClassNode chunkAccess = readJarClass(runtimeJar, RUNTIME_CHUNK_ACCESS);
        MethodNode setHeightmap = findMethod(
                chunkAccess,
                "setHeightmap",
                "(Lnet/minecraft/world/level/levelgen/Heightmap$Types;[J)V"
        );
        assertInvocation(
                setHeightmap,
                "net/minecraft/world/level/levelgen/Heightmap",
                "setRawData",
                "(Lnet/minecraft/world/level/chunk/ChunkAccess;Lnet/minecraft/world/level/levelgen/Heightmap$Types;[J)V",
                true,
                "ChunkAccess#setHeightmap must feed the raw long array into Heightmap#setRawData"
        );

        ClassNode heightmap = readJarClass(runtimeJar, RUNTIME_HEIGHTMAP);
        MethodNode constructor = findMethod(
                heightmap,
                "<init>",
                "(Lnet/minecraft/world/level/chunk/ChunkAccess;Lnet/minecraft/world/level/levelgen/Heightmap$Types;)V"
        );
        assertInvocation(constructor, "net/minecraft/world/level/chunk/ChunkAccess", "getHeight", "()I", true,
                "Heightmap bit width must derive from chunk height");
        assertInvocation(constructor, "net/minecraft/util/Mth", "ceillog2", "(I)I", true,
                "Heightmap bit width must use ceillog2(height + 1)");
        assertInvocation(constructor, "net/minecraft/util/SimpleBitStorage", "<init>", "(II)V", true,
                "Heightmap must allocate SimpleBitStorage");

        MethodNode setRawData = findMethod(
                heightmap,
                "setRawData",
                "(Lnet/minecraft/world/level/chunk/ChunkAccess;Lnet/minecraft/world/level/levelgen/Heightmap$Types;[J)V"
        );
        assertInvocation(setRawData, "net/minecraft/util/BitStorage", "getRaw", "()[J", true,
                "setRawData must inspect target storage length");
        assertInvocation(setRawData, "java/lang/System", "arraycopy", "(Ljava/lang/Object;ILjava/lang/Object;II)V", true,
                "matching arrays must copy directly");
        assertInvocation(setRawData, "net/minecraft/world/level/levelgen/Heightmap", "primeHeightmaps",
                "(Lnet/minecraft/world/level/chunk/ChunkAccess;Ljava/util/Set;)V", true,
                "mismatch path must retain vanilla recomputation fallback");
        assertTrue(containsConditionalBranch(setRawData), "setRawData must contain the length mismatch branch");

        Path neoForgeJar = requiredPath("runtimeNeoForgeJar");
        try (JarFile jar = new JarFile(neoForgeJar.toFile())) {
            assertTrue(jar.getJarEntry("META-INF/neoforge.mods.toml") != null,
                    "NeoForge 21.1.241 reference JAR metadata is missing");
        }
    }

    private static void verifyCompiledMixinContract() throws IOException {
        ClassNode mixin;
        try (InputStream stream = Objects.requireNonNull(
                ClassLoader.getSystemResourceAsStream(MIXIN_CLASS),
                "compiled mixin class is missing"
        )) {
            mixin = readClass(stream);
        }

        AnnotationNode mixinAnnotation = findAnnotation(
                mixin.visibleAnnotations,
                mixin.invisibleAnnotations,
                "Lorg/spongepowered/asm/mixin/Mixin;"
        );
        Object targetValue = annotationValue(mixinAnnotation, "value");
        assertTrue(targetValue instanceof List<?>, "@Mixin value must be a list");
        assertTrue(
                ((List<?>) targetValue).contains(Type.getType("Lnet/minecraft/world/level/chunk/ChunkAccess;")),
                "mixin must target ChunkAccess"
        );

        MethodNode handler = findMethod(
                mixin,
                "heightmap384To544Compat$repackLegacyArray",
                "([J)[J"
        );
        AnnotationNode modifyVariable = findAnnotation(
                handler.visibleAnnotations,
                handler.invisibleAnnotations,
                "Lorg/spongepowered/asm/mixin/injection/ModifyVariable;"
        );
        assertEquals(List.of("setHeightmap"), annotationValue(modifyVariable, "method"),
                "mixin method boundary");
        assertEquals(Boolean.TRUE, annotationValue(modifyVariable, "argsOnly"), "argsOnly contract");
        assertEquals(Integer.valueOf(2), annotationValue(modifyVariable, "index"), "long[] local index");
        assertAtValue(modifyVariable, "HEAD");

        for (String requiredCall : List.of("getHeight", "convert", "status", "noteConversion", "warnRejected", "data")) {
            assertInvokesByName(handler, requiredCall, true, "mixin must invoke " + requiredCall);
        }
        for (String forbiddenCall : List.of("setUnsaved", "save", "primeHeightmaps", "setRawData", "arraycopy")) {
            assertInvokesByName(handler, forbiddenCall, false,
                    "mixin must not force world writes or bypass vanilla boundary: " + forbiddenCall);
        }
        assertTrue(!referencesClientNamespace(handler), "BOTH-side mixin must not reference client classes");
    }

    private static void verifyBothSideMetadata() throws IOException {
        String mixinJson = readClasspathText(MIXIN_RESOURCE);
        assertTrue(mixinJson.contains("\"required\": true"), "mixin config must be required");
        assertTrue(mixinJson.contains("\"ChunkAccessMixin\""), "mixin config must register ChunkAccessMixin");
        assertTrue(!mixinJson.contains("\"client\""), "mixin config must not be client-only");

        String metadata = readClasspathText(MOD_METADATA);
        assertTrue(metadata.contains("modId=\"heightmap_384_to_544_compat\""), "mod metadata id");
        assertEquals(2, countOccurrences(metadata, "side=\"BOTH\""),
                "NeoForge and Minecraft dependencies must both declare BOTH side");
    }

    private static String readClasspathText(String resource) throws IOException {
        try (InputStream stream = Objects.requireNonNull(
                ClassLoader.getSystemResourceAsStream(resource),
                "missing classpath resource " + resource
        )) {
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static int countOccurrences(String value, String needle) {
        int count = 0;
        for (int index = 0; (index = value.indexOf(needle, index)) >= 0; index += needle.length()) {
            count++;
        }
        return count;
    }

    private static boolean referencesClientNamespace(MethodNode method) {
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call && call.owner.startsWith("net/minecraft/client/")) {
                return true;
            }
            if (instruction instanceof FieldInsnNode field && field.owner.startsWith("net/minecraft/client/")) {
                return true;
            }
        }
        return false;
    }

    private static boolean containsConditionalBranch(MethodNode method) {
        for (AbstractInsnNode instruction : method.instructions) {
            int opcode = instruction.getOpcode();
            if ((opcode >= Opcodes.IFEQ && opcode <= Opcodes.IF_ACMPNE)
                    || opcode == Opcodes.IFNULL
                    || opcode == Opcodes.IFNONNULL) {
                return true;
            }
        }
        return false;
    }

    private static void assertInvocation(
            MethodNode method,
            String owner,
            String name,
            String descriptor,
            boolean expected,
            String message
    ) {
        boolean actual = false;
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call
                    && owner.equals(call.owner)
                    && name.equals(call.name)
                    && descriptor.equals(call.desc)) {
                actual = true;
                break;
            }
        }
        if (actual != expected) {
            throw new AssertionError(message + ": expected=" + expected + ", actual=" + actual);
        }
    }

    private static void assertInvokesByName(MethodNode method, String name, boolean expected, String message) {
        boolean actual = false;
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call && name.equals(call.name)) {
                actual = true;
                break;
            }
        }
        if (actual != expected) {
            throw new AssertionError(message + ": expected=" + expected + ", actual=" + actual);
        }
    }

    private static AnnotationNode findAnnotation(
            List<AnnotationNode> first,
            List<AnnotationNode> second,
            String descriptor
    ) {
        AnnotationNode result = findAnnotationOrNull(first, descriptor);
        if (result == null) {
            result = findAnnotationOrNull(second, descriptor);
        }
        if (result == null) {
            throw new AssertionError("missing annotation " + descriptor);
        }
        return result;
    }

    private static AnnotationNode findAnnotationOrNull(List<AnnotationNode> annotations, String descriptor) {
        if (annotations == null) {
            return null;
        }
        for (AnnotationNode annotation : annotations) {
            if (descriptor.equals(annotation.desc)) {
                return annotation;
            }
        }
        return null;
    }

    private static Object annotationValue(AnnotationNode annotation, String key) {
        List<Object> values = annotation.values == null ? List.of() : annotation.values;
        for (int index = 0; index + 1 < values.size(); index += 2) {
            if (key.equals(values.get(index))) {
                return values.get(index + 1);
            }
        }
        throw new AssertionError("missing annotation value " + key);
    }

    private static void assertAtValue(AnnotationNode injection, String expected) {
        Object rawAt = annotationValue(injection, "at");
        AnnotationNode at;
        if (rawAt instanceof AnnotationNode singleAt) {
            at = singleAt;
        } else if (rawAt instanceof List<?> atList
                && atList.size() == 1
                && atList.getFirst() instanceof AnnotationNode listedAt) {
            at = listedAt;
        } else {
            throw new AssertionError("injection at must contain exactly one @At: " + rawAt);
        }
        assertEquals(expected, annotationValue(at, "value"), "@At value");
    }

    private static ClassNode readJarClass(Path jarPath, String entryName) throws IOException {
        try (JarFile jar = new JarFile(jarPath.toFile())) {
            JarEntry entry = jar.getJarEntry(entryName);
            if (entry == null) {
                throw new AssertionError("missing " + entryName + " in " + jarPath);
            }
            try (InputStream stream = jar.getInputStream(entry)) {
                return readClass(stream);
            }
        }
    }

    private static ClassNode readClass(InputStream stream) throws IOException {
        ClassNode node = new ClassNode();
        new ClassReader(stream).accept(node, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
        return node;
    }

    private static MethodNode findMethod(ClassNode owner, String name, String descriptor) {
        List<String> available = new ArrayList<>();
        for (MethodNode method : owner.methods) {
            available.add(method.name + method.desc);
            if (name.equals(method.name) && descriptor.equals(method.desc)) {
                return method;
            }
        }
        throw new AssertionError("missing method " + owner.name + "." + name + descriptor + "; available=" + available);
    }

    private static Path requiredPath(String property) {
        String value = System.getProperty(property);
        if (value == null || value.isBlank()) {
            throw new AssertionError("missing system property " + property);
        }
        return Path.of(value);
    }

    private static void assertArrayEquals(int[] expected, int[] actual, String message) {
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(message + ": arrays differ");
        }
    }

    private static void assertSame(Object expected, Object actual, String message) {
        if (expected != actual) {
            throw new AssertionError(message + ": objects are not identical");
        }
    }

    private static void assertTrue(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void assertEquals(Object expected, Object actual, String message) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(message + ": expected=" + expected + ", actual=" + actual);
        }
    }
}
