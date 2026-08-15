package dev.codex.backportfix;

import static dev.codex.backportfix.BackportPatchContract.DEFERRED_HOLDER_DESC;
import static dev.codex.backportfix.BackportPatchContract.DEFERRED_HOLDER_OWNER;
import static dev.codex.backportfix.BackportPatchContract.EXPECTED_CHANGED_ENTRIES;
import static dev.codex.backportfix.BackportPatchContract.EXPECTED_INPUT_SHA256;
import static dev.codex.backportfix.BackportPatchContract.EXPECTED_MIXIN_REPLACEMENTS;
import static dev.codex.backportfix.BackportPatchContract.SERIALIZER_DESC;
import static dev.codex.backportfix.BackportPatchContract.SERIALIZER_OWNER;
import static dev.codex.backportfix.BackportPatchContract.SERIALIZERS;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.FieldNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.analysis.Analyzer;
import org.objectweb.asm.tree.analysis.AnalyzerException;
import org.objectweb.asm.tree.analysis.BasicVerifier;

/** Static and byte-for-byte contract checks for the fixed replacement JAR. */
public final class BackportJarVerifier {
    private BackportJarVerifier() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: BackportJarVerifier <original.jar> <patched.jar>");
        }
        VerificationResult result = verify(
                Path.of(args[0]).toAbsolutePath().normalize(),
                Path.of(args[1]).toAbsolutePath().normalize());
        System.out.println("VERIFY_OK");
        System.out.println("original_sha256=" + result.originalSha256());
        System.out.println("patched_sha256=" + result.patchedSha256());
        System.out.println("changed_entries=" + String.join(",", result.changedEntries()));
        System.out.println("original_unsafe_deferred_get_sites=" + result.originalUnsafeSites());
        System.out.println("patched_unsafe_deferred_get_sites=" + result.patchedUnsafeSites());
        System.out.println("patched_eager_serializer_use_sites=" + result.eagerUseSites());
        System.out.println("preserved_cat_sound_variant_json=" + result.preservedCatSoundVariantJson());
        System.out.println("preserved_cat_sound_ogg=" + result.preservedCatSoundOgg());
    }

    public static VerificationResult verify(Path original, Path patched) throws IOException {
        require(Files.isRegularFile(original), "Original JAR missing: " + original);
        require(Files.isRegularFile(patched), "Patched JAR missing: " + patched);

        String originalSha = BackportJarPatcher.sha256(original);
        String patchedSha = BackportJarPatcher.sha256(patched);
        require(EXPECTED_INPUT_SHA256.equals(originalSha), "Original SHA-256 contract mismatch: " + originalSha);
        require(!originalSha.equals(patchedSha), "Patched JAR unexpectedly equals the original JAR");

        Map<String, byte[]> originalEntries = readEntriesAndValidateCrc(original);
        Map<String, byte[]> patchedEntries = readEntriesAndValidateCrc(patched);
        require(
                originalEntries.keySet().equals(patchedEntries.keySet()),
                "ZIP entry set changed; no entries may be added or removed");

        Set<String> changedEntries = new LinkedHashSet<>();
        for (String name : originalEntries.keySet()) {
            if (!Arrays.equals(originalEntries.get(name), patchedEntries.get(name))) {
                changedEntries.add(name);
            }
        }
        require(
                EXPECTED_CHANGED_ENTRIES.equals(changedEntries),
                "Unexpected changed entries. Expected "
                        + EXPECTED_CHANGED_ENTRIES
                        + ", got "
                        + changedEntries);

        String modsToml = new String(
                requireEntry(patchedEntries, "META-INF/neoforge.mods.toml"), StandardCharsets.UTF_8);
        require(modsToml.contains("modId = \"backport\""), "backport mod id changed or missing");
        require(countOccurrences(modsToml, "side = \"BOTH\"") >= 2, "BOTH-side metadata contract missing");
        require(
                Arrays.equals(
                        requireEntry(originalEntries, "META-INF/neoforge.mods.toml"),
                        requireEntry(patchedEntries, "META-INF/neoforge.mods.toml")),
                "Mod metadata must remain byte-for-byte unchanged");

        validateSerializerClass(requireEntry(patchedEntries, SERIALIZER_OWNER + ".class"));
        validateBytecodeStructure(requireEntry(patchedEntries, SERIALIZER_OWNER + ".class"));

        int originalUnsafeSites = 0;
        int patchedUnsafeSites = 0;
        int eagerUseSites = 0;
        for (var expected : EXPECTED_MIXIN_REPLACEMENTS.entrySet()) {
            ClassNode originalClass = readClass(requireEntry(originalEntries, expected.getKey()));
            ClassNode patchedClass = readClass(requireEntry(patchedEntries, expected.getKey()));
            validateBytecodeStructure(requireEntry(patchedEntries, expected.getKey()));
            int originalClassUnsafe = countUnsafeSerializerHolderGets(originalClass);
            int patchedClassUnsafe = countUnsafeSerializerHolderGets(patchedClass);
            int patchedClassEager = countEagerSerializerReads(patchedClass);
            require(
                    originalClassUnsafe == expected.getValue(),
                    "Original risk-site count changed for " + expected.getKey());
            require(
                    patchedClassUnsafe == 0,
                    "Unsafe DeferredHolder.get remains in " + expected.getKey());
            require(
                    patchedClassEager == expected.getValue(),
                    "Eager serializer replacement count mismatch for " + expected.getKey());
            originalUnsafeSites += originalClassUnsafe;
            patchedUnsafeSites += patchedClassUnsafe;
            eagerUseSites += patchedClassEager;
        }
        require(originalUnsafeSites == 8, "Expected eight original unsafe serializer reads");
        require(patchedUnsafeSites == 0, "Patched JAR still contains unsafe serializer reads");
        require(eagerUseSites == 8, "Expected eight eager serializer reads in patched mixins");

        int catJson = 0;
        int catOgg = 0;
        for (String name : patchedEntries.keySet()) {
            if (name.startsWith("data/minecraft/cat_sound_variant/") && name.endsWith(".json")) {
                catJson++;
            }
            if (name.startsWith("assets/minecraft/sounds/mob/cat/") && name.endsWith(".ogg")) {
                catOgg++;
            }
        }
        require(catJson == 2, "Expected classic and royal cat sound variant JSON files, got " + catJson);
        require(catOgg == 21, "Expected 21 backported cat sound files, got " + catOgg);

        return new VerificationResult(
                originalSha,
                patchedSha,
                Set.copyOf(changedEntries),
                originalUnsafeSites,
                patchedUnsafeSites,
                eagerUseSites,
                catJson,
                catOgg);
    }

    private static void validateSerializerClass(byte[] bytes) {
        ClassNode node = readClass(bytes);
        require(SERIALIZER_OWNER.equals(node.name), "Unexpected serializer class name: " + node.name);

        Set<String> fields = new HashSet<>();
        for (FieldNode field : node.fields) {
            fields.add(field.name + ":" + field.desc);
        }
        for (var entry : SERIALIZERS.entrySet()) {
            var spec = entry.getValue();
            require(
                    fields.contains(entry.getKey() + ":" + DEFERRED_HOLDER_DESC),
                    "Original DeferredHolder field missing: " + entry.getKey());
            require(
                    fields.contains(spec.eagerField() + ":" + SERIALIZER_DESC),
                    "Eager serializer field missing: " + spec.eagerField());

            MethodNode supplier = requireMethod(node, spec.supplierMethod(), "()" + SERIALIZER_DESC);
            var opcodes = opcodeInstructions(supplier);
            require(opcodes.size() == 2, "Supplier was not reduced to exact eager-field return: " + supplier.name);
            require(
                    opcodes.get(0) instanceof FieldInsnNode field
                            && field.getOpcode() == Opcodes.GETSTATIC
                            && SERIALIZER_OWNER.equals(field.owner)
                            && spec.eagerField().equals(field.name)
                            && SERIALIZER_DESC.equals(field.desc),
                    "Supplier does not return the eager serializer: " + supplier.name);
            require(opcodes.get(1).getOpcode() == Opcodes.ARETURN, "Supplier does not end with ARETURN");
        }

        MethodNode clinit = requireMethod(node, "<clinit>", "()V");
        Map<String, Integer> eagerAssignments = new HashMap<>();
        Set<String> registryNames = new HashSet<>();
        int eagerFactoryCalls = 0;
        for (AbstractInsnNode instruction : clinit.instructions) {
            if (instruction instanceof FieldInsnNode field
                    && field.getOpcode() == Opcodes.PUTSTATIC
                    && SERIALIZER_OWNER.equals(field.owner)
                    && SERIALIZER_DESC.equals(field.desc)) {
                eagerAssignments.merge(field.name, 1, Integer::sum);
            }
            if (instruction instanceof MethodInsnNode call
                    && call.getOpcode() == Opcodes.INVOKESTATIC
                    && SERIALIZER_OWNER.equals(call.owner)
                    && "holderSerializer".equals(call.name)) {
                eagerFactoryCalls++;
            }
            if (instruction instanceof LdcInsnNode ldc && ldc.cst instanceof String string) {
                registryNames.add(string);
            }
        }
        require(eagerFactoryCalls == 8, "Expected exactly eight eager serializer factory calls");
        for (var entry : SERIALIZERS.entrySet()) {
            require(
                    eagerAssignments.getOrDefault(entry.getValue().eagerField(), 0) == 1,
                    "Eager serializer must be initialized exactly once: " + entry.getValue().eagerField());
            require(
                    registryNames.contains(entry.getKey().toLowerCase(java.util.Locale.ROOT)),
                    "Original registry name missing: " + entry.getKey());
        }
    }

    private static int countUnsafeSerializerHolderGets(ClassNode node) {
        int count = 0;
        for (MethodNode method : node.methods) {
            if (!"<clinit>".equals(method.name)) {
                continue;
            }
            for (AbstractInsnNode instruction : method.instructions) {
                if (!(instruction instanceof FieldInsnNode field)
                        || field.getOpcode() != Opcodes.GETSTATIC
                        || !SERIALIZER_OWNER.equals(field.owner)
                        || !DEFERRED_HOLDER_DESC.equals(field.desc)
                        || !SERIALIZERS.containsKey(field.name)) {
                    continue;
                }
                AbstractInsnNode next = nextOpcodeInstruction(instruction);
                if (next instanceof MethodInsnNode call
                        && call.getOpcode() == Opcodes.INVOKEVIRTUAL
                        && DEFERRED_HOLDER_OWNER.equals(call.owner)
                        && "get".equals(call.name)) {
                    count++;
                }
            }
        }
        return count;
    }

    private static void validateBytecodeStructure(byte[] bytes) {
        ClassNode node = readClass(bytes);
        for (MethodNode method : node.methods) {
            if ((method.access & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_NATIVE)) != 0) {
                continue;
            }
            try {
                new Analyzer<>(new BasicVerifier()).analyze(node.name, method);
            } catch (AnalyzerException failure) {
                throw new IllegalStateException(
                        "ASM bytecode verification failed for "
                                + node.name
                                + "."
                                + method.name
                                + method.desc,
                        failure);
            }
        }
    }

    private static int countEagerSerializerReads(ClassNode node) {
        int count = 0;
        for (MethodNode method : node.methods) {
            if (!"<clinit>".equals(method.name)) {
                continue;
            }
            for (AbstractInsnNode instruction : method.instructions) {
                if (instruction instanceof FieldInsnNode field
                        && field.getOpcode() == Opcodes.GETSTATIC
                        && SERIALIZER_OWNER.equals(field.owner)
                        && SERIALIZER_DESC.equals(field.desc)
                        && SERIALIZERS.values().stream()
                                .anyMatch(spec -> spec.eagerField().equals(field.name))) {
                    count++;
                }
            }
        }
        return count;
    }

    private static AbstractInsnNode nextOpcodeInstruction(AbstractInsnNode instruction) {
        AbstractInsnNode next = instruction == null ? null : instruction.getNext();
        while (next != null && next.getOpcode() < 0) {
            next = next.getNext();
        }
        return next;
    }

    private static java.util.List<AbstractInsnNode> opcodeInstructions(MethodNode method) {
        java.util.List<AbstractInsnNode> instructions = new java.util.ArrayList<>();
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction.getOpcode() >= 0) {
                instructions.add(instruction);
            }
        }
        return instructions;
    }

    private static MethodNode requireMethod(ClassNode node, String name, String descriptor) {
        for (MethodNode method : node.methods) {
            if (name.equals(method.name) && descriptor.equals(method.desc)) {
                return method;
            }
        }
        throw new IllegalStateException("Missing method " + node.name + "." + name + descriptor);
    }

    private static ClassNode readClass(byte[] bytes) {
        ClassNode node = new ClassNode();
        new ClassReader(bytes).accept(node, 0);
        return node;
    }

    private static Map<String, byte[]> readEntriesAndValidateCrc(Path jar) throws IOException {
        Map<String, byte[]> entries = new TreeMap<>();
        try (ZipFile zip = new ZipFile(jar.toFile())) {
            Enumeration<? extends ZipEntry> enumeration = zip.entries();
            while (enumeration.hasMoreElements()) {
                ZipEntry entry = enumeration.nextElement();
                byte[] bytes = entry.isDirectory() ? new byte[0] : zip.getInputStream(entry).readAllBytes();
                require(entries.put(entry.getName(), bytes) == null, "Duplicate ZIP entry: " + entry.getName());
            }
        }
        return entries;
    }

    private static byte[] requireEntry(Map<String, byte[]> entries, String name) {
        byte[] bytes = entries.get(name);
        if (bytes == null) {
            throw new IllegalStateException("Missing JAR entry: " + name);
        }
        return bytes;
    }

    private static int countOccurrences(String haystack, String needle) {
        int count = 0;
        int cursor = 0;
        while ((cursor = haystack.indexOf(needle, cursor)) >= 0) {
            count++;
            cursor += needle.length();
        }
        return count;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    public record VerificationResult(
            String originalSha256,
            String patchedSha256,
            Set<String> changedEntries,
            int originalUnsafeSites,
            int patchedUnsafeSites,
            int eagerUseSites,
            int preservedCatSoundVariantJson,
            int preservedCatSoundOgg) {}
}
