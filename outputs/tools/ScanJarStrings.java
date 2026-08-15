import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.jar.JarFile;

public final class ScanJarStrings {
    private ScanJarStrings() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length < 2) {
            throw new IllegalArgumentException("Usage: ScanJarStrings <jar-directory> <needle> [needle...]");
        }
        Path directory = Path.of(args[0]);
        List<String> needles = List.of(args).subList(1, args.length);
        try (var paths = Files.list(directory)) {
            for (Path path : paths.filter(p -> p.getFileName().toString().endsWith(".jar")).sorted().toList()) {
                scan(path, needles);
            }
        }
    }

    private static void scan(Path path, List<String> needles) throws IOException {
        try (JarFile jar = new JarFile(path.toFile())) {
            var entries = jar.entries();
            while (entries.hasMoreElements()) {
                var entry = entries.nextElement();
                if (entry.isDirectory() || entry.getSize() > 16 * 1024 * 1024) {
                    continue;
                }
                byte[] bytes;
                try (var input = jar.getInputStream(entry)) {
                    bytes = input.readAllBytes();
                }
                String content = new String(bytes, StandardCharsets.ISO_8859_1);
                for (String needle : needles) {
                    if (content.contains(needle)) {
                        System.out.printf("%s\t%s\t%s%n", path.getFileName(), entry.getName(), needle);
                    }
                }
            }
        }
    }
}
