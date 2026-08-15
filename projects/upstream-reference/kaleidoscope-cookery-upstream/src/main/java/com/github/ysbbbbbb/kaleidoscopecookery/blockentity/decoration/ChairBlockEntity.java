package com.github.ysbbbbbb.kaleidoscopecookery.blockentity.decoration;

import com.github.ysbbbbbb.kaleidoscopecookery.blockentity.BaseBlockEntity;
import com.github.ysbbbbbb.kaleidoscopecookery.init.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.item.DyeColor;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;

public class ChairBlockEntity extends BaseBlockEntity {
    private static final String COLOR_TAG = "CarpetColor";
    private DyeColor color = DyeColor.WHITE;

    public ChairBlockEntity(BlockPos pos, BlockState blockState) {
        super(ModBlocks.CHAIR_BE.get(), pos, blockState);
    }

    @Override
    protected void saveAdditional(CompoundTag tag) {
        super.saveAdditional(tag);
        tag.putInt(COLOR_TAG, this.color.getId());
    }

    @Override
    public void load(CompoundTag tag) {
        super.load(tag);
        this.color = DyeColor.byId(tag.getInt(COLOR_TAG));
    }

    public DyeColor getColor() {
        return this.color;
    }

    @Override
    public AABB getRenderBoundingBox() {
        return new AABB(this.worldPosition);
    }

    public void setColor(DyeColor color) {
        this.color = color;
    }
}
