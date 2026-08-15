import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodNode;

public final class PatchBarchedAnnotation {
    private static final String CLASS_ENTRY =
            "zzik2/barched/mixin/entity/EntityTypeMixin.class";
    private static final String METHOD_NAME = "barched$modifyMobCategory";
    private static final String MODIFY_ARG_DESC =
            "Lorg/spongepowered/asm/mixin/injection/ModifyArg;";

    private PatchBarchedAnnotation() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: PatchBarchedAnnotation <original-jar> <patched-dev-class> <output-class>");
        }

        byte[] original = readJarEntry(Path.of(args[0]), CLASS_ENTRY);
        byte[] patched = Files.readAllBytes(Path.of(args[1]));

        ClassNode originalNode = readClass(original);
        ClassNode patchedNode = readClass(patched);
        MethodNode originalMethod = findMethod(originalNode);
        MethodNode patchedMethod = findMethod(patchedNode);
        AnnotationNode patchedAnnotation = findAnnotation(patchedMethod.visibleAnnotations);

        if (!containsValue(patchedAnnotation, "stringValue=zombified_piglin")) {
            throw new IllegalStateException("Patched annotation has no bounded slice end");
        }

        AnnotationNode annotationCopy = new AnnotationNode(patchedAnnotation.desc);
        patchedAnnotation.accept(annotationCopy);
        replaceAnnotation(originalMethod.visibleAnnotations, annotationCopy);

        ClassWriter writer = new ClassWriter(0);
        originalNode.accept(writer);
        byte[] output = writer.toByteArray();

        requireAscii(output, "zzik2/barched/minecraft/world/entity/monster/Parched");
        requireAscii(output, "zzik2/barched/minecraft/world/entity/animal/CamelHusk");
        requireAscii(output, "stringValue=zombified_piglin");

        Path outputPath = Path.of(args[2]);
        Files.createDirectories(outputPath.getParent());
        Files.write(outputPath, output);
        System.out.println("patched_class_bytes=" + output.length);
    }

    private static byte[] readJarEntry(Path jar, String entryName) throws IOException {
        try (ZipFile zip = new ZipFile(jar.toFile())) {
            ZipEntry entry = zip.getEntry(entryName);
            if (entry == null) {
                throw new IOException("Missing JAR entry: " + entryName);
            }
            return zip.getInputStream(entry).readAllBytes();
        }
    }

    private static ClassNode readClass(byte[] bytes) {
        ClassNode node = new ClassNode();
        new ClassReader(bytes).accept(node, 0);
        return node;
    }

    private static MethodNode findMethod(ClassNode node) {
        return node.methods.stream()
                .filter(method -> method.name.equals(METHOD_NAME))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("Missing method: " + METHOD_NAME));
    }

    private static AnnotationNode findAnnotation(List<AnnotationNode> annotations) {
        if (annotations == null) {
            throw new IllegalStateException("Method has no visible annotations");
        }
        return annotations.stream()
                .filter(annotation -> annotation.desc.equals(MODIFY_ARG_DESC))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("Missing @ModifyArg annotation"));
    }

    private static void replaceAnnotation(List<AnnotationNode> annotations, AnnotationNode replacement) {
        for (int i = 0; i < annotations.size(); i++) {
            if (annotations.get(i).desc.equals(MODIFY_ARG_DESC)) {
                annotations.set(i, replacement);
                return;
            }
        }
        throw new IllegalStateException("Original @ModifyArg annotation disappeared");
    }

    private static boolean containsValue(Object value, String needle) {
        if (value instanceof String string) {
            return string.equals(needle);
        }
        if (value instanceof AnnotationNode annotation) {
            return containsValue(annotation.values, needle);
        }
        if (value instanceof List<?> list) {
            return list.stream().anyMatch(item -> containsValue(item, needle));
        }
        return false;
    }

    private static void requireAscii(byte[] bytes, String value) {
        String binaryText = new String(bytes, StandardCharsets.ISO_8859_1);
        if (!binaryText.contains(value)) {
            throw new IllegalStateException("Output class lost required reference: " + value);
        }
    }
}
