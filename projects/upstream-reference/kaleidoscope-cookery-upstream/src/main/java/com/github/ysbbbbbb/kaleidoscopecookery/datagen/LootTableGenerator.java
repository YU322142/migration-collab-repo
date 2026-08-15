package com.github.ysbbbbbb.kaleidoscopecookery.datagen;

import com.github.ysbbbbbb.kaleidoscopecookery.datagen.lootable.BlockLootTables;
import com.github.ysbbbbbb.kaleidoscopecookery.datagen.lootable.ChestLootTables;
import com.github.ysbbbbbb.kaleidoscopecookery.datagen.lootable.EntityLootTables;
import com.github.ysbbbbbb.kaleidoscopecookery.datagen.lootable.GiftLootTables;
import net.minecraft.data.PackOutput;
import net.minecraft.data.loot.LootTableProvider;
import net.minecraft.world.level.storage.loot.parameters.LootContextParamSets;

import java.util.List;
import java.util.Set;

public class LootTableGenerator extends LootTableProvider {
    public LootTableGenerator(PackOutput pack) {
        super(pack, Set.of(), List.of(
                new LootTableProvider.SubProviderEntry(BlockLootTables::new, LootContextParamSets.BLOCK),
                new LootTableProvider.SubProviderEntry(EntityLootTables::new, LootContextParamSets.ENTITY),
                new LootTableProvider.SubProviderEntry(ChestLootTables::new, LootContextParamSets.CHEST),
                new LootTableProvider.SubProviderEntry(GiftLootTables::new, LootContextParamSets.GIFT)
        ));
    }
}
