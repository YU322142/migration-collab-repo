package com.github.ysbbbbbb.kaleidoscopetavern.datagen.datamap;


import com.github.ysbbbbbb.kaleidoscopetavern.init.ModItems;
import net.minecraft.core.HolderLookup;
import net.minecraft.data.PackOutput;
import net.minecraft.world.item.Item;
import net.neoforged.neoforge.common.data.DataMapProvider;
import net.neoforged.neoforge.registries.DeferredItem;
import net.neoforged.neoforge.registries.datamaps.builtin.Compostable;
import net.neoforged.neoforge.registries.datamaps.builtin.FurnaceFuel;
import net.neoforged.neoforge.registries.datamaps.builtin.NeoForgeDataMaps;

import java.util.concurrent.CompletableFuture;

public class DataMapGenerator extends DataMapProvider {
    private final Builder<FurnaceFuel, Item> furnaceFuels;
    private final Builder<Compostable, Item> compostableBuilder;

    public DataMapGenerator(PackOutput packOutput, CompletableFuture<HolderLookup.Provider> lookupProvider) {
        super(packOutput, lookupProvider);
        this.furnaceFuels = builder(NeoForgeDataMaps.FURNACE_FUELS);
        this.compostableBuilder = builder(NeoForgeDataMaps.COMPOSTABLES);
    }

    @Override
    protected void gather(HolderLookup.Provider provider) {
        furnaceFuels.add(ModItems.GRAPEVINE, new FurnaceFuel(200), false);

        addCompostable(ModItems.GRAPEVINE, 0.25F);
        addCompostable(ModItems.GRAPE, 0.5F);
        addCompostable(ModItems.ICE_GRAPE, 0.5F);
        addCompostable(ModItems.GOLD_GRAPE, 0.5F);
        addCompostable(ModItems.GREEN_GRAPE, 0.5F);
    }

    private void addCompostable(DeferredItem<Item> item, float chance) {
        compostableBuilder.add(item, new Compostable(chance, true), false);
    }
}
