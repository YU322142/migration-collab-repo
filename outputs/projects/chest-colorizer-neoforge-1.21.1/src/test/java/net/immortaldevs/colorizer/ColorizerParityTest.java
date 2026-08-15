package net.immortaldevs.colorizer;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import net.minecraft.core.BlockPos;

public final class ColorizerParityTest {
    private static int assertions;

    private ColorizerParityTest() {
    }

    public static void main(String[] args) throws Exception {
        testOfficialColorSet();
        testByteStableLoadAndDuplicateSemantics();
        testUnknownLinePreservation();
        testOfficialConfigUpgradeWrite();
        testUncoloredBarrelPreservesOriginalState();
        testRenderMixinsAreMutuallyExclusive();
        System.out.println("Chest Colorizer parity tests: " + assertions + " assertions PASS");
    }

    private static void testOfficialColorSet() {
        List<String> expected = List.of(
                "default", "white", "light_gray", "gray", "black", "brown", "red", "orange",
                "yellow", "lime", "green", "cyan", "light_blue", "blue", "purple", "magenta", "pink"
        );
        List<String> actual = Arrays.stream(BlockColor.values()).map(BlockColor::getName).toList();
        check(expected.equals(actual), "official BlockColor order and names changed");
        for (String name : expected) {
            check(BlockColor.fromName(name) != null, "official color did not parse: " + name);
        }
        check(BlockColor.fromName("RED") == null, "CSV color parsing must stay case-sensitive");
    }

    private static void testByteStableLoadAndDuplicateSemantics() {
        String source = "127.0.0.1:25565;1;64;-2;red\r\n"
                + "127.0.0.1:25565;1;64;-2;blue\r\n"
                + "World Name;-4;70;9;light_gray\r\n";
        ColorizerCsvDocument document = ColorizerCsvDocument.parse(source);
        check(source.equals(document.serialize()), "unmodified official CSV must remain byte-stable");
        check(document.getColor("127.0.0.1:25565", 1, 64, -2) == BlockColor.BLUE,
                "official duplicate-key last-record-wins semantics changed");

        document.setColor("127.0.0.1:25565", 1, 64, -2, BlockColor.GREEN);
        check(document.getColor("127.0.0.1:25565", 1, 64, -2) == BlockColor.GREEN,
                "setColor did not replace the effective duplicate");
        check(document.serialize().contains(";red\r\n"), "historical duplicate was discarded");
        check(document.serialize().contains(";green\r\n"), "effective duplicate was not updated");

        document.removeColor("127.0.0.1:25565", 1, 64, -2);
        check(document.getColor("127.0.0.1:25565", 1, 64, -2) == null,
                "removeColor must remove every record for the coordinate");
        check(document.serialize().equals("World Name;-4;70;9;light_gray\r\n"),
                "removeColor changed an unrelated record");
    }

    private static void testUnknownLinePreservation() {
        String source = "# retained future metadata\n"
                + "server;bad;64;0;red\n"
                + "server;1;64;0;future_color\n"
                + "server;2;64;0;yellow\n";
        ColorizerCsvDocument document = ColorizerCsvDocument.parse(source);
        check(document.validRecordCount() == 1, "invalid records were treated as valid");
        check(document.preservedLineCount() == 3, "unknown records were not preserved");
        document.setColor("server", 3, 64, 0, BlockColor.PINK);
        String saved = document.serialize();
        check(saved.contains("# retained future metadata\n"), "comment line was lost");
        check(saved.contains("server;bad;64;0;red\n"), "malformed coordinate line was lost");
        check(saved.contains("server;1;64;0;future_color\n"), "future color line was lost");
        check(saved.endsWith("server;3;64;0;pink\n"), "new record did not use official five-field format");
    }

    private static void testOfficialConfigUpgradeWrite() throws Exception {
        Path directory = Files.createTempDirectory("colorizer-config-upgrade-");
        Path config = directory.resolve("colorizer.csv");
        String original = "old-server.example;8;70;8;purple\nfuture;line\n";
        Files.writeString(config, original, StandardCharsets.UTF_8);

        ColorizerConfig.load(config);
        check(Files.readString(config, StandardCharsets.UTF_8).equals(original),
                "loading an official 1.21.1 config rewrote it");
        ColorizerConfig.setColor("old-server.example", new BlockPos(9, 70, 8), BlockColor.CYAN);
        String upgraded = Files.readString(config, StandardCharsets.UTF_8);
        check(upgraded.contains("old-server.example;8;70;8;purple\n"), "old color record was lost on upgrade");
        check(upgraded.contains("future;line\n"), "unknown future record was lost on upgrade");
        check(upgraded.endsWith("old-server.example;9;70;8;cyan\n"), "new color record was not persisted");
        check(Files.notExists(config.resolveSibling("colorizer.csv.tmp")), "atomic-save temporary file leaked");
    }

    private static void testUncoloredBarrelPreservesOriginalState() {
        check(!BlockColor.isExplicit(null),
                "missing barrel color must preserve the original resource-pack state");
        check(!BlockColor.isExplicit(BlockColor.DEFAULT),
                "default barrel color must preserve the original resource-pack state");
        check(BlockColor.isExplicit(BlockColor.RED),
                "explicitly colored barrels must still use the synthetic colorizer state");
    }

    private static void testRenderMixinsAreMutuallyExclusive() {
        String vanilla = "net.immortaldevs.colorizer.mixin.SectionCompilerMixin";
        String sodium = "net.immortaldevs.colorizer.mixin.sodium.LevelSliceMixin";
        String unrelated = "net.immortaldevs.colorizer.mixin.BlockMixin";

        check(ColorizerMixinPlugin.shouldApplyRenderMixin(vanilla, false),
                "vanilla section compiler mixin must load when Sodium is absent");
        check(!ColorizerMixinPlugin.shouldApplyRenderMixin(sodium, false),
                "Sodium mixin must not load when Sodium is absent");
        check(!ColorizerMixinPlugin.shouldApplyRenderMixin(vanilla, true),
                "vanilla section compiler mixin must not load alongside Sodium");
        check(ColorizerMixinPlugin.shouldApplyRenderMixin(sodium, true),
                "Sodium level-slice mixin must load when Sodium is present");
        check(ColorizerMixinPlugin.shouldApplyRenderMixin(unrelated, true),
                "unrelated mixins must remain enabled");
    }

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
