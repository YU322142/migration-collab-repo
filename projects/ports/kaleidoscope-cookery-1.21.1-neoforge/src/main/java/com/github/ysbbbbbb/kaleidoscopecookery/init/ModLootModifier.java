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
