import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Collectors;

public final class PatchCookeryCode {
    private static final Path NEOFORGE = Path.of("D:/Trans/migration-audit-work/KaleidoscopeCookery-1.21.1-neoforge");
    private static final Path FABRIC = Path.of("D:/Trans/migration-audit-work/KaleidoscopeCookery-1.21.1-fabric");

    public static void main(String[] args) throws Exception {
        patchKnife();
        createCopperTier();
        patchBlocks();
        patchItems();
        patchCreativeTabs();
        patchTrades();
        portFoodProperties();
    }

    private static void patchKnife() throws IOException {
        Path path = java("item/KitchenKnifeItem.java");
        String text = read(path);
        text = replaceOnce(text, indent4("""
                public KitchenKnifeItem(Tier tier) {
                    super(tier, new Properties().attributes(SwordItem.createAttributes(tier, 0, -2.0F)));
                }

                public KitchenKnifeItem(Tier tier, Properties properties) {
                    super(tier, properties.attributes(SwordItem.createAttributes(tier, 0, -2.0F)));
                }
                """), indent4("""
                public KitchenKnifeItem(Tier tier) {
                    this(tier, 3.0F, -2.4F);
                }

                public KitchenKnifeItem(Tier tier, Properties properties) {
                    this(tier, properties, 3.0F, -2.4F);
                }

                public KitchenKnifeItem(Tier tier, float attackDamageBonus, float attackSpeedBonus) {
                    this(tier, new Properties(), attackDamageBonus, attackSpeedBonus);
                }

                public KitchenKnifeItem(Tier tier, Properties properties, float attackDamageBonus, float attackSpeedBonus) {
                    super(tier, properties.stacksTo(1).attributes(SwordItem.createAttributes(tier, attackDamageBonus, attackSpeedBonus)));
                }
                """));
        write(path, text);
    }

    private static void createCopperTier() throws IOException {
        Path path = java("init/ModTiers.java");
        if (Files.exists(path)) {
            throw new IllegalStateException("Refusing to overwrite existing " + path);
        }
        write(path, """
                package com.github.ysbbbbbb.kaleidoscopecookery.init;

                import net.minecraft.tags.BlockTags;
                import net.minecraft.tags.TagKey;
                import net.minecraft.world.item.Items;
                import net.minecraft.world.item.Tier;
                import net.minecraft.world.item.crafting.Ingredient;
                import net.minecraft.world.level.block.Block;

                public final class ModTiers {
                    public static final Tier COPPER = new Tier() {
                        @Override
                        public int getUses() {
                            return 190;
                        }

                        @Override
                        public float getSpeed() {
                            return 5.0F;
                        }

                        @Override
                        public float getAttackDamageBonus() {
                            return 1.0F;
                        }

                        @Override
                        public TagKey<Block> getIncorrectBlocksForDrops() {
                            return BlockTags.INCORRECT_FOR_IRON_TOOL;
                        }

                        @Override
                        public int getEnchantmentValue() {
                            return 13;
                        }

                        @Override
                        public Ingredient getRepairIngredient() {
                            return Ingredient.of(Items.COPPER_INGOT);
                        }
                    };

                    private ModTiers() {
                    }
                }
                """);
    }

    private static void patchBlocks() throws IOException {
        Path path = java("init/ModBlocks.java");
        String text = read(path);
        text = insertAfter(text,
                "    public static DeferredBlock<Block> COOK_STOOL_OAK = BLOCKS.register(\"cook_stool_oak\", CookStoolBlock::new);",
                "    public static DeferredBlock<Block> COOK_STOOL_PALE_OAK = BLOCKS.register(\"cook_stool_pale_oak\", CookStoolBlock::new);");
        text = insertAfter(text,
                "    public static DeferredBlock<Block> CHAIR_OAK = BLOCKS.register(\"chair_oak\", ChairBlock::new);",
                "    public static DeferredBlock<Block> CHAIR_PALE_OAK = BLOCKS.register(\"chair_pale_oak\", ChairBlock::new);");
        text = insertAfter(text,
                "    public static DeferredBlock<Block> TABLE_OAK = BLOCKS.register(\"table_oak\", TableBlock::new);",
                "    public static DeferredBlock<Block> TABLE_PALE_OAK = BLOCKS.register(\"table_pale_oak\", TableBlock::new);");
        text = replaceOnce(text,
                "            CHAIR_JUNGLE.get(), CHAIR_MANGROVE.get(), CHAIR_WARPED.get()",
                "            CHAIR_JUNGLE.get(), CHAIR_MANGROVE.get(), CHAIR_WARPED.get(), CHAIR_PALE_OAK.get()");
        text = replaceOnce(text,
                "            TABLE_JUNGLE.get(), TABLE_MANGROVE.get(), TABLE_WARPED.get()",
                "            TABLE_JUNGLE.get(), TABLE_MANGROVE.get(), TABLE_WARPED.get(), TABLE_PALE_OAK.get()");
        write(path, text);
    }

    private static void patchItems() throws IOException {
        Path path = java("init/ModItems.java");
        String text = read(path);
        text = replaceOnce(text, """
                    public static DeferredItem<Item> IRON_KITCHEN_KNIFE = ITEMS.register("iron_kitchen_knife", () -> new KitchenKnifeItem(Tiers.IRON));
                    public static DeferredItem<Item> GOLD_KITCHEN_KNIFE = ITEMS.register("gold_kitchen_knife", () -> new KitchenKnifeItem(Tiers.GOLD));
                    public static DeferredItem<Item> DIAMOND_KITCHEN_KNIFE = ITEMS.register("diamond_kitchen_knife", () -> new KitchenKnifeItem(Tiers.DIAMOND));
                    public static DeferredItem<Item> NETHERITE_KITCHEN_KNIFE = ITEMS.register("netherite_kitchen_knife", () -> new KitchenKnifeItem(Tiers.NETHERITE, (new Item.Properties()).fireResistant()));
                """, """
                    public static DeferredItem<Item> COPPER_KITCHEN_KNIFE = ITEMS.register("copper_kitchen_knife", () -> new KitchenKnifeItem(ModTiers.COPPER, 2.5F, -2.4F));
                    public static DeferredItem<Item> IRON_KITCHEN_KNIFE = ITEMS.register("iron_kitchen_knife", () -> new KitchenKnifeItem(Tiers.IRON, 3.0F, -2.4F));
                    public static DeferredItem<Item> GOLD_KITCHEN_KNIFE = ITEMS.register("gold_kitchen_knife", () -> new KitchenKnifeItem(Tiers.GOLD, 3.0F, -2.4F));
                    public static DeferredItem<Item> DIAMOND_KITCHEN_KNIFE = ITEMS.register("diamond_kitchen_knife", () -> new KitchenKnifeItem(Tiers.DIAMOND, 3.0F, -2.4F));
                    public static DeferredItem<Item> NETHERITE_KITCHEN_KNIFE = ITEMS.register("netherite_kitchen_knife", () -> new KitchenKnifeItem(Tiers.NETHERITE, (new Item.Properties()).fireResistant(), 3.0F, -2.4F));
                """);
        text = insertAfter(text, item("COOK_STOOL_OAK", "cook_stool_oak", "COOK_STOOL_OAK"), item("COOK_STOOL_PALE_OAK", "cook_stool_pale_oak", "COOK_STOOL_PALE_OAK"));
        text = insertAfter(text, item("CHAIR_OAK", "chair_oak", "CHAIR_OAK"), item("CHAIR_PALE_OAK", "chair_pale_oak", "CHAIR_PALE_OAK"));
        text = insertAfter(text, item("TABLE_OAK", "table_oak", "TABLE_OAK"), item("TABLE_PALE_OAK", "table_pale_oak", "TABLE_PALE_OAK"));
        text = insertAfter(text, bowl("SCRAMBLE_EGG_WITH_TOMATOES_RICE_BOWL", "scramble_egg_with_tomatoes_rice_bowl"), bowl("STIR_FRIED_BEEF_OFFAL", "stir_fried_beef_offal"));
        text = insertAfter(text, bowl("STIR_FRIED_BEEF_OFFAL", "stir_fried_beef_offal"), bowl("STIR_FRIED_BEEF_OFFAL_RICE_BOWL", "stir_fried_beef_offal_rice_bowl"));
        text = insertAfter(text, bowl("SWEET_AND_SOUR_PORK_RICE_BOWL", "sweet_and_sour_pork_rice_bowl"), bowl("COUNTRY_STYLE_MIXED_VEGETABLES", "country_style_mixed_vegetables"));
        text = insertAfter(text, bowl("FISH_FLAVORED_SHREDDED_PORK_RICE_BOWL", "fish_flavored_shredded_pork_rice_bowl"), bowl("BRAISED_FISH_RICE_BOWL", "braised_fish_rice_bowl"));
        text = insertAfter(text, bowl("BRAISED_FISH_RICE_BOWL", "braised_fish_rice_bowl"), bowl("SPICY_CHICKEN_RICE_BOWL", "spicy_chicken_rice_bowl"));
        text = insertAfter(text, bowl("SPICY_CHICKEN_RICE_BOWL", "spicy_chicken_rice_bowl"), bowl("SUSPICIOUS_STIR_FRY_RICE_BOWL", "suspicious_stir_fry_rice_bowl"));
        text = insertAfter(text, bowl("SUSPICIOUS_STIR_FRY_RICE_BOWL", "suspicious_stir_fry_rice_bowl"), bowl("DELICIOUS_EGG_FRIED_RICE", "delicious_egg_fried_rice"));
        text = insertAfter(text, bowl("WILD_MUSHROOM_RABBIT_SOUP", "wild_mushroom_rabbit_soup"), bowl("TOMATO_BEEF_BRISKET_SOUP", "tomato_beef_brisket_soup"));
        text = insertAfter(text, bowl("CHICKEN_AND_MUSHROOM_STEW", "chicken_and_mushroom_stew"), bowl("DONKEY_SOUP", "donkey_soup"));
        text = insertAfter(text, food("RAW_PORK_BELLY", "raw_pork_belly"), food("RAW_DONKEY_MEAT", "raw_donkey_meat"));
        text = insertAfter(text, food("COOKED_PORK_BELLY", "cooked_pork_belly"), food("COOKED_DONKEY_MEAT", "cooked_donkey_meat"));
        write(path, text);
    }

    private static void patchCreativeTabs() throws IOException {
        Path path = java("init/ModCreativeTabs.java");
        String text = read(path);
        text = insertAfter(text, accept("SICKLE"), accept("COPPER_KITCHEN_KNIFE"));
        text = insertAfter(text, accept("COOK_STOOL_OAK"), accept("COOK_STOOL_PALE_OAK"));
        text = insertAfter(text, accept("CHAIR_OAK"), accept("CHAIR_PALE_OAK"));
        text = insertAfter(text, accept("TABLE_OAK"), accept("TABLE_PALE_OAK"));
        text = insertAfter(text, accept("COOKED_PORK_BELLY"), accept("RAW_DONKEY_MEAT"));
        text = insertAfter(text, accept("RAW_DONKEY_MEAT"), accept("COOKED_DONKEY_MEAT"));
        text = insertAfter(text, accept("EGG_FRIED_RICE"), accept("DELICIOUS_EGG_FRIED_RICE"));
        text = insertAfter(text, accept("SCRAMBLE_EGG_WITH_TOMATOES_RICE_BOWL"), accept("STIR_FRIED_BEEF_OFFAL"));
        text = insertAfter(text, accept("STIR_FRIED_BEEF_OFFAL"), accept("STIR_FRIED_BEEF_OFFAL_RICE_BOWL"));
        text = insertAfter(text, accept("SWEET_AND_SOUR_PORK_RICE_BOWL"), accept("COUNTRY_STYLE_MIXED_VEGETABLES"));
        text = insertAfter(text, accept("FISH_FLAVORED_SHREDDED_PORK_RICE_BOWL"), accept("BRAISED_FISH_RICE_BOWL"));
        text = insertAfter(text, accept("BRAISED_FISH_RICE_BOWL"), accept("SPICY_CHICKEN_RICE_BOWL"));
        text = insertAfter(text, accept("SPICY_CHICKEN_RICE_BOWL"), accept("SUSPICIOUS_STIR_FRY_RICE_BOWL"));
        text = insertAfter(text, accept("WILD_MUSHROOM_RABBIT_SOUP"), accept("TOMATO_BEEF_BRISKET_SOUP"));
        text = insertAfter(text, accept("CHICKEN_AND_MUSHROOM_STEW"), accept("DONKEY_SOUP"));
        write(path, text);
    }

    private static void patchTrades() throws IOException {
        Path path = java("event/ModTradesEvent.java");
        String text = read(path);
        text = replaceOnce(text,
                "RecipeItem.RecipeRecord.pot(SCRAMBLE_EGG_WITH_TOMATOES, FRIED_EGG, FRIED_EGG, FRIED_EGG, TOMATO, TOMATO, TOMATO)",
                "RecipeItem.RecipeRecord.pot(SCRAMBLE_EGG_WITH_TOMATOES, FRIED_EGG, FRIED_EGG, TOMATO, TOMATO)");
        text = insertAfter(text,
                "    private static void addJourneymanTrades(VillagerTradesEvent event) {",
                "        addTrade(event, 3, DELICIOUS_EGG_FRIED_RICE.get(), 1, EMERALD, 3, 16, 5, 0.05f);\n" +
                "        addTrade(event, 3, SUSPICIOUS_STIR_FRY_RICE_BOWL.get(), 3, EMERALD, 1, 16, 5, 0.05f);");
        text = insertAfter(text,
                "        addTrade(event, 3, FoodBiteRegistry.getItem(FoodBiteRegistry.DARK_CUISINE), 5, EMERALD, 2, 16, 5, 0.1f);",
                "\n        addTrade(event, 3, EMERALD, 3,\n" +
                "                RecipeItem.RecipeRecord.stockpot(TOMATO_BEEF_BRISKET_SOUP.get(), BEEF, BEEF, BEEF, TOMATO.get(), TOMATO.get(), TOMATO.get()),\n" +
                "                16, 4, 0.1f);");
        text = replaceOnce(text,
                "RecipeItem.RecipeRecord.stockpot(PUFFERFISH_SOUP.get(), PUFFERFISH, PUFFERFISH, PUFFERFISH, SEAGRASS, SEAGRASS)",
                "RecipeItem.RecipeRecord.stockpot(PUFFERFISH_SOUP.get(), PUFFERFISH, PUFFERFISH, PUFFERFISH, SEAGRASS)");
        text = replaceOnce(text,
                "RecipeItem.RecipeRecord.stockpot(BRAISED_BEEF_WITH_POTATOES.get(), BEEF, BEEF, BEEF, POTATO, POTATO, POTATO, POTATO)",
                "RecipeItem.RecipeRecord.stockpot(BRAISED_BEEF_WITH_POTATOES.get(), BEEF, BEEF, POTATO, POTATO, POTATO)");
        text = insertAfter(text,
                "        addTrade(event, 4, WILD_MUSHROOM_RABBIT_SOUP.get(), 1, EMERALD, 3, 16, 10, 0.1f);",
                "        addTrade(event, 4, TOMATO_BEEF_BRISKET_SOUP.get(), 1, EMERALD, 2, 16, 10, 0.1f);");
        text = replaceOnce(text,
                "                        PORKCHOP, PORKCHOP, PORKCHOP,\n                        PORKCHOP, PORKCHOP, PORKCHOP),",
                "                        PORKCHOP, PORKCHOP, PORKCHOP),");
        text = replaceOnce(text,
                "                        TROPICAL_FISH, TROPICAL_FISH,\n                        TROPICAL_FISH, TROPICAL_FISH),",
                "                        TROPICAL_FISH, TROPICAL_FISH),");
        text = replaceOnce(text,
                "                        SLIME_BALL, SLIME_BALL, SLIME_BALL, SLIME_BALL),",
                "                        SLIME_BALL, SLIME_BALL, SLIME_BALL, SLIME_BALL, SLIME_BALL, SLIME_BALL),");
        text = replaceOnce(text,
                "                        RED_CHILI.get(), RED_CHILI.get(), RED_CHILI.get(),\n                        RED_CHILI.get(), RED_CHILI.get(),",
                "                        GREEN_CHILI.get(), GREEN_CHILI.get(), GREEN_CHILI.get(),");
        text = insertAfter(text, """
                        addTrade(event, 4, EMERALD, 5,
                                RecipeItem.RecipeRecord.pot(FoodBiteRegistry.getItem(FoodBiteRegistry.SPICY_CHICKEN),
                                        GREEN_CHILI.get(), GREEN_CHILI.get(), GREEN_CHILI.get(),
                                        CHICKEN, CHICKEN, CHICKEN, CHICKEN),
                                16, 4, 0.1f);
                """.stripTrailing(), """

                        addTrade(event, 4, EMERALD, 5,
                                RecipeItem.RecipeRecord.pot(FoodBiteRegistry.getItem(FoodBiteRegistry.YAKITORI),
                                        GREEN_CHILI.get(), GREEN_CHILI.get(),
                                        CHICKEN, CHICKEN, CHICKEN, CHICKEN),
                                16, 4, 0.1f);
                """.stripTrailing());
        write(path, text);
    }

    private static void portFoodProperties() throws IOException {
        Path source = FABRIC.resolve("src/main/java/com/github/ysbbbbbb/kaleidoscopecookery/init/ModFoods.java");
        String text = read(source).replace(".effect(new MobEffectInstance(", ".effect(() -> new MobEffectInstance(");
        if (text.contains(".effect(new MobEffectInstance(")) {
            throw new IllegalStateException("Unconverted FoodProperties effect");
        }
        write(java("init/ModFoods.java"), text);
    }

    private static Path java(String relative) {
        return NEOFORGE.resolve("src/main/java/com/github/ysbbbbbb/kaleidoscopecookery").resolve(relative);
    }

    private static String item(String field, String id, String blockField) {
        return "    public static DeferredItem<Item> " + field + " = ITEMS.register(\"" + id + "\", () -> new BlockItem(ModBlocks." + blockField + ".get(), new Item.Properties()));";
    }

    private static String bowl(String field, String id) {
        return "    public static DeferredItem<Item> " + field + " = ITEMS.register(\"" + id + "\", () -> new BowlFoodOnlyItem(ModFoods." + field + "));";
    }

    private static String food(String field, String id) {
        return "    public static DeferredItem<Item> " + field + " = ITEMS.register(\"" + id + "\", () -> new Item(new Item.Properties().food(ModFoods." + field + ")));";
    }

    private static String accept(String field) {
        return "                output.accept(ModItems." + field + ".get());";
    }

    private static String insertAfter(String text, String anchor, String addition) {
        return replaceOnce(text, anchor, anchor + "\n" + addition);
    }

    private static String indent4(String text) {
        return text.stripTrailing().lines()
                .map(line -> line.isEmpty() ? line : "    " + line)
                .collect(Collectors.joining("\n"));
    }

    private static String replaceOnce(String text, String before, String after) {
        int first = text.indexOf(before);
        if (first < 0 || text.indexOf(before, first + before.length()) >= 0) {
            throw new IllegalStateException("Expected exactly one match for:\n" + before);
        }
        return text.substring(0, first) + after + text.substring(first + before.length());
    }

    private static String read(Path path) throws IOException {
        return Files.readString(path, StandardCharsets.UTF_8).replace("\r\n", "\n");
    }

    private static void write(Path path, String text) throws IOException {
        Files.createDirectories(path.getParent());
        Files.writeString(path, text, StandardCharsets.UTF_8);
    }
}
