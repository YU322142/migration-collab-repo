import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Enumeration;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnList;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.VarInsnNode;

/**
 * Backports Immersive Paintings 0.7.9's hanging-entity persistence fixes to
 * the NeoForge 1.21.1 0.7.8 build.
 */
public final class PatchImmersivePaintingEntity {
    private static final String CLASS_ENTRY =
            "net/conczin/immersive_paintings/entity/ImmersivePaintingEntity.class";
    private static final String CLASS_NAME =
            "net/conczin/immersive_paintings/entity/ImmersivePaintingEntity";
    private static final String HANGING_ENTITY =
            "net/minecraft/world/entity/decoration/HangingEntity";
    private static final String COMPOUND_TAG = "Lnet/minecraft/nbt/CompoundTag;";
    private static final String DIRECTION = "Lnet/minecraft/core/Direction;";
    private static final String EXPECTED_CLASS_SHA256 =
            "0afa7c9ff8110535a3ade200392a6515ebe7701ff4536d4305e80b1ee4784eef";
    private static final String LEGACY_ROTATION_KEY = "Rotation";
    private static final String VERTICAL_ROTATION_KEY = "VRotation";

    private PatchImmersivePaintingEntity() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: PatchImmersivePaintingEntity <original-jar> <output-jar>");
        }

        Path inputJar = Path.of(args[0]).toAbsolutePath().normalize();
        Path outputJar = Path.of(args[1]).toAbsolutePath().normalize();
        if (inputJar.equals(outputJar)) {
            throw new IllegalArgumentException("Input and output JARs must differ");
        }

        byte[] originalClass = readJarEntry(inputJar, CLASS_ENTRY);
        requireEquals(EXPECTED_CLASS_SHA256, sha256(originalClass),
                "Unexpected ImmersivePaintingEntity class");
        byte[] patchedClass = patchClass(originalClass);

        Files.createDirectories(outputJar.getParent());
        writePatchedJar(inputJar, outputJar, patchedClass);

        byte[] verificationClass = readJarEntry(outputJar, CLASS_ENTRY);
        requireEquals(sha256(patchedClass), sha256(verificationClass),
                "Output JAR contains the wrong patched class");
        verifyPatchedClass(verificationClass);

        System.out.println("input_jar=" + inputJar);
        System.out.println("output_jar=" + outputJar);
        System.out.println("original_class_sha256=" + sha256(originalClass));
        System.out.println("patched_class_sha256=" + sha256(patchedClass));
        System.out.println("output_jar_sha256=" + sha256(Files.readAllBytes(outputJar)));
    }

    private static byte[] patchClass(byte[] originalClass) {
        ClassNode node = readClass(originalClass);
        requireEquals(CLASS_NAME, node.name, "Unexpected class name");

        MethodNode save = findMethod(node, "addAdditionalSaveData", "(" + COMPOUND_TAG + ")V");
        MethodNode load = findMethod(node, "readAdditionalSaveData", "(" + COMPOUND_TAG + ")V");
        replaceSingleRotationKey(save);
        replaceSingleRotationKey(load);

        MethodInsnNode superLoad = null;
        for (AbstractInsnNode instruction : load.instructions) {
            if (instruction instanceof MethodInsnNode call
                    && call.getOpcode() == Opcodes.INVOKESPECIAL
                    && HANGING_ENTITY.equals(call.owner)
                    && "readAdditionalSaveData".equals(call.name)
                    && ("(" + COMPOUND_TAG + ")V").equals(call.desc)) {
                if (superLoad != null) {
                    throw new IllegalStateException("Multiple HangingEntity load calls");
                }
                superLoad = call;
            }
        }
        if (superLoad == null) {
            throw new IllegalStateException("Missing HangingEntity load call");
        }

        InsnList reconcile = new InsnList();
        reconcile.add(new VarInsnNode(Opcodes.ALOAD, 0));
        reconcile.add(new VarInsnNode(Opcodes.ALOAD, 0));
        reconcile.add(new FieldInsnNode(Opcodes.GETFIELD, CLASS_NAME, "direction", DIRECTION));
        reconcile.add(new VarInsnNode(Opcodes.ALOAD, 0));
        reconcile.add(new FieldInsnNode(Opcodes.GETFIELD, CLASS_NAME, "rotation", "I"));
        reconcile.add(new MethodInsnNode(Opcodes.INVOKEVIRTUAL, CLASS_NAME, "setDirection",
                "(" + DIRECTION + "I)V", false));
        load.instructions.insert(superLoad, reconcile);

        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        byte[] patched = writer.toByteArray();
        verifyPatchedClass(patched);
        return patched;
    }

    private static void replaceSingleRotationKey(MethodNode method) {
        int replacements = 0;
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof LdcInsnNode constant
                    && LEGACY_ROTATION_KEY.equals(constant.cst)) {
                constant.cst = VERTICAL_ROTATION_KEY;
                replacements++;
            }
        }
        if (replacements != 1) {
            throw new IllegalStateException(method.name
                    + " expected one Rotation key, found " + replacements);
        }
    }

    private static void verifyPatchedClass(byte[] bytes) {
        ClassNode node = readClass(bytes);
        MethodNode save = findMethod(node, "addAdditionalSaveData", "(" + COMPOUND_TAG + ")V");
        MethodNode load = findMethod(node, "readAdditionalSaveData", "(" + COMPOUND_TAG + ")V");
        requireKeyCounts(save, 0, 1);
        requireKeyCounts(load, 0, 1);

        int reconciliationCalls = 0;
        boolean afterSuper = false;
        boolean reconciliationAfterSuper = false;
        for (AbstractInsnNode instruction : load.instructions) {
            if (instruction instanceof MethodInsnNode call) {
                if (call.getOpcode() == Opcodes.INVOKESPECIAL
                        && HANGING_ENTITY.equals(call.owner)
                        && "readAdditionalSaveData".equals(call.name)) {
                    afterSuper = true;
                } else if (call.getOpcode() == Opcodes.INVOKEVIRTUAL
                        && CLASS_NAME.equals(call.owner)
                        && "setDirection".equals(call.name)
                        && ("(" + DIRECTION + "I)V").equals(call.desc)) {
                    reconciliationCalls++;
                    reconciliationAfterSuper |= afterSuper;
                }
            }
        }
        if (reconciliationCalls != 1 || !reconciliationAfterSuper) {
            throw new IllegalStateException("Direction reconciliation verification failed");
        }
    }

    private static void requireKeyCounts(MethodNode method, int legacy, int vertical) {
        int legacyCount = 0;
        int verticalCount = 0;
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction instanceof LdcInsnNode constant) {
                if (LEGACY_ROTATION_KEY.equals(constant.cst)) {
                    legacyCount++;
                } else if (VERTICAL_ROTATION_KEY.equals(constant.cst)) {
                    verticalCount++;
                }
            }
        }
        if (legacyCount != legacy || verticalCount != vertical) {
            throw new IllegalStateException(method.name + " key counts: Rotation="
                    + legacyCount + " VRotation=" + verticalCount);
        }
    }

    private static MethodNode findMethod(ClassNode node, String name, String descriptor) {
        return node.methods.stream()
                .filter(candidate -> name.equals(candidate.name)
                        && descriptor.equals(candidate.desc))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "Missing method " + name + descriptor));
    }

    private static ClassNode readClass(byte[] bytes) {
        ClassNode node = new ClassNode();
        new ClassReader(bytes).accept(node, 0);
        return node;
    }

    private static byte[] readJarEntry(Path jar, String entryName) throws IOException {
        try (ZipFile zip = new ZipFile(jar.toFile())) {
            ZipEntry entry = zip.getEntry(entryName);
            if (entry == null) {
                throw new IOException("Missing JAR entry: " + entryName);
            }
            try (InputStream input = zip.getInputStream(entry)) {
                return input.readAllBytes();
            }
        }
    }

    private static void writePatchedJar(
            Path inputJar, Path outputJar, byte[] patchedClass) throws IOException {
        int inputEntries = 0;
        int outputEntries = 0;
        try (ZipFile input = new ZipFile(inputJar.toFile());
             OutputStream fileOutput = Files.newOutputStream(outputJar);
             ZipOutputStream output = new ZipOutputStream(fileOutput, StandardCharsets.UTF_8)) {
            output.setLevel(9);
            Enumeration<? extends ZipEntry> entries = input.entries();
            while (entries.hasMoreElements()) {
                ZipEntry sourceEntry = entries.nextElement();
                inputEntries++;
                String upperName = sourceEntry.getName().toUpperCase(Locale.ROOT);
                if (upperName.startsWith("META-INF/")
                        && (upperName.endsWith(".SF") || upperName.endsWith(".RSA")
                        || upperName.endsWith(".DSA") || upperName.endsWith(".EC"))) {
                    throw new IOException("Refusing to patch signed JAR entry: "
                            + sourceEntry.getName());
                }

                ZipEntry targetEntry = new ZipEntry(sourceEntry.getName());
                targetEntry.setTime(0L);
                output.putNextEntry(targetEntry);
                if (!sourceEntry.isDirectory()) {
                    if (CLASS_ENTRY.equals(sourceEntry.getName())) {
                        output.write(patchedClass);
                    } else {
                        try (InputStream entryInput = input.getInputStream(sourceEntry)) {
                            entryInput.transferTo(output);
                        }
                    }
                }
                output.closeEntry();
                outputEntries++;
            }
        }
        if (inputEntries != outputEntries) {
            throw new IOException("JAR entry count changed: input=" + inputEntries
                    + " output=" + outputEntries);
        }
    }

    private static String sha256(byte[] bytes) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder result = new StringBuilder(digest.length * 2);
        for (byte value : digest) {
            result.append(String.format(Locale.ROOT, "%02x", value & 0xff));
        }
        return result.toString();
    }

    private static void requireEquals(Object expected, Object actual, String message) {
        if (!expected.equals(actual)) {
            throw new IllegalStateException(message + ": expected=" + expected
                    + " actual=" + actual);
        }
    }
}
