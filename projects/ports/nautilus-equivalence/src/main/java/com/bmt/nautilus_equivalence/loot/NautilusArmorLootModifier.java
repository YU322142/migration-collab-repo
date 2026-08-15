package com.bmt.nautilus_equivalence.loot;

import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import it.unimi.dsi.fastutil.objects.ObjectArrayList;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.storage.loot.LootContext;
import net.minecraft.world.level.storage.loot.LootTable;
import net.minecraft.world.level.storage.loot.predicates.LootItemCondition;
import net.neoforged.neoforge.common.loot.IGlobalLootModifier;
import net.neoforged.neoforge.common.loot.LootModifier;

public final class NautilusArmorLootModifier extends LootModifier {
    public static final MapCodec<NautilusArmorLootModifier> CODEC = RecordCodecBuilder.mapCodec(instance ->
        codecStart(instance)
            .and(ResourceKey.codec(Registries.LOOT_TABLE)
                .fieldOf("table")
                .forGetter(modifier -> modifier.table))
            .apply(instance, NautilusArmorLootModifier::new)
    );

    private final ResourceKey<LootTable> table;

    public NautilusArmorLootModifier(LootItemCondition[] conditions, ResourceKey<LootTable> table) {
        super(conditions);
        this.table = table;
    }

    @SuppressWarnings("deprecation")
    @Override
    protected ObjectArrayList<ItemStack> doApply(ObjectArrayList<ItemStack> generatedLoot, LootContext context) {
        if (context.getQueriedLootTableId().equals(this.table.location())) {
            return generatedLoot;
        }

        context.getResolver().get(Registries.LOOT_TABLE, this.table).ifPresent(addition ->
            addition.value().getRandomItemsRaw(
                context,
                LootTable.createStackSplitter(context.getLevel(), generatedLoot::add)
            )
        );
        return generatedLoot;
    }

    @Override
    public MapCodec<? extends IGlobalLootModifier> codec() {
        return NautilusLootModifiers.ADD_NAUTILUS_ARMOR.get();
    }
}
