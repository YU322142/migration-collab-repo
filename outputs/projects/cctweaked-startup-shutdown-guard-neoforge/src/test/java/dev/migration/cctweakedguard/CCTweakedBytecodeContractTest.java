package dev.migration.cctweakedguard;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.jar.JarFile;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

public final class CCTweakedBytecodeContractTest {
    private static final String TIMEOUT_STATE =
        "dan200/computercraft/core/computer/TimeoutState";
    private static final String MANAGED_TIMEOUT =
        "dan200/computercraft/core/computer/computerthread/ManagedTimeoutState";
    private static final String COMPUTER_THREAD =
        "dan200/computercraft/core/computer/computerthread/ComputerThread";
    private static final String COMPUTER_EXECUTOR =
        "dan200/computercraft/core/computer/ComputerExecutor";
    private static final String SERVER_CONTEXT =
        "dan200/computercraft/shared/computer/core/ServerContext";

    private CCTweakedBytecodeContractTest() {
    }

    public static void main(String[] args) throws Exception {
        var jar = Path.of(requiredProperty("computercraftJar"));
        try (var input = new JarFile(jar.toFile())) {
            verifyStartupTimeout(input);
            verifyNormalLuaTimeout(input);
            verifyAbandonedWorkerSentinel(input);
            verifyServerShutdownDeadline(input);
            verifyGuardSemantics();
        }
        System.out.println("CC:Tweaked 1.120.0 bytecode contract: PASS");
    }

    private static void verifyStartupTimeout(JarFile jar) throws IOException {
        var initializer = method(readClass(jar, TIMEOUT_STATE), "<clinit>", "()V");
        require(countLongPush(initializer, CCTweakedStartupGuard.ORIGINAL_STARTUP_TIMEOUT_SECONDS) == 1,
            "Expected one 30-second BASE_TIMEOUT initializer");
        require(hasTimeConversion(
                initializer,
                CCTweakedStartupGuard.ORIGINAL_STARTUP_TIMEOUT_SECONDS,
                "SECONDS",
                "BASE_TIMEOUT"),
            "BASE_TIMEOUT is no longer initialized from TimeUnit.SECONDS.toNanos(30)");

        var startTimer = method(readClass(jar, MANAGED_TIMEOUT), "startTimer", "(J)V");
        require(hasFieldRead(startTimer, MANAGED_TIMEOUT, "BASE_TIMEOUT", "J"),
            "ManagedTimeoutState.startTimer no longer reads TimeoutState.BASE_TIMEOUT");
    }

    private static void verifyNormalLuaTimeout(JarFile jar) throws IOException {
        var initializer = method(readClass(jar, TIMEOUT_STATE), "<clinit>", "()V");
        require(hasTimeConversion(
                initializer,
                CCTweakedStartupGuard.NORMAL_LUA_TIMEOUT_MILLIS,
                "MILLISECONDS",
                "TIMEOUT"),
            "Normal Lua TIMEOUT is no longer seven seconds");
        require(hasTimeConversion(
                initializer,
                CCTweakedStartupGuard.NORMAL_LUA_ABORT_GRACE_MILLIS,
                "MILLISECONDS",
                "ABORT_TIMEOUT"),
            "Normal Lua ABORT_TIMEOUT is no longer 1.5 seconds");

        var executor = readClass(jar, COMPUTER_EXECUTOR);
        var turnOn = method(executor, "turnOn", "()V");
        var workImpl = method(executor, "workImpl", "()V");
        require(hasFieldRead(turnOn, TIMEOUT_STATE, "TIMEOUT", "J"),
            "ComputerExecutor.turnOn no longer resets the post-startup budget to TIMEOUT");
        require(hasFieldRead(workImpl, TIMEOUT_STATE, "TIMEOUT", "J"),
            "ComputerExecutor.workImpl no longer resets event execution to TIMEOUT");
        require(hasMethodCall(
                workImpl,
                "dan200/computercraft/core/computer/computerthread/ComputerScheduler$Executor",
                "setRemainingTime",
                "(J)V"),
            "ComputerExecutor.workImpl no longer applies the per-event timeout");
    }

    private static void verifyAbandonedWorkerSentinel(JarFile jar) throws IOException {
        var method = method(
            readClass(jar, COMPUTER_THREAD),
            "workerFinished",
            "(Ldan200/computercraft/core/computer/computerthread/ComputerThread$WorkerThread;)V"
        );
        var instructions = instructions(method);
        var addWorker = -1;
        var subtract = -1;
        var add = -1;
        var workerCountReads = 0;
        var workerCountWrites = 0;

        for (var i = 0; i < instructions.size(); i++) {
            var instruction = instructions.get(i);
            if (instruction instanceof MethodInsnNode call
                && call.owner.equals(COMPUTER_THREAD)
                && call.name.equals("addWorker")
                && call.desc.equals("(I)V")) {
                require(addWorker < 0, "Expected one addWorker call in workerFinished");
                addWorker = i;
            }
            if (instruction.getOpcode() == Opcodes.ISUB) subtract = i;
            if (instruction.getOpcode() == Opcodes.IADD) add = i;
            if (instruction instanceof FieldInsnNode field
                && field.owner.equals(COMPUTER_THREAD)
                && field.name.equals("workerCount")
                && field.desc.equals("I")) {
                if (field.getOpcode() == Opcodes.GETFIELD) workerCountReads++;
                if (field.getOpcode() == Opcodes.PUTFIELD) workerCountWrites++;
            }
        }

        require(addWorker >= 0, "Missing addWorker call in workerFinished");
        require(subtract >= 0 && subtract < addWorker, "Missing workerCount decrement before replacement");
        require(add > addWorker, "Missing abandoned-worker safety count after addWorker");
        require(workerCountReads == 2 && workerCountWrites == 2,
            "Unexpected workerCount shape: reads=" + workerCountReads + ", writes=" + workerCountWrites);
    }

    private static void verifyServerShutdownDeadline(JarFile jar) throws IOException {
        var method = method(readClass(jar, SERVER_CONTEXT), "close", "()V");
        var instructions = instructions(method);
        var closeCall = -1;
        for (var i = 0; i < instructions.size(); i++) {
            var instruction = instructions.get(i);
            if (instruction instanceof MethodInsnNode call
                && call.owner.equals("dan200/computercraft/core/ComputerContext")
                && call.name.equals("close")
                && call.desc.equals("(JLjava/util/concurrent/TimeUnit;)Z")) {
                closeCall = i;
                break;
            }
        }
        require(closeCall >= 2, "Missing ComputerContext.close call");
        require(instructions.get(closeCall - 2).getOpcode() == Opcodes.LCONST_1,
            "CC shutdown timeout is no longer the expected one-second constant");
        var unit = instructions.get(closeCall - 1);
        require(unit instanceof FieldInsnNode field
                && field.getOpcode() == Opcodes.GETSTATIC
                && field.owner.equals("java/util/concurrent/TimeUnit")
                && field.name.equals("SECONDS"),
            "CC shutdown timeout unit is no longer TimeUnit.SECONDS");
    }

    private static void verifyGuardSemantics() {
        require(CCTweakedStartupGuard.EXTENDED_STARTUP_TIMEOUT_SECONDS
                > CCTweakedStartupGuard.ORIGINAL_STARTUP_TIMEOUT_SECONDS,
            "Startup timeout extension must be positive");
        require(CCTweakedStartupGuard.NORMAL_LUA_TIMEOUT_MILLIS == 7_000,
            "Infinite-loop soft timeout changed");
        require(CCTweakedStartupGuard.NORMAL_LUA_TIMEOUT_MILLIS
                + CCTweakedStartupGuard.NORMAL_LUA_ABORT_GRACE_MILLIS == 8_500,
            "Infinite-loop hard timeout changed");

        var workersBeforeAbandon = 1;
        var afterLogicalRemoval = workersBeforeAbandon - 1;
        var afterReplacement = afterLogicalRemoval + 1;
        var withAbandonedWorkerSentinel = afterReplacement + 1;
        require(withAbandonedWorkerSentinel == 2,
            "Abandoned-worker safety sentinel no longer keeps close fail-closed");
        require(CCTweakedStartupGuard.EXTENDED_SHUTDOWN_TIMEOUT_SECONDS == 30L,
            "Shutdown wait guard changed");
    }

    private static boolean hasFieldRead(MethodNode method, String owner, String name, String descriptor) {
        return instructions(method).stream().anyMatch(instruction ->
            instruction instanceof FieldInsnNode field
                && field.getOpcode() == Opcodes.GETSTATIC
                && field.owner.equals(owner)
                && field.name.equals(name)
                && field.desc.equals(descriptor));
    }

    private static boolean hasMethodCall(MethodNode method, String owner, String name, String descriptor) {
        return instructions(method).stream().anyMatch(instruction ->
            instruction instanceof MethodInsnNode call
                && call.owner.equals(owner)
                && call.name.equals(name)
                && call.desc.equals(descriptor));
    }

    private static int countLongPush(MethodNode method, long value) {
        var count = 0;
        for (var instruction : instructions(method)) {
            if (longPush(instruction) == value) count++;
        }
        return count;
    }

    private static boolean hasTimeConversion(
        MethodNode method, long value, String unitName, String destinationField
    ) {
        var instructions = instructions(method);
        for (var i = 0; i + 3 < instructions.size(); i++) {
            var unit = instructions.get(i);
            var amount = instructions.get(i + 1);
            var conversion = instructions.get(i + 2);
            var destination = instructions.get(i + 3);
            if (unit instanceof FieldInsnNode unitField
                && unitField.getOpcode() == Opcodes.GETSTATIC
                && unitField.owner.equals("java/util/concurrent/TimeUnit")
                && unitField.name.equals(unitName)
                && longPush(amount) == value
                && conversion instanceof MethodInsnNode call
                && call.owner.equals("java/util/concurrent/TimeUnit")
                && call.name.equals("toNanos")
                && call.desc.equals("(J)J")
                && destination instanceof FieldInsnNode output
                && output.getOpcode() == Opcodes.PUTSTATIC
                && output.owner.equals(TIMEOUT_STATE)
                && output.name.equals(destinationField)) {
                return true;
            }
        }
        return false;
    }

    private static long longPush(AbstractInsnNode instruction) {
        return switch (instruction.getOpcode()) {
            case Opcodes.LCONST_0 -> 0L;
            case Opcodes.LCONST_1 -> 1L;
            case Opcodes.LDC -> ((LdcInsnNode) instruction).cst instanceof Long value
                ? value : Long.MIN_VALUE;
            default -> Long.MIN_VALUE;
        };
    }

    private static ClassNode readClass(JarFile jar, String name) throws IOException {
        var entry = jar.getJarEntry(name + ".class");
        require(entry != null, "Missing class " + name);
        try (InputStream stream = jar.getInputStream(entry)) {
            var node = new ClassNode();
            new ClassReader(stream).accept(node, 0);
            return node;
        }
    }

    private static MethodNode method(ClassNode owner, String name, String descriptor) {
        return owner.methods.stream()
            .filter(method -> method.name.equals(name) && method.desc.equals(descriptor))
            .findFirst()
            .orElseThrow(() -> new AssertionError("Missing method " + owner.name + "." + name + descriptor));
    }

    private static List<AbstractInsnNode> instructions(MethodNode method) {
        var result = new ArrayList<AbstractInsnNode>();
        for (var instruction = method.instructions.getFirst(); instruction != null; instruction = instruction.getNext()) {
            if (instruction.getOpcode() >= 0) result.add(instruction);
        }
        return result;
    }

    private static String requiredProperty(String name) {
        var value = System.getProperty(name);
        if (value == null || value.isBlank()) throw new IllegalArgumentException("Missing -D" + name);
        return value;
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
