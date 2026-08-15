package com.github.ysbbbbbb.kaleidoscopecookery.blockentity.decoration;

import com.github.ysbbbbbb.kaleidoscopecookery.blockentity.BaseBlockEntity;
import com.github.ysbbbbbb.kaleidoscopecookery.init.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.items.ItemStackHandler;

public class RecipeBlockEntity extends BaseBlockEntity {
    private static final String SHOW_ITEMS = "ShowItems";
    private ItemStackHandler items = new ItemStackHandler(1);

    public RecipeBlockEntity(BlockPos pos, BlockState blockState) {
        super(ModBlocks.RECIPE_BLOCK_BE.get(), pos, blockState);
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.put(SHOW_ITEMS, this.items.serializeNBT(registries));
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        if (tag.contains(SHOW_ITEMS)) {
            this.items.deserializeNBT(registries, tag.getCompound(SHOW_ITEMS));
        }
    }

    public ItemStackHandler getItems() {
        return items;
    }
}
