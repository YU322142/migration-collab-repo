package com.crabmod.hotbath.audit;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.JumpInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

class HotBathTriggerRegistrationContractTest {
    private static final String EXTRA_EVENTS =
            "com/crabmod/hotbath/registers/ExtraEventsRegister.class";
    private static final List<String> TRIGGER_IDS =
            List.of(
                    "hotbath:foot_health",
                    "hotbath:milk_skin",
                    "hotbath:chronic_invalid",
                    "hotbath:rose_body_fragrance");

    @Test
    void advancementRegistrationIsGuardedAndPreservesAllFourIds() throws Exception {
        ClassNode type = readClass(builtJar(), EXTRA_EVENTS);
        MethodNode method =
                type.methods.stream()
                        .filter(candidate -> candidate.name.equals("registerAdvancementTrigger"))
                        .filter(
                                candidate ->
                                        candidate.desc.equals(
                                                "(Lnet/neoforged/neoforge/registries/RegisterEvent;)V"))
                        .findFirst()
                        .orElseThrow();

        assertTrue(
                hasAnnotation(
                        method.visibleAnnotations, "Lnet/neoforged/bus/api/SubscribeEvent;"));
        assertTrue(
                hasAnnotation(
                        type.visibleAnnotations,
                        "Lnet/neoforged/fml/common/EventBusSubscriber;"));

        List<AbstractInsnNode> instructions = meaningfulInstructions(method);
        int getRegistryKey =
                findMethodCall(
                        instructions,
                        "net/neoforged/neoforge/registries/RegisterEvent",
                        "getRegistryKey");
        int triggerType =
                findFieldRead(
                        instructions,
                        "net/minecraft/core/registries/Registries",
                        "TRIGGER_TYPE");
        int equalsCall = findMethodCallByName(instructions, "equals", "(Ljava/lang/Object;)Z");
        int firstRegister =
                findMethodCall(
                        instructions,
                        "net/minecraft/advancements/CriteriaTriggers",
                        "register");

        assertTrue(getRegistryKey >= 0, "RegisterEvent.getRegistryKey guard is missing");
        assertTrue(
                triggerType > getRegistryKey,
                "TRIGGER_TYPE must be compared after reading the event registry key");
        assertTrue(equalsCall > triggerType, "registry key comparison is missing");
        assertTrue(firstRegister > equalsCall, "guard must execute before any registration");

        AbstractInsnNode branch = instructions.get(equalsCall + 1);
        assertTrue(branch instanceof JumpInsnNode, "comparison must branch around the return");
        assertEquals(
                Opcodes.IFNE,
                branch.getOpcode(),
                "matching TRIGGER_TYPE must enter the registration body");
        assertEquals(
                Opcodes.RETURN,
                instructions.get(equalsCall + 2).getOpcode(),
                "all unrelated registry events must return without registering");
        AbstractInsnNode branchTarget = nextMeaningful(((JumpInsnNode) branch).label);
        assertTrue(branchTarget instanceof LdcInsnNode, "guard target must enter the first trigger block");
        assertEquals(
                TRIGGER_IDS.getFirst(),
                ((LdcInsnNode) branchTarget).cst,
                "guard must dominate all four registrations from the first ID onward");

        List<String> namespacedIds = new ArrayList<>();
        int registerCalls = 0;
        int triggerConstructors = 0;
        for (AbstractInsnNode instruction : instructions) {
            if (instruction instanceof LdcInsnNode ldc
                    && ldc.cst instanceof String value
                    && value.startsWith("hotbath:")) {
                namespacedIds.add(value);
            }
            if (instruction instanceof MethodInsnNode call
                    && call.owner.equals("net/minecraft/advancements/CriteriaTriggers")
                    && call.name.equals("register")) {
                registerCalls++;
            }
            if (instruction instanceof MethodInsnNode call
                    && call.owner.equals("com/crabmod/hotbath/advancements/AdvancementTrigger")
                    && call.name.equals("<init>")) {
                triggerConstructors++;
            }
            if (instruction instanceof MethodInsnNode call) {
                assertFalse(
                        call.owner.startsWith("net/minecraft/client/")
                                || call.owner.startsWith("net/neoforged/neoforge/client/"),
                        "common trigger registration path must not invoke client-only code");
            }
        }

        assertEquals(TRIGGER_IDS, namespacedIds);
        assertEquals(4, registerCalls);
        assertEquals(4, triggerConstructors);
    }

    @Test
    void oneCompleteRegistryPassRegistersEachTriggerExactlyOnce() throws Exception {
        ClassNode type = readClass(builtJar(), EXTRA_EVENTS);
        MethodNode method =
                type.methods.stream()
                        .filter(candidate -> candidate.name.equals("registerAdvancementTrigger"))
                        .findFirst()
                        .orElseThrow();
        List<AbstractInsnNode> instructions = meaningfulInstructions(method);

        assertTrue(
                findMethodCall(
                                instructions,
                                "net/neoforged/neoforge/registries/RegisterEvent",
                                "getRegistryKey")
                        >= 0);
        assertTrue(
                findFieldRead(
                                instructions,
                                "net/minecraft/core/registries/Registries",
                                "TRIGGER_TYPE")
                        >= 0);

        List<String> emittedIds = new ArrayList<>();
        for (AbstractInsnNode instruction : instructions) {
            if (instruction instanceof LdcInsnNode ldc
                    && ldc.cst instanceof String value
                    && value.startsWith("hotbath:")) {
                emittedIds.add(value);
            }
        }

        Map<String, Integer> registrations = new LinkedHashMap<>();
        List<String> registryEvents =
                List.of("block", "item", "fluid", "particle_type", "trigger_type", "sound_event");
        for (String registryEvent : registryEvents) {
            if (!registryEvent.equals("trigger_type")) {
                continue;
            }
            for (String id : emittedIds) {
                registrations.merge(id, 1, Integer::sum);
            }
        }

        assertEquals(new TreeSet<>(TRIGGER_IDS), new TreeSet<>(registrations.keySet()));
        assertTrue(registrations.values().stream().allMatch(count -> count == 1));
    }

    @Test
    void advancementJsonStillTargetsTheSameFourTriggerIds() throws Exception {
        try (ZipFile built = new ZipFile(builtJar().toFile())) {
            for (String id : TRIGGER_IDS) {
                String path = id.substring(id.indexOf(':') + 1);
                ZipEntry entry = built.getEntry("data/hotbath/advancement/" + path + ".json");
                assertNotNull(entry, path);
                String json = new String(read(built, entry), StandardCharsets.UTF_8);
                assertTrue(json.contains("\"id\": \"" + id + "\""), path + " advancement id changed");
                assertTrue(
                        json.contains("\"trigger\": \"" + id + "\""),
                        path + " criterion trigger changed");
            }
        }
    }

    @Test
    void jarKeepsGameplayResourcesAndAllClassNames() throws Exception {
        try (ZipFile original = new ZipFile(originalJar().toFile());
                ZipFile built = new ZipFile(builtJar().toFile())) {
            Map<String, ZipEntry> originalFiles = filesByName(original);
            Map<String, ZipEntry> builtFiles = filesByName(built);
            assertEquals(originalFiles.keySet(), builtFiles.keySet(), "JAR file entry set changed");

            Set<String> originalClasses = entriesEndingWith(originalFiles.keySet(), ".class");
            Set<String> builtClasses = entriesEndingWith(builtFiles.keySet(), ".class");
            assertEquals(originalClasses, builtClasses, "class entry set changed");

            for (String name : originalFiles.keySet()) {
                if (name.endsWith(".class")
                        || name.equals("META-INF/MANIFEST.MF")
                        || name.equals("META-INF/neoforge.mods.toml")) {
                    continue;
                }
                assertTrue(builtFiles.containsKey(name), "missing original resource: " + name);
                assertArrayEquals(
                        read(original, originalFiles.get(name)),
                        read(built, builtFiles.get(name)),
                        name);
            }

            for (String className : originalClasses) {
                byte[] originalClass = read(original, originalFiles.get(className));
                byte[] builtClass = read(built, builtFiles.get(className));
                if (className.equals(EXTRA_EVENTS)) {
                    assertFalse(
                            Arrays.equals(originalClass, builtClass),
                            "patched class must differ from the broken release");
                    continue;
                }
                assertArrayEquals(
                        originalClass,
                        builtClass,
                        "unexpected bytecode change: " + className);
            }

            String modsToml =
                    new String(
                            read(built, builtFiles.get("META-INF/neoforge.mods.toml")),
                            StandardCharsets.UTF_8);
            String manifest =
                    new String(
                            read(built, builtFiles.get("META-INF/MANIFEST.MF")),
                            StandardCharsets.UTF_8);
            assertTrue(modsToml.contains("modId=\"hotbath\""));
            assertTrue(modsToml.contains("version=\"1.21.1-3.0.0-registry-fix.1\""));
            assertTrue(
                    manifest.contains(
                            "Implementation-Version: 1.21.1-3.0.0-registry-fix.1"));
            assertFalse(
                    java.util.regex.Pattern.compile(
                                    "(?m)^\\s*clientSideOnly\\s*=\\s*true\\s*(?:#.*)?$")
                            .matcher(modsToml)
                            .find(),
                    "Hot Bath must remain a BOTH-side mod");
        }
    }

    @Test
    void everyZipEntryCanBeReadAndHasNoDuplicateName() throws Exception {
        try (ZipFile jar = new ZipFile(builtJar().toFile())) {
            Set<String> names = new HashSet<>();
            Enumeration<? extends ZipEntry> entries = jar.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                assertTrue(names.add(entry.getName()), "duplicate ZIP entry: " + entry.getName());
                if (!entry.isDirectory()) {
                    try (InputStream input = jar.getInputStream(entry)) {
                        input.transferTo(java.io.OutputStream.nullOutputStream());
                    }
                }
            }
        }
    }

    private static Path originalJar() {
        return Path.of(System.getProperty("hotbath.originalJar"));
    }

    private static Path builtJar() {
        return Path.of(System.getProperty("hotbath.builtJar"));
    }

    private static ClassNode readClass(Path jar, String entryName) throws IOException {
        try (ZipFile zip = new ZipFile(jar.toFile())) {
            ZipEntry entry = zip.getEntry(entryName);
            assertNotNull(entry, entryName);
            ClassNode node = new ClassNode();
            new ClassReader(read(zip, entry)).accept(node, 0);
            return node;
        }
    }

    private static Map<String, ZipEntry> filesByName(ZipFile zip) {
        Map<String, ZipEntry> result = new HashMap<>();
        Enumeration<? extends ZipEntry> entries = zip.entries();
        while (entries.hasMoreElements()) {
            ZipEntry entry = entries.nextElement();
            if (!entry.isDirectory()) {
                assertNull(result.put(entry.getName(), entry), "duplicate ZIP entry: " + entry.getName());
            }
        }
        return result;
    }

    private static Set<String> entriesEndingWith(Set<String> entries, String suffix) {
        Set<String> result = new TreeSet<>();
        for (String entry : entries) {
            if (entry.endsWith(suffix)) {
                result.add(entry);
            }
        }
        return result;
    }

    private static byte[] read(ZipFile zip, ZipEntry entry) throws IOException {
        assertNotNull(entry);
        try (InputStream input = zip.getInputStream(entry)) {
            return input.readAllBytes();
        }
    }

    private static List<AbstractInsnNode> meaningfulInstructions(MethodNode method) {
        List<AbstractInsnNode> result = new ArrayList<>();
        for (AbstractInsnNode instruction : method.instructions) {
            if (instruction.getOpcode() >= 0) {
                result.add(instruction);
            }
        }
        return result;
    }

    private static AbstractInsnNode nextMeaningful(AbstractInsnNode start) {
        for (AbstractInsnNode instruction = start;
                instruction != null;
                instruction = instruction.getNext()) {
            if (instruction.getOpcode() >= 0) {
                return instruction;
            }
        }
        throw new AssertionError("branch target has no executable instruction");
    }

    private static int findMethodCall(
            List<AbstractInsnNode> instructions, String owner, String name) {
        for (int index = 0; index < instructions.size(); index++) {
            if (instructions.get(index) instanceof MethodInsnNode call
                    && call.owner.equals(owner)
                    && call.name.equals(name)) {
                return index;
            }
        }
        return -1;
    }

    private static int findMethodCallByName(
            List<AbstractInsnNode> instructions, String name, String descriptor) {
        for (int index = 0; index < instructions.size(); index++) {
            if (instructions.get(index) instanceof MethodInsnNode call
                    && call.name.equals(name)
                    && call.desc.equals(descriptor)) {
                return index;
            }
        }
        return -1;
    }

    private static int findFieldRead(
            List<AbstractInsnNode> instructions, String owner, String name) {
        for (int index = 0; index < instructions.size(); index++) {
            if (instructions.get(index) instanceof FieldInsnNode field
                    && field.getOpcode() == Opcodes.GETSTATIC
                    && field.owner.equals(owner)
                    && field.name.equals(name)) {
                return index;
            }
        }
        return -1;
    }

    private static boolean hasAnnotation(
            List<AnnotationNode> annotations, String descriptor) {
        return annotations != null
                && annotations.stream()
                        .anyMatch(annotation -> annotation.desc.equals(descriptor));
    }
}
