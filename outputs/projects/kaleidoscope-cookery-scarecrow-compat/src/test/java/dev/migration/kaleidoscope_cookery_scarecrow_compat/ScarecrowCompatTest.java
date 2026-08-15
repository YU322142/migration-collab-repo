package dev.migration.kaleidoscope_cookery_scarecrow_compat;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.Tag;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.jar.JarFile;

public final class ScarecrowCompatTest {
    private static final String TARGET_SCARECROW =
            "com/github/ysbbbbbb/kaleidoscopecookery/entity/ScarecrowEntity.class";
    private static final String SOURCE_SCARECROW = TARGET_SCARECROW;
    private static final String MIXIN_CLASS =
            "dev/migration/kaleidoscope_cookery_scarecrow_compat/mixin/ScarecrowEntityMixin.class";

    private ScarecrowCompatTest() {
    }

    public static void main(String[] args) throws Exception {
        verifyNormalisationTruthTable();
        verifySourceAndTargetEvidence();
        verifyCompiledMixinBytecode();
        System.out.println("Kaleidoscope Cookery Scarecrow compatibility tests passed");
    }

    private static void verifyNormalisationTruthTable() {
        CompoundTag source = new CompoundTag();
        ListTag armor = new ListTag();
        CompoundTag dragonHead = new CompoundTag();
        dragonHead.putInt("Slot", 3);
        dragonHead.putString("id", "minecraft:dragon_head");
        dragonHead.putInt("count", 1);
        armor.add(dragonHead);
        source.put(LegacyScarecrowNbt.ARMOR_ITEMS, armor);

        int first = LegacyScarecrowNbt.normalize(source);
        assertEquals(1, first, "one legacy list must convert");
        assertTrue(!source.contains(LegacyScarecrowNbt.HAND_ITEMS),
                "absent HandItems must remain absent");
        CompoundTag converted = source.getCompound(LegacyScarecrowNbt.ARMOR_ITEMS);
        assertEquals(4, converted.getInt("Size"), "armor logical size");
        ListTag items = converted.getList("Items", Tag.TAG_COMPOUND);
        assertEquals(1, items.size(), "dragon head item count");
        assertEquals(3, items.getCompound(0).getInt("Slot"), "dragon head slot");
        assertEquals("minecraft:dragon_head", items.getCompound(0).getString("id"), "dragon head id");

        CompoundTag afterFirst = source.copy();
        int second = LegacyScarecrowNbt.normalize(source);
        assertEquals(0, second, "normalisation must be idempotent");
        assertEquals(afterFirst, source, "target handler compound must remain byte-semantically unchanged");

        CompoundTag hands = new CompoundTag();
        hands.put(LegacyScarecrowNbt.HAND_ITEMS, new ListTag());
        assertEquals(1, LegacyScarecrowNbt.normalize(hands), "empty legacy hand list still needs its Size=2 wrapper");
        assertEquals(2, hands.getCompound(LegacyScarecrowNbt.HAND_ITEMS).getInt("Size"), "hand logical size");

        CompoundTag unrelated = new CompoundTag();
        unrelated.putString("ArmorItems", "not-a-list");
        CompoundTag before = unrelated.copy();
        assertEquals(0, LegacyScarecrowNbt.normalize(unrelated), "wrong tag types must be left untouched");
        assertEquals(before, unrelated, "wrong tag types must be preserved for fail-closed diagnosis");
    }

    private static void verifySourceAndTargetEvidence() throws IOException {
        ClassNode target = readJarClass(requiredPath("targetCookeryJar"), TARGET_SCARECROW);
        ClassNode source = readJarClass(requiredPath("sourceReferenceJar"), SOURCE_SCARECROW);

        MethodNode targetLoad = findMethodByInvocations(target, "getCompound", "getStackInSlot");
        assertInvokes(targetLoad, "deserializeNBT", true,
                "1.21.1 target must use NeoForge ItemStackHandler deserialisation");
        assertInvokes(targetLoad, "getCompound", true,
                "1.21.1 target must request compound inventory fields");
        assertInvokes(targetLoad, "getStackInSlot", true,
                "1.21.1 target must iterate fixed logical slots");

        MethodNode sourceLoad = findMethodByInvocations(source, "method_71437", "method_71368");
        assertInvokes(sourceLoad, "method_71437", true,
                "1.21.11 source must read a list of slotted ItemStacks");
        assertInvokes(sourceLoad, "method_71368", true,
                "1.21.11 source must validate the explicit slot against logical size");
    }

    private static void verifyCompiledMixinBytecode() throws IOException {
        ClassNode mixin;
        try (InputStream stream = Objects.requireNonNull(
                ClassLoader.getSystemResourceAsStream(MIXIN_CLASS),
                "Compiled mixin class is missing from the test classpath"
        )) {
            mixin = readClass(stream);
        }
        MethodNode method = findMethod(
                mixin,
                "candidate13$normalizeLegacyInventory",
                "(Lnet/minecraft/nbt/CompoundTag;Lorg/spongepowered/asm/mixin/injection/callback/CallbackInfo;)V"
        );
        AnnotationNode inject = findAnnotation(
                method.visibleAnnotations,
                method.invisibleAnnotations,
                "Lorg/spongepowered/asm/mixin/injection/Inject;"
        );
        assertAnnotationContains(inject, "method", "readAdditionalSaveData");
        assertHeadInjection(inject);
        assertInvokes(method, "normalize", true, "Mixin must invoke the pure legacy normaliser at HEAD");
    }

    private static MethodNode findMethodByInvocations(ClassNode owner, String... invocations) {
        for (MethodNode method : owner.methods) {
            boolean all = true;
            for (String invocation : invocations) {
                if (!invokes(method, invocation)) {
                    all = false;
                    break;
                }
            }
            if (all) {
                return method;
            }
        }
        throw new AssertionError("No method in " + owner.name + " invokes " + List.of(invocations));
    }

    private static boolean invokes(MethodNode method, String name) {
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call && call.name.equals(name)) {
                return true;
            }
        }
        return false;
    }

    private static void assertInvokes(MethodNode method, String name, boolean expected, String message) {
        boolean actual = invokes(method, name);
        if (actual != expected) {
            throw new AssertionError(message + ": invocation " + name + " expected=" + expected);
        }
    }

    private static AnnotationNode findAnnotation(
            List<AnnotationNode> first,
            List<AnnotationNode> second,
            String descriptor
    ) {
        AnnotationNode value = findAnnotationOrNull(first, descriptor);
        if (value == null) {
            value = findAnnotationOrNull(second, descriptor);
        }
        if (value != null) {
            return value;
        }
        throw new AssertionError("Missing annotation " + descriptor);
    }

    private static AnnotationNode findAnnotationOrNull(
            List<AnnotationNode> annotations,
            String descriptor
    ) {
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

    private static void assertAnnotationContains(AnnotationNode annotation, String key, Object expected) {
        Object actual = annotationValue(annotation, key);
        if (actual instanceof List<?> values) {
            if (!values.contains(expected)) {
                throw new AssertionError("Annotation " + key + " does not contain " + expected + ": " + values);
            }
            return;
        }
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError("Annotation " + key + " expected=" + expected + ", actual=" + actual);
        }
    }

    private static void assertHeadInjection(AnnotationNode inject) {
        Object rawAt = annotationValue(inject, "at");
        if (!(rawAt instanceof List<?> atList)
                || atList.size() != 1
                || !(atList.getFirst() instanceof AnnotationNode at)) {
            throw new AssertionError("Inject.at must contain exactly one @At annotation: " + rawAt);
        }
        Object value = annotationValue(at, "value");
        if (!"HEAD".equals(value)) {
            throw new AssertionError("Injection must run at HEAD, actual=" + value);
        }
    }

    private static Object annotationValue(AnnotationNode annotation, String key) {
        List<Object> values = annotation.values == null ? List.of() : annotation.values;
        for (int index = 0; index + 1 < values.size(); index += 2) {
            if (key.equals(values.get(index))) {
                return values.get(index + 1);
            }
        }
        throw new AssertionError("Missing annotation value " + key);
    }

    private static Path requiredPath(String property) {
        String value = System.getProperty(property);
        if (value == null || value.isBlank()) {
            throw new AssertionError("Missing system property " + property);
        }
        return Path.of(value);
    }

    private static ClassNode readJarClass(Path jarPath, String entryName) throws IOException {
        try (JarFile jar = new JarFile(jarPath.toFile())) {
            var entry = jar.getJarEntry(entryName);
            if (entry == null) {
                throw new AssertionError("Missing " + entryName + " in " + jarPath);
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
            if (method.name.equals(name) && method.desc.equals(descriptor)) {
                return method;
            }
        }
        throw new AssertionError("Missing " + owner.name + "." + name + descriptor + "; available=" + available);
    }

    private static void assertTrue(boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }

    private static void assertEquals(Object expected, Object actual, String message) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(message + ": expected=" + expected + ", actual=" + actual);
        }
    }
}
