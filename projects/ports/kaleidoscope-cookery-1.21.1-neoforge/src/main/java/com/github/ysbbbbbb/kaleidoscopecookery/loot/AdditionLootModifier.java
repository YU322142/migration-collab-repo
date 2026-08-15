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
