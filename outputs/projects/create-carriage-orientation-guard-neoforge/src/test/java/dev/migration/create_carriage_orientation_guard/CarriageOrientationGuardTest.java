package dev.migration.create_carriage_orientation_guard;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class CarriageOrientationGuardTest {
    private static final String TARGET_ORIENTED =
            "com/simibubi/create/content/contraptions/OrientedContraptionEntity.class";
    private static final String TARGET_CARRIAGE =
            "com/simibubi/create/content/trains/entity/CarriageContraptionEntity.class";
    private static final String TARGET_CONTROLS =
            "com/simibubi/create/content/contraptions/actors/trainControls/ControlsMovementBehaviour.class";
    private static final String TARGET_RENDERER =
            "com/simibubi/create/content/trains/entity/CarriageContraptionEntityRenderer.class";
    private static final String TARGET_HUD =
            "com/simibubi/create/content/trains/TrainHUD.class";
    private static final String SOURCE_ORIENTED =
            "com/zurrtum/create/content/contraptions/OrientedContraptionEntity.class";
    private static final String SOURCE_CARRIAGE =
            "com/zurrtum/create/content/trains/entity/CarriageContraptionEntity.class";
    private static final String MIXIN_CLASS =
            "dev/migration/create_carriage_orientation_guard/mixin/OrientedContraptionEntityMixin.class";
    private static final String DECISION_CLASS =
            "dev/migration/create_carriage_orientation_guard/CarriageOrientationDecision.class";

    private CarriageOrientationGuardTest() {
    }

    public static void main(String[] args) throws Exception {
        verifyDecisionTruthTable();
        verifyTargetAndSourceEvidence();
        verifyCaseSensitiveTargetEnumReader();
        verifyCompiledMixinBytecode();
        System.out.println("Create carriage orientation guard contract and bytecode tests passed");
    }

    private static void verifyDecisionTruthTable() {
        assertResolution(CarriageOrientationDecision.Resolution.KEEP_RAW, true, false);
        assertResolution(CarriageOrientationDecision.Resolution.KEEP_RAW, true, true);
        assertResolution(CarriageOrientationDecision.Resolution.DERIVE_FROM_ASSEMBLY, false, true);
        assertResolution(CarriageOrientationDecision.Resolution.SAFE_SOUTH, false, false);
    }

    private static void assertResolution(
            CarriageOrientationDecision.Resolution expected,
            boolean rawHorizontal,
            boolean assemblyHorizontal
    ) {
        CarriageOrientationDecision.Resolution actual =
                CarriageOrientationDecision.choose(rawHorizontal, assemblyHorizontal);
        if (actual != expected) {
            throw new AssertionError("resolution expected=" + expected + ", actual=" + actual);
        }
    }

    private static void verifyTargetAndSourceEvidence() throws IOException {
        Path targetJar = requiredPath("targetCreateJar");
        Path sourceJar = requiredPath("sourceReferenceJar");

        ClassNode targetOriented = readJarClass(targetJar, TARGET_ORIENTED);
        MethodNode targetRead = findMethodByName(targetOriented, "readAdditional");
        assertInvokes(targetRead, "readEnum", true,
                "Create 6.0.10 must expose the case-sensitive legacy enum read path");
        MethodNode targetGetter = findMethod(
                targetOriented,
                "getInitialOrientation",
                "()Lnet/minecraft/core/Direction;"
        );
        assertInvokes(targetGetter, "isHorizontal", false,
                "Create 6.0.10 baseline unexpectedly already validates the getter result");

        ClassNode targetCarriage = readJarClass(targetJar, TARGET_CARRIAGE);
        MethodNode targetCreate = findMethodByName(targetCarriage, "create");
        assertInvokes(targetCreate, "getAssemblyDirection", true,
                "Carriage creation must read AssemblyDirection");
        assertInvokes(targetCreate, "getClockWise", true,
                "Carriage creation must derive InitialOrientation clockwise from AssemblyDirection");
        assertInvokes(targetCreate, "setInitialOrientation", true,
                "Carriage creation must install the derived orientation");
        assertHazardCall(readJarClass(targetJar, TARGET_CONTROLS), "renderInContraption");
        assertHazardCall(targetCarriage, "control");
        assertHazardCall(readJarClass(targetJar, TARGET_RENDERER), "lambda$render$1");
        assertHazardCall(readJarClass(targetJar, TARGET_HUD), "renderOverlay");

        ClassNode sourceOriented = readJarClass(sourceJar, SOURCE_ORIENTED);
        MethodNode sourceRead = findMethodByName(sourceOriented, "readAdditional");
        assertInvokes(sourceRead, "readEnum", false,
                "1.21.11 source must use its codec-based orientation reader, not target NBTHelper.readEnum");
        ClassNode sourceCarriage = readJarClass(sourceJar, SOURCE_CARRIAGE);
        MethodNode sourceCreate = findMethodByName(sourceCarriage, "create");
        assertInvokes(sourceCreate, "getAssemblyDirection", true,
                "1.21.11 source carriage creation must read AssemblyDirection");
        assertInvokes(sourceCreate, "setInitialOrientation", true,
                "1.21.11 source carriage creation must install InitialOrientation");
    }

    private static void assertHazardCall(ClassNode owner, String methodName) {
        MethodNode method = findMethodByName(owner, methodName);
        assertInvokes(method, "getInitialOrientation", true,
                owner.name + "." + methodName + " must read InitialOrientation");
        assertInvokes(method, "getCounterClockWise", true,
                owner.name + "." + methodName + " must expose the vertical-direction crash edge");
    }

    private static void verifyCaseSensitiveTargetEnumReader() throws IOException {
        Path targetJar = requiredPath("targetCreateJar");
        ClassNode helper = readNestedJarClass(
                targetJar,
                "META-INF/jarjar/ponder-neoforge-1.0.82+mc1.21.1.jar",
                "net/createmod/catnip/nbt/NBTHelper.class"
        );
        MethodNode readEnum = findMethodByName(helper, "readEnum");
        assertOwnerInvocation(readEnum, "java/lang/String", "equals", true,
                "Target enum reader must demonstrate exact case-sensitive equality");
        assertOwnerInvocation(readEnum, "java/lang/String", "equalsIgnoreCase", false,
                "Target enum reader unexpectedly accepts legacy lowercase values");
        assertOwnerInvocation(readEnum, "java/lang/String", "toUpperCase", false,
                "Target enum reader unexpectedly normalizes legacy lowercase values");
        if (!containsOpcode(readEnum, Opcodes.AALOAD)) {
            throw new AssertionError("Target enum reader no longer has an enum-array fallback path");
        }
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
                "createCarriageOrientationGuard$resolveInvalidCarriageOrientation",
                "(Lorg/spongepowered/asm/mixin/injection/callback/CallbackInfoReturnable;)V"
        );
        AnnotationNode inject = findAnnotation(
                guard.visibleAnnotations,
                guard.invisibleAnnotations,
                "Lorg/spongepowered/asm/mixin/injection/Inject;"
        );
        assertAnnotationValue(inject, "method", List.of("getInitialOrientation"));
        assertAnnotationValue(inject, "cancellable", Boolean.TRUE);
        assertAtValue(inject, "RETURN");

        for (String invocation : List.of(
                "getReturnValue",
                "getContraption",
                "getAssemblyDirection",
                "resolve",
                "warnFallback",
                "setReturnValue"
        )) {
            assertInvokes(guard, invocation, true, "Mixin must invoke " + invocation);
        }
        for (String forbidden : List.of(
                "setInitialOrientation",
                "writeAdditional",
                "readAdditional",
                "putString",
                "put",
                "save"
        )) {
            assertInvokes(guard, forbidden, false,
                    "Read-only runtime guard must not invoke mutator " + forbidden);
        }
        if (!containsConditionalBranch(guard)) {
            throw new AssertionError("Mixin guard bytecode has no conditional branch");
        }
        if (mixin.name.contains("client") || referencesClientNamespace(guard)) {
            throw new AssertionError("BOTH-side guard must not reference client-only classes");
        }

        ClassNode decision;
        try (InputStream stream = Objects.requireNonNull(
                ClassLoader.getSystemResourceAsStream(DECISION_CLASS),
                "Compiled decision class is missing from the test classpath"
        )) {
            decision = readClass(stream);
        }
        MethodNode resolve = findMethod(
                decision,
                "resolve",
                "(Lnet/minecraft/core/Direction;Lnet/minecraft/core/Direction;)Lnet/minecraft/core/Direction;"
        );
        for (String invocation : List.of("getAxis", "isHorizontal", "choose", "getClockWise")) {
            assertInvokes(resolve, invocation, true, "Decision helper must invoke " + invocation);
        }
        if (!readsField(resolve, "net/minecraft/core/Direction", "SOUTH")) {
            throw new AssertionError("Decision helper must provide a horizontal fail-safe");
        }
        if (referencesClientNamespace(resolve)) {
            throw new AssertionError("BOTH-side decision helper must not reference client-only classes");
        }
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

    private static boolean readsField(MethodNode method, String owner, String name) {
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof FieldInsnNode field
                    && field.getOpcode() == Opcodes.GETSTATIC
                    && owner.equals(field.owner)
                    && name.equals(field.name)) {
                return true;
            }
        }
        return false;
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

    private static boolean containsOpcode(MethodNode method, int opcode) {
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction.getOpcode() == opcode) {
                return true;
            }
        }
        return false;
    }

    private static void assertOwnerInvocation(
            MethodNode method,
            String owner,
            String name,
            boolean expected,
            String message
    ) {
        boolean actual = false;
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call
                    && owner.equals(call.owner)
                    && name.equals(call.name)) {
                actual = true;
                break;
            }
        }
        if (actual != expected) {
            throw new AssertionError(message + ": " + owner + "." + name + " expected=" + expected);
        }
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

    private static void assertAtValue(AnnotationNode inject, String expected) {
        Object rawAt = annotationValue(inject, "at");
        if (!(rawAt instanceof List<?> atList)
                || atList.size() != 1
                || !(atList.getFirst() instanceof AnnotationNode at)) {
            throw new AssertionError("Inject.at must contain exactly one @At annotation: " + rawAt);
        }
        assertAnnotationValue(at, "value", expected);
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
            JarEntry entry = jar.getJarEntry(entryName);
            if (entry == null) {
                throw new AssertionError("Missing " + entryName + " in " + jarPath);
            }
            try (InputStream stream = jar.getInputStream(entry)) {
                return readClass(stream);
            }
        }
    }

    private static ClassNode readNestedJarClass(
            Path outerJarPath,
            String nestedEntryName,
            String classEntryName
    ) throws IOException {
        byte[] nestedBytes;
        try (JarFile outer = new JarFile(outerJarPath.toFile())) {
            JarEntry nestedEntry = outer.getJarEntry(nestedEntryName);
            if (nestedEntry == null) {
                throw new AssertionError("Missing nested JAR " + nestedEntryName + " in " + outerJarPath);
            }
            try (InputStream stream = outer.getInputStream(nestedEntry)) {
                nestedBytes = readAll(stream);
            }
        }
        try (java.util.jar.JarInputStream nested =
                     new java.util.jar.JarInputStream(new ByteArrayInputStream(nestedBytes))) {
            for (JarEntry entry; (entry = nested.getNextJarEntry()) != null; ) {
                if (classEntryName.equals(entry.getName())) {
                    return readClass(new ByteArrayInputStream(readAll(nested)));
                }
            }
        }
        throw new AssertionError("Missing " + classEntryName + " in nested JAR " + nestedEntryName);
    }

    private static byte[] readAll(InputStream stream) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        stream.transferTo(output);
        return output.toByteArray();
    }

    private static ClassNode readClass(InputStream stream) throws IOException {
        ClassNode node = new ClassNode();
        new ClassReader(stream).accept(node, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
        return node;
    }

    private static MethodNode findMethodByName(ClassNode owner, String name) {
        List<MethodNode> matches = owner.methods.stream()
                .filter(method -> method.name.equals(name))
                .toList();
        if (matches.size() != 1) {
            throw new AssertionError(
                    "Expected one method " + owner.name + "." + name + ", found="
                            + matches.stream().map(method -> method.name + method.desc).toList()
            );
        }
        return matches.getFirst();
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
