package dev.migration.create_chute_unload_guard;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
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

public final class ChuteUnloadGuardTest {
    private static final String TARGET_CHUTE =
            "com/simibubi/create/content/logistics/chute/ChuteBlockEntity.class";
    private static final String SOURCE_CHUTE =
            "com/zurrtum/create/content/logistics/chute/ChuteBlockEntity.class";
    private static final String MIXIN_CLASS =
            "dev/migration/create_chute_unload_guard/mixin/ChuteBlockEntityMixin.class";

    private ChuteUnloadGuardTest() {
    }

    public static void main(String[] args) throws Exception {
        verifyDecisionTruthTable();
        verifySourceAndTargetEvidence();
        verifyCompiledMixinBytecode();
        System.out.println("Create chute unload guard parity and bytecode tests passed");
    }

    private static void verifyDecisionTruthTable() {
        assertDecision(true, false, false, "missing level must remove");
        assertDecision(true, false, true, "missing level dominates impossible chute state");
        assertDecision(true, true, false, "non-chute state must remove");
        assertDecision(false, true, true, "valid chute must retain and run original onAdded");
    }

    private static void assertDecision(
            boolean expected,
            boolean hasLevel,
            boolean chuteAtPosition,
            String message
    ) {
        boolean actual = ChuteGuardDecision.shouldRemove(hasLevel, chuteAtPosition);
        if (actual != expected) {
            throw new AssertionError(message + ": expected=" + expected + ", actual=" + actual);
        }
    }

    private static void verifySourceAndTargetEvidence() throws IOException {
        Path targetJar = requiredPath("targetCreateJar");
        Path sourceJar = requiredPath("sourceReferenceJar");
        MethodNode targetOnAdded = findMethod(readJarClass(targetJar, TARGET_CHUTE), "onAdded", "()V");
        MethodNode sourceOnAdded = findMethod(readJarClass(sourceJar, SOURCE_CHUTE), "onAdded", "()V");

        assertInvokes(targetOnAdded, "refreshBlockState", true,
                "Create 6.0.10 target must expose the crashing refresh path");
        assertInvokes(targetOnAdded, "isChute", false,
                "Create 6.0.10 baseline unexpectedly already contains the source guard");
        assertInvokes(sourceOnAdded, "isChute", true,
                "1.21.11 source reference must check the block state before refreshing");
        assertInvokes(sourceOnAdded, "method_11012", true,
                "1.21.11 source reference must remove the stale block entity on guard failure");
        assertInvokes(sourceOnAdded, "refreshBlockState", true,
                "1.21.11 source reference must retain refresh for valid chutes");
    }

    private static void verifyCompiledMixinBytecode() throws IOException {
        ClassNode mixin;
        try (InputStream stream = Objects.requireNonNull(
                ClassLoader.getSystemResourceAsStream(MIXIN_CLASS),
                "Compiled mixin class is missing from the test classpath"
        )) {
            mixin = readClass(stream);
        }
        MethodNode guard = findMethod(
                mixin,
                "createChuteUnloadGuard$guardOnAdded",
                "(Lorg/spongepowered/asm/mixin/injection/callback/CallbackInfo;)V"
        );
        AnnotationNode inject = findAnnotation(
                guard.visibleAnnotations,
                guard.invisibleAnnotations,
                "Lorg/spongepowered/asm/mixin/injection/Inject;"
        );
        assertAnnotationValue(inject, "method", List.of("onAdded"));
        assertAnnotationValue(inject, "cancellable", Boolean.TRUE);
        assertHeadInjection(inject);
        assertInvokes(guard, "isChute", true, "Mixin must evaluate the actual block state");
        assertInvokes(guard, "shouldRemove", true, "Mixin must use the tested source-equivalent predicate");
        assertInvokes(guard, "setRemoved", true, "Mixin must remove a stale chute block entity");
        assertInvokes(guard, "cancel", true, "Mixin must cancel the unsafe original onAdded path");
        if (!containsConditionalBranch(guard)) {
            throw new AssertionError("Mixin guard bytecode has no conditional branch");
        }
    }

    private static boolean containsConditionalBranch(MethodNode method) {
        for (AbstractInsnNode instruction : method.instructions) {
            int opcode = instruction.getOpcode();
            if (opcode >= Opcodes.IFEQ && opcode <= Opcodes.IF_ACMPNE) {
                return true;
            }
        }
        return false;
    }

    private static void assertInvokes(MethodNode method, String name, boolean expected, String message) {
        boolean actual = false;
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call && call.name.equals(name)) {
                actual = true;
                break;
            }
        }
        if (actual != expected) {
            throw new AssertionError(message + ": invocation " + name + " expected=" + expected);
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
        if (result != null) {
            return result;
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

    private static void assertAnnotationValue(AnnotationNode annotation, String key, Object expected) {
        Object actual = annotationValue(annotation, key);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Annotation value " + key + " expected=" + expected + ", actual=" + actual
            );
        }
    }

    private static void assertHeadInjection(AnnotationNode inject) {
        Object rawAt = annotationValue(inject, "at");
        if (!(rawAt instanceof List<?> atList)
                || atList.size() != 1
                || !(atList.getFirst() instanceof AnnotationNode at)) {
            throw new AssertionError("Inject.at must contain exactly one @At annotation: " + rawAt);
        }
        if (!"Lorg/spongepowered/asm/mixin/injection/At;".equals(at.desc)) {
            throw new AssertionError("Unexpected Inject.at descriptor " + at.desc);
        }
        assertAnnotationValue(at, "value", "HEAD");
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
        throw new AssertionError(
                "Missing method " + owner.name + "." + name + descriptor + "; available=" + available
        );
    }
}
