import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PatchCookeryFoodBites {
    private static String insertOnce(String text, String anchor, String replacement) {
        int first = text.indexOf(anchor);
        if (first < 0 || text.indexOf(anchor, first + anchor.length()) >= 0) {
            throw new IllegalStateException("Expected exactly one anchor: " + anchor);
        }
        return text.substring(0, first) + replacement + text.substring(first + anchor.length());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: PatchCookeryFoodBites <FoodBiteRegistry.java>");
        }

        Path path = Path.of(args[0]);
        String text = Files.readString(path, StandardCharsets.UTF_8);
        String lineEnding = text.contains("\r\n") ? "\r\n" : "\n";
        text = text.replace("\r\n", "\n");
        if (text.contains("public static ResourceLocation BRAISED_FISH;")) {
            throw new IllegalStateException("Food-bite additions are already present");
        }

        text = insertOnce(text,
                "    public static ResourceLocation CHORUS_FRIED_EGG;\n    public static ResourceLocation GOLDEN_SALAD;",
                "    public static ResourceLocation CHORUS_FRIED_EGG;\n    public static ResourceLocation BRAISED_FISH;\n    public static ResourceLocation GOLDEN_SALAD;");
        text = insertOnce(text,
                "    public static ResourceLocation SPICY_CHICKEN;\n    public static ResourceLocation PAN_SEARED_KNIGHT_STEAK;",
                "    public static ResourceLocation SPICY_CHICKEN;\n    public static ResourceLocation YAKITORI;\n    public static ResourceLocation PAN_SEARED_KNIGHT_STEAK;");
        text = insertOnce(text,
                "    public static ResourceLocation SPICY_BLOOD_STEW;\n\n    public static ResourceLocation BRAISED_PORK_RIBS;",
                "    public static ResourceLocation SPICY_BLOOD_STEW;\n    public static ResourceLocation FRUIT_PLATTER;\n\n    public static ResourceLocation BRAISED_PORK_RIBS;");

        text = insertOnce(text,
                "        SPICY_CHICKEN = registry.registerFoodData(\"spicy_chicken\", FoodData\n                .create(4, SPICY_CHICKEN_BLOCK, SPICY_CHICKEN_ITEM));",
                "        BRAISED_FISH = registry.registerFoodData(\"braised_fish\", FoodData\n                .create(4, BRAISED_FISH_BLOCK, BRAISED_FISH_ITEM)\n                .addLootItems(Items.BONE, Items.BONE_MEAL));\n\n        SPICY_CHICKEN = registry.registerFoodData(\"spicy_chicken\", FoodData\n                .create(4, SPICY_CHICKEN_BLOCK, SPICY_CHICKEN_ITEM));\n\n        YAKITORI = registry.registerFoodData(\"yakitori\", FoodData\n                .create(4, YAKITORI_BLOCK, YAKITORI_ITEM));");
        text = insertOnce(text,
                "        // ========================== 1x2",
                "        FRUIT_PLATTER = registry.registerFoodData(\"fruit_platter\", FoodData\n                .create(4, FRUIT_PLATTER_BLOCK, FRUIT_PLATTER_ITEM));\n\n        // ========================== 1x2");

        Files.writeString(path, text.replace("\n", lineEnding), StandardCharsets.UTF_8);
        System.out.println("Patched " + path);
    }
}
