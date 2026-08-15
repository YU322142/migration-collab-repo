package com.crabmod.hotbath.registers;

import com.crabmod.hotbath.HotBath;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

import java.util.function.Supplier;

public class BlocksRegister {
    public static final DeferredRegister<Block> BLOCKS =
            DeferredRegister.create(BuiltInRegistries.BLOCK, HotBath.MOD_ID);

    private static <T extends Block> DeferredHolder<Block, T> registerBlock(
            String name, Supplier<T> block, CreativeModeTab tab) {
        DeferredHolder<Block, T> toReturn = BLOCKS.register(name, block);
        registerBlockItem(name, toReturn, tab);
        return toReturn;
    }

    private static <T extends Block> DeferredHolder<Item, Item> registerBlockItem(
            String name, DeferredHolder<Block, T> block, CreativeModeTab tab) {
        return ItemRegister.ITEMS.register(
                name, () -> new BlockItem(block.get(), new Item.Properties()));
    }

    public static void register(IEventBus eventBus) {
        BLOCKS.register(eventBus);
    }
}
