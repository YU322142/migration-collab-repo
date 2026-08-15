package com.github.ysbbbbbb.kaleidoscopetavern.compat.jade.block;

import com.github.ysbbbbbb.kaleidoscopetavern.api.blockentity.IPressingTub;
import com.github.ysbbbbbb.kaleidoscopetavern.compat.jade.ModPlugin;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.neoforge.fluids.FluidStack;
import net.neoforged.neoforge.fluids.capability.templates.FluidTank;
import snownee.jade.api.BlockAccessor;
import snownee.jade.api.IServerDataProvider;

public enum PressingTubDataProvider implements IServerDataProvider<BlockAccessor> {
    INSTANCE;

    static final String KEY_FLUID = "kt_fluid";
    static final String KEY_AMOUNT = "kt_amount";
    static final String KEY_CAPACITY = "kt_capacity";

    @Override
    public void appendServerData(CompoundTag data, BlockAccessor accessor) {
        if (!(accessor.getBlockEntity() instanceof IPressingTub pressingTub)) {
            return;
        }
        FluidTank tank = pressingTub.getFluid();
        if (tank == null) {
            return;
        }

        data.putInt(KEY_CAPACITY, tank.getCapacity());
        FluidStack stack = tank.getFluid();
        if (stack.isEmpty()) {
            data.putString(KEY_FLUID, "");
            data.putInt(KEY_AMOUNT, 0);
            return;
        }

        data.putString(KEY_FLUID, BuiltInRegistries.FLUID.getKey(stack.getFluid()).toString());
        data.putInt(KEY_AMOUNT, stack.getAmount());
    }

    @Override
    public ResourceLocation getUid() {
        return ModPlugin.PRESSING_TUB;
    }
}
