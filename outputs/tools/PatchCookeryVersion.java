import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PatchCookeryVersion {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: PatchCookeryVersion <gradle.properties>");
        }
        Path path = Path.of(args[0]);
        String text = Files.readString(path, StandardCharsets.UTF_8);
        String oldLine = "mod_version=1.4.1.7-migration.1-neoforge+mc1.21.1";
        String newLine = "mod_version=1.4.1.7-migration.2-neoforge+mc1.21.1";
        int first = text.indexOf(oldLine);
        if (first < 0 || text.indexOf(oldLine, first + oldLine.length()) >= 0) {
            throw new IllegalStateException("Expected exactly one original mod_version line");
        }
        Files.writeString(path, text.substring(0, first) + newLine
                + text.substring(first + oldLine.length()), StandardCharsets.UTF_8);
        System.out.println("Set Cookery migration version in " + path);
    }
}
