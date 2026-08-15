import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodNode;

/**
 * Adds the missing descriptor to MishangUC 1.6.1's GameRenderer mixin selector.
 * The descriptor keeps Connector's Mojmap remap unambiguous when GameRenderer
 * has overloaded pick methods and another mixin transforms the same class first.
 */
public final class PatchMishangucGameRendererMixin {
    private static final String CLASS_ENTRY =
            "pers/solid/mishang/uc/mixin/GameRendererMixin.class";
    private static final String EXPECTED_CLASS_SHA256 =
            "4443d5e299dc7e78bf5d0fb0a367e19b4afce37e7261282d7630fd429ce14150";
    private static final String METHOD_NAME = "modifyRaycastCall";
    private static final String METHOD_DESC = "(Z)Z";
    private static final String MODIFY_ARG_DESC =
            "Lorg/spongepowered/asm/mixin/injection/ModifyArg;";
    private static final String AT_DESC =
            "Lorg/spongepowered/asm/mixin/injection/At;";
    private static final String ORIGINAL_SELECTOR = "method_56153";
    private static final String PATCHED_SELECTOR =
            "method_56153(Lnet/minecraft/class_1297;DDF)Lnet/minecraft/class_239;";
    private static final String EXPECTED_INVOKE_TARGET =
            "Lnet/minecraft/class_1297;method_5745(DFZ)Lnet/minecraft/class_239;";

    private PatchMishangucGameRendererMixin() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: PatchMishangucGameRendererMixin <original-jar> <output-jar>");
        }

        Path inputJar = Path.of(args[0]).toAbsolutePath().normalize();
        Path outputJar = Path.of(args[1]).toAbsolutePath().normalize();
        if (inputJar.equals(outputJar)) {
            throw new IllegalArgumentException("Input and output JARs must differ");
        }

        byte[] originalClass = readJarEntry(inputJar, CLASS_ENTRY);
        requireEquals(EXPECTED_CLASS_SHA256, sha256(originalClass),
                "Unexpected MishangUC GameRendererMixin class");
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
        System.out.println("selector=" + PATCHED_SELECTOR);
    }

    private static byte[] patchClass(byte[] originalClass) {
        ClassNode node = readClass(originalClass);
        MethodNode method = node.methods.stream()
                .filter(candidate -> candidate.name.equals(METHOD_NAME)
                        && candidate.desc.equals(METHOD_DESC))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "Missing method " + METHOD_NAME + METHOD_DESC));
        AnnotationNode modifyArg = findAnnotation(method.visibleAnnotations, MODIFY_ARG_DESC);

        Object methodValue = annotationValue(modifyArg, "method");
        if (!(methodValue instanceof List<?> selectors) || selectors.size() != 1
                || !ORIGINAL_SELECTOR.equals(selectors.get(0))) {
            throw new IllegalStateException("Unexpected @ModifyArg method selector: " + methodValue);
        }

        Object atValue = annotationValue(modifyArg, "at");
        if (!(atValue instanceof AnnotationNode at) || !AT_DESC.equals(at.desc)) {
            throw new IllegalStateException("Unexpected @ModifyArg at value");
        }
        requireEquals("INVOKE", annotationValue(at, "value"), "Unexpected @At value");
        requireEquals(EXPECTED_INVOKE_TARGET, annotationValue(at, "target"),
                "Unexpected @At target");
        requireEquals(Integer.valueOf(2), annotationValue(modifyArg, "index"),
                "Unexpected @ModifyArg index");

        ArrayList<String> patchedSelectors = new ArrayList<>();
        patchedSelectors.add(PATCHED_SELECTOR);
        setAnnotationValue(modifyArg, "method", patchedSelectors);

        ClassWriter writer = new ClassWriter(0);
        node.accept(writer);
        byte[] patched = writer.toByteArray();
        verifyPatchedClass(patched);
        return patched;
    }

    private static void verifyPatchedClass(byte[] bytes) {
        ClassNode node = readClass(bytes);
        MethodNode method = node.methods.stream()
                .filter(candidate -> candidate.name.equals(METHOD_NAME)
                        && candidate.desc.equals(METHOD_DESC))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("Patched method disappeared"));
        AnnotationNode modifyArg = findAnnotation(method.visibleAnnotations, MODIFY_ARG_DESC);
        Object methodValue = annotationValue(modifyArg, "method");
        if (!(methodValue instanceof List<?> selectors) || selectors.size() != 1
                || !PATCHED_SELECTOR.equals(selectors.get(0))) {
            throw new IllegalStateException("Patched selector verification failed: " + methodValue);
        }
        Object atValue = annotationValue(modifyArg, "at");
        if (!(atValue instanceof AnnotationNode at)) {
            throw new IllegalStateException("Patched @At disappeared");
        }
        requireEquals(EXPECTED_INVOKE_TARGET, annotationValue(at, "target"),
                "Patched @At target changed");
        requireEquals(Integer.valueOf(2), annotationValue(modifyArg, "index"),
                "Patched @ModifyArg index changed");
    }

    private static ClassNode readClass(byte[] bytes) {
        ClassNode node = new ClassNode();
        new ClassReader(bytes).accept(node, 0);
        return node;
    }

    private static AnnotationNode findAnnotation(
            List<AnnotationNode> annotations, String descriptor) {
        if (annotations == null) {
            throw new IllegalStateException("Method has no visible annotations");
        }
        return annotations.stream()
                .filter(annotation -> descriptor.equals(annotation.desc))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "Missing annotation " + descriptor));
    }

    private static Object annotationValue(AnnotationNode annotation, String key) {
        if (annotation.values == null) {
            return null;
        }
        for (int i = 0; i < annotation.values.size(); i += 2) {
            if (key.equals(annotation.values.get(i))) {
                return annotation.values.get(i + 1);
            }
        }
        return null;
    }

    private static void setAnnotationValue(
            AnnotationNode annotation, String key, Object value) {
        for (int i = 0; i < annotation.values.size(); i += 2) {
            if (key.equals(annotation.values.get(i))) {
                annotation.values.set(i + 1, value);
                return;
            }
        }
        throw new IllegalStateException("Missing annotation value " + key);
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
