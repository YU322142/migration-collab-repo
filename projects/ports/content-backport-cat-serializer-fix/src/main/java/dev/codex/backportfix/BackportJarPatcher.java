package dev.codex.backportfix;

import static dev.codex.backportfix.BackportPatchContract.DEFERRED_HOLDER_DESC;
import static dev.codex.backportfix.BackportPatchContract.DEFERRED_HOLDER_OWNER;
import static dev.codex.backportfix.BackportPatchContract.EXPECTED_INPUT_SHA256;
import static dev.codex.backportfix.BackportPatchContract.EXPECTED_MIXIN_REPLACEMENTS;
import static dev.codex.backportfix.BackportPatchContract.KEYS_OWNER;
import static dev.codex.backportfix.BackportPatchContract.RESOURCE_KEY_DESC;
import static dev.codex.backportfix.BackportPatchContract.SERIALIZER_DESC;
import static dev.codex.backportfix.BackportPatchContract.SERIALIZER_OWNER;
import static dev.codex.backportfix.BackportPatchContract.SERIALIZERS;

import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.zip.CRC32;
import java.util.zip.Deflater;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.FieldNode;
import org.objectweb.asm.tree.InsnList;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

/** Deterministically applies the registry-lifecycle fix to the exact audited Content Backport JAR. */
public final class BackportJarPatcher {
    private static final long FIXED_ZIP_TIME_MILLIS = 315_532_800_000L; // 1980-01-01T00:00:00Z

    private BackportJarPatcher() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: BackportJarPatcher <backport-1.5.jar> <output.jar>");
        }
        Path input = Path.of(args[0]).toAbsolutePath().normalize();
        Path output = Path.of(args[1]).toAbsolutePath().normalize();
        PatchResult result = patch(input, output);
        System.out.println("PATCH_OK");
        System.out.println("input_sha256=" + result.inputSha256());
        System.out.println("output_sha256=" + result.outputSha256());
        System.out.println("patched_classes=" + String.join(",", result.patchedClasses()));
        System.out.println("replaced_unbound_get_sites=" + result.replacedUnboundGetSites());
    }

    public static PatchResult patch(Path input, Path output) throws IOException {
        requireExactInput(input);
        if (input.equals(output)) {
            throw new IllegalArgumentException("Refusing to overwrite the audited input JAR");
        }

        Map<String, EntryData> entries = readEntries(input);
        Map<String, byte[]> replacements = new LinkedHashMap<>();

        String serializerEntry = SERIALIZER_OWNER + ".class";
        byte[] serializerClass = requireEntry(entries, serializerEntry).bytes();
        replacements.put(serializerEntry, patchSerializerRegistryClass(serializerClass));

        int replacedSites = 0;
        for (var expected : EXPECTED_MIXIN_REPLACEMENTS.entrySet()) {
            byte[] originalClass = requireEntry(entries, expected.getKey()).bytes();
            UseSitePatch patched = patchDeferredHolderUseSites(originalClass);
            if (patched.replacements() != expected.getValue()) {
                throw new IllegalStateException(
                        "Unexpected use-site count for "
                                + expected.getKey()
                                + ": expected "
                                + expected.getValue()
                                + ", got "
                                + patched.replacements());
            }
            replacements.put(expected.getKey(), patched.bytes());
            replacedSites += patched.replacements();
        }
        if (replacedSites != SERIALIZERS.size()) {
            throw new IllegalStateException(
                    "Expected " + SERIALIZERS.size() + " total unsafe reads, got " + replacedSites);
        }

        Files.createDirectories(output.getParent());
        Path temporary = Files.createTempFile(output.getParent(), output.getFileName().toString(), ".tmp");
        boolean moved = false;
        try {
            writeDeterministicJar(temporary, entries, replacements);
            try {
                Files.move(
                        temporary,
                        output,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(temporary, output, StandardCopyOption.REPLACE_EXISTING);
            }
            moved = true;
        } finally {
            if (!moved) {
                Files.deleteIfExists(temporary);
            }
        }

        return new PatchResult(
                sha256(input),
                sha256(output),
                List.copyOf(replacements.keySet()),
                replacedSites);
    }

    private static byte[] patchSerializerRegistryClass(byte[] original) {
        ClassNode node = readClass(original);
        if (!SERIALIZER_OWNER.equals(node.name)) {
            throw new IllegalStateException("Unexpected serializer class name: " + node.name);
        }

        Set<String> existingFields = new java.util.HashSet<>();
        for (FieldNode field : node.fields) {
            existingFields.add(field.name);
        }
        for (var spec : SERIALIZERS.values()) {
            if (!existingFields.add(spec.eagerField())) {
                throw new IllegalStateException("Eager serializer field already exists: " + spec.eagerField());
            }
            node.fields.add(new FieldNode(
                    Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC | Opcodes.ACC_FINAL,
                    spec.eagerField(),
                    SERIALIZER_DESC,
                    null,
                    null));
        }

        MethodNode clinit = requireMethod(node, "<clinit>", "()V");
        AbstractInsnNode serializersAssignment = null;
        for (AbstractInsnNode instruction : clinit.instructions) {
            if (instruction instanceof FieldInsnNode field
                    && instruction.getOpcode() == Opcodes.PUTSTATIC
                    && SERIALIZER_OWNER.equals(field.owner)
                    && "SERIALIZERS".equals(field.name)) {
                serializersAssignment = instruction;
                break;
            }
        }
        if (serializersAssignment == null) {
            throw new IllegalStateException("Could not find SERIALIZERS initialization anchor");
        }

        InsnList eagerInitializers = new InsnList();
        for (var entry : SERIALIZERS.entrySet()) {
            eagerInitializers.add(new FieldInsnNode(
                    Opcodes.GETSTATIC, KEYS_OWNER, entry.getKey(), RESOURCE_KEY_DESC));
            eagerInitializers.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC,
                    SERIALIZER_OWNER,
                    "holderSerializer",
                    "(" + RESOURCE_KEY_DESC + ")" + SERIALIZER_DESC,
                    false));
            eagerInitializers.add(new FieldInsnNode(
                    Opcodes.PUTSTATIC,
                    SERIALIZER_OWNER,
                    entry.getValue().eagerField(),
                    SERIALIZER_DESC));
        }
        clinit.instructions.insert(serializersAssignment, eagerInitializers);

        for (var spec : SERIALIZERS.values()) {
            MethodNode supplier = requireMethod(node, spec.supplierMethod(), "()" + SERIALIZER_DESC);
            supplier.instructions.clear();
            supplier.instructions.add(new FieldInsnNode(
                    Opcodes.GETSTATIC, SERIALIZER_OWNER, spec.eagerField(), SERIALIZER_DESC));
            supplier.instructions.add(new InsnNode(Opcodes.ARETURN));
            supplier.tryCatchBlocks.clear();
            supplier.localVariables = null;
            supplier.maxStack = 1;
            supplier.maxLocals = 0;
        }
        return writeClass(node);
    }

    private static UseSitePatch patchDeferredHolderUseSites(byte[] original) {
        ClassNode node = readClass(original);
        int replacements = 0;
        for (MethodNode method : node.methods) {
            if (!"<clinit>".equals(method.name)) {
                continue;
            }
            for (AbstractInsnNode instruction = method.instructions.getFirst();
                    instruction != null;
                    instruction = instruction.getNext()) {
                if (!(instruction instanceof FieldInsnNode field)
                        || instruction.getOpcode() != Opcodes.GETSTATIC
                        || !SERIALIZER_OWNER.equals(field.owner)
                        || !DEFERRED_HOLDER_DESC.equals(field.desc)) {
                    continue;
                }
                var spec = SERIALIZERS.get(field.name);
                if (spec == null) {
                    continue;
                }

                AbstractInsnNode getCall = nextOpcodeInstruction(instruction);
                AbstractInsnNode cast = nextOpcodeInstruction(getCall);
                if (!(getCall instanceof MethodInsnNode call)
                        || call.getOpcode() != Opcodes.INVOKEVIRTUAL
                        || !DEFERRED_HOLDER_OWNER.equals(call.owner)
                        || !"get".equals(call.name)
                        || !"()Ljava/lang/Object;".equals(call.desc)
                        || cast == null
                        || cast.getOpcode() != Opcodes.CHECKCAST) {
                    throw new IllegalStateException(
                            "Unexpected DeferredHolder access shape in " + node.name + ".<clinit>");
                }

                field.name = spec.eagerField();
                field.desc = SERIALIZER_DESC;
                method.instructions.remove(getCall);
                method.instructions.remove(cast);
                replacements++;
            }
        }
        if (replacements == 0) {
            throw new IllegalStateException("No unsafe DeferredHolder reads found in " + node.name);
        }
        return new UseSitePatch(writeClass(node), replacements);
    }

    private static AbstractInsnNode nextOpcodeInstruction(AbstractInsnNode instruction) {
        if (instruction == null) {
            return null;
        }
        AbstractInsnNode next = instruction.getNext();
        while (next != null && next.getOpcode() < 0) {
            next = next.getNext();
        }
        return next;
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

    private static byte[] writeClass(ClassNode node) {
        ClassWriter writer = new ClassWriter(0);
        node.accept(writer);
        return writer.toByteArray();
    }

    private static void requireExactInput(Path input) throws IOException {
        if (!Files.isRegularFile(input)) {
            throw new IOException("Input JAR does not exist: " + input);
        }
        String actual = sha256(input);
        if (!EXPECTED_INPUT_SHA256.equals(actual)) {
            throw new IllegalArgumentException(
                    "Refusing unaudited input JAR. Expected SHA-256 "
                            + EXPECTED_INPUT_SHA256
                            + ", got "
                            + actual);
        }
    }

    static String sha256(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (var input = Files.newInputStream(path)) {
                byte[] buffer = new byte[1024 * 1024];
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    digest.update(buffer, 0, read);
                }
            }
            return java.util.HexFormat.of().formatHex(digest.digest()).toLowerCase(Locale.ROOT);
        } catch (NoSuchAlgorithmException impossible) {
            throw new AssertionError(impossible);
        }
    }

    private static Map<String, EntryData> readEntries(Path input) throws IOException {
        Map<String, EntryData> entries = new TreeMap<>();
        try (ZipFile zip = new ZipFile(input.toFile())) {
            Enumeration<? extends ZipEntry> enumeration = zip.entries();
            while (enumeration.hasMoreElements()) {
                ZipEntry entry = enumeration.nextElement();
                byte[] bytes = entry.isDirectory() ? new byte[0] : zip.getInputStream(entry).readAllBytes();
                EntryData previous = entries.put(entry.getName(), new EntryData(entry.isDirectory(), bytes));
                if (previous != null) {
                    throw new IllegalStateException("Duplicate ZIP entry: " + entry.getName());
                }
            }
        }
        return entries;
    }

    private static EntryData requireEntry(Map<String, EntryData> entries, String name) {
        EntryData entry = entries.get(name);
        if (entry == null || entry.directory()) {
            throw new IllegalStateException("Missing class entry: " + name);
        }
        return entry;
    }

    private static void writeDeterministicJar(
            Path output, Map<String, EntryData> entries, Map<String, byte[]> replacements) throws IOException {
        List<String> names = new ArrayList<>(entries.keySet());
        Collections.sort(names);
        String manifest = "META-INF/MANIFEST.MF";
        if (names.remove(manifest)) {
            names.add(0, manifest);
        }

        try (OutputStream file = Files.newOutputStream(output);
                ZipOutputStream zip = new ZipOutputStream(new BufferedOutputStream(file))) {
            zip.setLevel(Deflater.BEST_COMPRESSION);
            for (String name : names) {
                EntryData original = entries.get(name);
                byte[] bytes = replacements.getOrDefault(name, original.bytes());
                ZipEntry entry = new ZipEntry(name);
                entry.setTime(FIXED_ZIP_TIME_MILLIS);
                entry.setComment(null);
                entry.setExtra(null);
                if (original.directory()) {
                    CRC32 crc = new CRC32();
                    entry.setMethod(ZipEntry.STORED);
                    entry.setSize(0);
                    entry.setCompressedSize(0);
                    entry.setCrc(crc.getValue());
                } else {
                    entry.setMethod(ZipEntry.DEFLATED);
                }
                zip.putNextEntry(entry);
                if (!original.directory()) {
                    zip.write(bytes);
                }
                zip.closeEntry();
            }
        }
    }

    record PatchResult(
            String inputSha256,
            String outputSha256,
            List<String> patchedClasses,
            int replacedUnboundGetSites) {}

    private record UseSitePatch(byte[] bytes, int replacements) {}

    private record EntryData(boolean directory, byte[] bytes) {
        EntryData {
            bytes = Arrays.copyOf(bytes, bytes.length);
        }

        @Override
        public byte[] bytes() {
            return Arrays.copyOf(bytes, bytes.length);
        }
    }
}
