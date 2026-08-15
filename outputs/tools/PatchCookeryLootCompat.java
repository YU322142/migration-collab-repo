import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PatchCookeryLootCompat {
    private static final String PACKAGE = "com/github/ysbbbbbb/kaleidoscopecookery/";

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: PatchCookeryLootCompat <repository>");
        }
        Path root = Path.of(args[0]).toAbsolutePath().normalize();
        Path javaRoot = root.resolve("src/main/java");
        if (!Files.isDirectory(javaRoot.resolve(PACKAGE))) {
            throw new IllegalStateException("Unexpected Cookery repository: " + root);
        }

        write(javaRoot.resolve(PACKAGE + "loot/AdditionLootModifier.java"), additionLootModifier());
        write(javaRoot.resolve(PACKAGE + "init/ModLootModifier.java"), modLootModifier());

        Path mod = javaRoot.resolve(PACKAGE + "KaleidoscopeCookery.java");
        String modText = Files.readString(mod, StandardCharsets.UTF_8);
        String newline = modText.contains("\r\n") ? "\r\n" : "\n";
        String anchor = "        ModArmorMaterials.ARMOR_MATERIALS.register(modEventBus);" + newline;
        String replacement = anchor + "        ModLootModifier.GLOBAL_LOOT_MODIFIER_SERIALIZERS.register(modEventBus);\n";
        if (!modText.contains(replacement)) {
            requireCount(modText, anchor, 1, mod);
            modText = modText.replace(anchor, replacement);
            write(mod, modText);
        }

        Path properties = root.resolve("gradle.properties");
        String propertiesText = Files.readString(properties, StandardCharsets.UTF_8);
        String oldVersion = "mod_version=1.4.1.7-migration.2-neoforge+mc1.21.1";
        String newVersion = "mod_version=1.4.1.7-migration.3-neoforge+mc1.21.1";
        if (!propertiesText.contains(newVersion)) {
            requireCount(propertiesText, oldVersion, 1, properties);
            propertiesText = propertiesText.replace(oldVersion, newVersion);
            write(properties, propertiesText);
        }

        System.out.println("Patched NeoForge addition loot modifier compatibility and migration.3 version");
    }

    private static void requireCount(String text, String needle, int expected, Path path) {
        int count = 0;
        for (int index = 0; (index = text.indexOf(needle, index)) >= 0; index += needle.length()) {
            count++;
        }
        if (count != expected) {
            throw new IllegalStateException("Expected " + expected + " occurrence(s) in " + path + ", found " + count);
        }
    }

    private static void write(Path path, String text) throws IOException {
        Files.createDirectories(path.getParent());
        Files.writeString(path, text, StandardCharsets.UTF_8);
    }

    private static String additionLootModifier() {
        return """
                package com.github.ysbbbbbb.kaleidoscopecookery.loot;

                import com.github.ysbbbbbb.kaleidoscopecookery.init.ModLootModifier;
                import com.mojang.serialization.MapCodec;
                import com.mojang.serialization.codecs.RecordCodecBuilder;
                import it.unimi.dsi.fastutil.objects.ObjectArrayList;
                import net.minecraft.core.registries.Registries;
                import net.minecraft.resources.ResourceKey;
                import net.minecraft.resources.ResourceLocation;
                import net.minecraft.world.item.ItemStack;
                import net.minecraft.world.level.storage.loot.LootContext;
                import net.minecraft.world.level.storage.loot.LootTable;
                import net.minecraft.world.level.storage.loot.parameters.LootContextParamSet;
                import net.minecraft.world.level.storage.loot.parameters.LootContextParamSets;
                import net.minecraft.world.level.storage.loot.predicates.LootItemCondition;
                import net.neoforged.neoforge.common.loot.IGlobalLootModifier;
                import net.neoforged.neoforge.common.loot.LootModifier;

                import java.util.Optional;

                public class AdditionLootModifier extends LootModifier {
                    public static final MapCodec<AdditionLootModifier> CODEC = RecordCodecBuilder.mapCodec(instance ->
                            codecStart(instance).and(instance.group(
                                    LootContextParamSets.CODEC.fieldOf("loot_table_type").forGetter(modifier -> modifier.lootTableType),
                                    ResourceLocation.CODEC.optionalFieldOf("loot_table_id").forGetter(modifier -> Optional.ofNullable(modifier.lootTableId)),
                                    ResourceLocation.CODEC.fieldOf("loot_table_add").forGetter(modifier -> modifier.lootTableAdd)
                            )).apply(instance, AdditionLootModifier::new));

                    private final LootContextParamSet lootTableType;
                    private final ResourceLocation lootTableId;
                    private final ResourceLocation lootTableAdd;

                    public AdditionLootModifier(LootItemCondition[] conditions, LootContextParamSet lootTableType,
                                                Optional<ResourceLocation> lootTableId, ResourceLocation lootTableAdd) {
                        super(conditions);
                        this.lootTableType = lootTableType;
                        this.lootTableId = lootTableId.orElse(null);
                        this.lootTableAdd = lootTableAdd;
                    }

                    @Override
                    protected ObjectArrayList<ItemStack> doApply(ObjectArrayList<ItemStack> generatedLoot, LootContext context) {
                        ResourceLocation currentLootTable = context.getQueriedLootTableId();
                        if (!currentLootTable.equals(lootTableAdd) && typeMatches(context, currentLootTable)
                                && (lootTableId == null || currentLootTable.equals(lootTableId))) {
                            ResourceKey<LootTable> additionKey = ResourceKey.create(Registries.LOOT_TABLE, lootTableAdd);
                            context.getResolver().get(Registries.LOOT_TABLE, additionKey).ifPresent(additionTable ->
                                    additionTable.value().getRandomItemsRaw(context,
                                            LootTable.createStackSplitter(context.getLevel(), generatedLoot::add)));
                        }
                        return generatedLoot;
                    }

                    private boolean typeMatches(LootContext context, ResourceLocation currentLootTable) {
                        ResourceKey<LootTable> currentKey = ResourceKey.create(Registries.LOOT_TABLE, currentLootTable);
                        return context.getResolver().get(Registries.LOOT_TABLE, currentKey)
                                .map(table -> table.value().getParamSet().equals(lootTableType))
                                .orElse(false);
                    }

                    @Override
                    public MapCodec<? extends IGlobalLootModifier> codec() {
                        return ModLootModifier.ADDITION.get();
                    }
                }
                """;
    }

    private static String modLootModifier() {
        return """
                package com.github.ysbbbbbb.kaleidoscopecookery.init;

                import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
                import com.github.ysbbbbbb.kaleidoscopecookery.loot.AdditionLootModifier;
                import com.github.ysbbbbbb.kaleidoscopecookery.loot.AdvanceBlockMatchTool;
                import com.github.ysbbbbbb.kaleidoscopecookery.loot.AdvanceEntityMatchTool;
                import com.github.ysbbbbbb.kaleidoscopecookery.loot.RecipeRandomlyFunction;
                import com.mojang.serialization.MapCodec;
                import net.minecraft.core.Registry;
                import net.minecraft.core.registries.BuiltInRegistries;
                import net.minecraft.core.registries.Registries;
                import net.minecraft.world.level.storage.loot.functions.LootItemFunctionType;
                import net.minecraft.world.level.storage.loot.predicates.LootItemConditionType;
                import net.neoforged.bus.api.SubscribeEvent;
                import net.neoforged.fml.common.EventBusSubscriber;
                import net.neoforged.neoforge.common.loot.IGlobalLootModifier;
                import net.neoforged.neoforge.registries.DeferredHolder;
                import net.neoforged.neoforge.registries.DeferredRegister;
                import net.neoforged.neoforge.registries.NeoForgeRegistries;
                import net.neoforged.neoforge.registries.RegisterEvent;

                @EventBusSubscriber(bus = EventBusSubscriber.Bus.MOD)
                public final class ModLootModifier {
                    public static final DeferredRegister<MapCodec<? extends IGlobalLootModifier>> GLOBAL_LOOT_MODIFIER_SERIALIZERS =
                            DeferredRegister.create(NeoForgeRegistries.Keys.GLOBAL_LOOT_MODIFIER_SERIALIZERS, KaleidoscopeCookery.MOD_ID);
                    public static final DeferredHolder<MapCodec<? extends IGlobalLootModifier>, MapCodec<AdditionLootModifier>> ADDITION =
                            GLOBAL_LOOT_MODIFIER_SERIALIZERS.register("addition", () -> AdditionLootModifier.CODEC);

                    public static final LootItemConditionType ADVANCE_ENTITY_MATCH_TOOL = new LootItemConditionType(AdvanceEntityMatchTool.CODEC);
                    public static final LootItemConditionType ADVANCE_BLOCK_MATCH_TOOL = new LootItemConditionType(AdvanceBlockMatchTool.CODEC);
                    public static final LootItemFunctionType<RecipeRandomlyFunction> RECIPE_RANDOMLY = new LootItemFunctionType<>(RecipeRandomlyFunction.CODEC);

                    @SubscribeEvent
                    public static void register(RegisterEvent event) {
                        if (event.getRegistryKey().equals(Registries.LOOT_CONDITION_TYPE)) {
                            Registry.register(BuiltInRegistries.LOOT_CONDITION_TYPE, AdvanceEntityMatchTool.ID, ADVANCE_ENTITY_MATCH_TOOL);
                            Registry.register(BuiltInRegistries.LOOT_CONDITION_TYPE, AdvanceBlockMatchTool.ID, ADVANCE_BLOCK_MATCH_TOOL);
                            Registry.register(BuiltInRegistries.LOOT_FUNCTION_TYPE, RecipeRandomlyFunction.ID, RECIPE_RANDOMLY);
                        }
                    }
                }
                """;
    }
}
