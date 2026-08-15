package io.github.mcmodsync;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** Small package-local validation harness for a generated MCModSync v4 file. */
public final class ValidateModsyncV4 {
    private ValidateModsyncV4() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ValidateModsyncV4 <mods-v4.txt>");
        }
        String text = Files.readString(Path.of(args[0]), StandardCharsets.UTF_8);
        ModManifest manifest = ModManifest.parse(text);
        long recommended = manifest.entries().stream().filter(ManifestEntry::recommended).count();
        long required = manifest.entries().size() - recommended;
        if (manifest.managedClientConfig().isEmpty()) {
            throw new IllegalStateException("managed client config is absent");
        }
        System.out.println("status=PASS_MCModSync_1_9_2_PARSE");
        System.out.println("catalogVersion=" + manifest.catalogVersion());
        System.out.println("entries=" + manifest.entries().size());
        System.out.println("required=" + required);
        System.out.println("recommended=" + recommended);
        System.out.println("managedClientConfig=true");
    }
}
