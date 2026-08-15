package io.github.mcmodsync;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.File;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.TimeUnit;

public final class PostBuildPortableSmoke {
    private PostBuildPortableSmoke() {
    }

    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 2) {
            throw new IllegalArgumentException("Expected built JAR and test classes arguments");
        }
        Path jar = Path.of(arguments[0]).toAbsolutePath().normalize();
        Path testClasses = Path.of(arguments[1]).toAbsolutePath().normalize();
        Path temporaryRoot = Files.createTempDirectory("modsync-post-build-portable-");
        // Spaces, Chinese text and parentheses match the failing Prism
        // instance path and exercise Unicode command-line handling.
        Path root = temporaryRoot.resolve("Motiquies - 动静交映 - Tiny (1)");
        Files.createDirectories(root);
        HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        try {
            byte[] wanted = new byte[2 * 1024 * 1024 + 321];
            for (int index = 0; index < wanted.length; index++) {
                wanted[index] = (byte) (index * 31 + 7);
            }
            byte[] updater = Files.readAllBytes(jar);
            String manifest = ModManifest.MAGIC + "\n"
                    + Hashing.md5(updater) + "\tmcmodsync\tMCModSync-" + BuildInfo.VERSION + ".jar\n"
                    + Hashing.md5(wanted) + "\t-\twanted-progress.jar\n";
            server.createContext("/base/mods.txt", exchange -> respond(
                    exchange, manifest.getBytes(StandardCharsets.UTF_8)));
            server.createContext("/base/MCModSync-" + BuildInfo.VERSION + ".jar",
                    exchange -> respond(exchange, updater));
            server.createContext("/base/wanted-progress.jar", exchange -> respond(exchange, wanted));
            server.start();

            Path mods = Files.createDirectories(root.resolve("mods"));
            Path oldUpdater = mods.resolve("MCModSync-1.6.2.jar");
            Files.copy(jar, oldUpdater);
            String manifestUri = "http://127.0.0.1:" + server.getAddress().getPort() + "/base/mods.txt";
            Path java = Path.of(
                    System.getProperty("java.home"),
                    "bin",
                    System.getProperty("os.name", "").toLowerCase().contains("windows") ? "java.exe" : "java");
            verifyExecutableJarPathWithSemicolon(java, jar, temporaryRoot);
            // Run from the JAR that is itself inside mods. The helper must copy
            // itself elsewhere before the parent exits or Windows will prevent
            // replacing this file.
            String classPath = oldUpdater + File.pathSeparator + testClasses;
            Process child = new ProcessBuilder(
                    java.toString(),
                    "-Dfile.encoding=UTF-8",
                    "-Dsun.stdout.encoding=UTF-8",
                    "-Dsun.stderr.encoding=UTF-8",
                    "-Dmodsync.disableDialogs=true",
                    "-Dmodsync.syncResourcePacks=false",
                    "-Dmodsync.syncServerList=false",
                    "-Dmodsync.manifest=" + manifestUri,
                    "-Dmodsync.requireManifest=true",
                    "-cp",
                    classPath,
                    PortableActualChildMain.class.getName(),
                    root.toString())
                    .redirectErrorStream(true)
                    .start();

            boolean exited = child.waitFor(20, TimeUnit.SECONDS);
            if (!exited) {
                child.destroyForcibly();
                throw new AssertionError("Portable preLaunch child did not exit normally");
            }
            String childOutput = new String(child.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            if (child.exitValue() != 0) {
                throw new AssertionError("Portable preLaunch child exit=" + child.exitValue() + "\n" + childOutput);
            }
            if (!childOutput.contains("[MCModSync] RESTART_REQUIRED")) {
                throw new AssertionError("Portable preLaunch did not take the graceful-exit path\n" + childOutput);
            }
            if (!childOutput.contains("更新辅助进程已确认可用")
                    && !childOutput.contains("Update helper confirmed ready")) {
                throw new AssertionError("Parent exited without a helper readiness handshake\n" + childOutput);
            }

            Path installed = root.resolve("mods/wanted-progress.jar");
            waitFor(() -> Files.isRegularFile(installed), Duration.ofSeconds(20), "helper did not install file");
            if (!Arrays.equals(Files.readAllBytes(installed), wanted)) {
                throw new AssertionError("Helper-installed bytes differ from server bytes");
            }
            Path updatedUpdater = mods.resolve("MCModSync-" + BuildInfo.VERSION + ".jar");
            waitFor(() -> Files.isRegularFile(updatedUpdater), Duration.ofSeconds(20),
                    "helper did not install its own new filename");
            if (Files.exists(oldUpdater)) {
                throw new AssertionError("Old updater filename was not replaced");
            }
            if (!Arrays.equals(Files.readAllBytes(updatedUpdater), updater)) {
                throw new AssertionError("Self-updated MCModSync bytes differ from published JAR");
            }

            Path helperRuntime = root.resolve(".modsync/helper-runtime-v2");
            waitFor(
                    () -> containsJar(helperRuntime),
                    Duration.ofSeconds(5),
                    "versioned helper-runtime-v2 copy was not retained");

            Path helperLog = root.resolve(".modsync/helper.log");
            waitFor(
                    () -> Files.isRegularFile(helperLog)
                            && Files.readString(helperLog, StandardCharsets.UTF_8)
                                    .contains("退出后更新完成: UPDATED"),
                    Duration.ofSeconds(10),
                    "helper did not report successful completion");
            String helperText = Files.readString(helperLog, StandardCharsets.UTF_8);
            if (helperText.contains("UPDATE_FAILED")) {
                throw new AssertionError("Helper reported failure\n" + helperText);
            }
            System.out.println("Post-build portable helper graceful-exit smoke passed.");
        } finally {
            server.stop(0);
            deleteTree(temporaryRoot);
        }
    }

    private static void respond(HttpExchange exchange, byte[] body) throws IOException {
        try (exchange) {
            if (exchange.getRequestMethod().equalsIgnoreCase("HEAD")) {
                exchange.getResponseHeaders().set("Content-Length", Long.toString(body.length));
                exchange.sendResponseHeaders(200, -1);
                return;
            }
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        }
    }

    private static void waitFor(CheckedCondition condition, Duration timeout, String failure) throws Exception {
        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            if (condition.test()) {
                return;
            }
            Thread.sleep(100L);
        }
        throw new AssertionError(failure);
    }

    private static boolean containsJar(Path directory) throws IOException {
        if (!Files.isDirectory(directory)) {
            return false;
        }
        try (var paths = Files.list(directory)) {
            return paths.anyMatch(path -> path.getFileName().toString().endsWith(".jar"));
        }
    }

    private static void verifyExecutableJarPathWithSemicolon(
            Path java,
            Path jar,
            Path temporaryRoot) throws Exception {
        Path probeDirectory = Files.createDirectories(temporaryRoot.resolve("path;with;semicolons"));
        Path probeJar = probeDirectory.resolve("MCModSync executable probe.jar");
        Files.copy(jar, probeJar);
        ProcessBuilder builder = new ProcessBuilder(
                java.toString(), "-jar", probeJar.getFileName().toString(), "--version");
        builder.directory(probeDirectory.toFile());
        Process probe = builder.redirectErrorStream(true).start();
        if (!probe.waitFor(10, TimeUnit.SECONDS)) {
            probe.destroyForcibly();
            throw new AssertionError("Executable-JAR semicolon-path probe timed out");
        }
        String output = new String(probe.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        if (probe.exitValue() != 0 || !output.contains("MCModSync")) {
            throw new AssertionError("Executable-JAR semicolon-path probe failed\n" + output);
        }
    }

    private static void deleteTree(Path root) throws IOException {
        IOException last = null;
        for (int attempt = 1; attempt <= 50; attempt++) {
            if (!Files.exists(root)) {
                return;
            }
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
                return;
            } catch (IOException exception) {
                last = exception;
                try {
                    Thread.sleep(100L);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Interrupted while waiting for helper log release", interrupted);
                }
            }
        }
        throw new IOException("Portable helper did not release its test files", last);
    }

    @FunctionalInterface
    private interface CheckedCondition {
        boolean test() throws Exception;
    }
}
