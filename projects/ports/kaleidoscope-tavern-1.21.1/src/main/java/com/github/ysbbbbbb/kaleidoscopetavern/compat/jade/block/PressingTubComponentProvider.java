package com.github.ysbbbbbb.kaleidoscopetavern.compat.jade.block;

import com.github.ysbbbbbb.kaleidoscopetavern.compat.jade.ModPlugin;
import net.minecraft.ChatFormatting;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.material.Fluid;
import net.minecraft.world.level.material.Fluids;
import net.neoforged.neoforge.fluids.FluidStack;
import snownee.jade.api.BlockAccessor;
import snownee.jade.api.IBlockComponentProvider;
import snownee.jade.api.ITooltip;
import snownee.jade.api.config.IPluginConfig;
import snownee.jade.api.ui.BoxStyle;
import snownee.jade.api.ui.IElementHelper;

public enum PressingTubComponentProvider implements IBlockComponentProvider {
    INSTANCE;

    @Override
    public void appendTooltip(ITooltip tooltip, BlockAccessor accessor, IPluginConfig pluginConfig) {
        CompoundTag data = accessor.getServerData();
        int capacity = data.getInt(PressingTubDataProvider.KEY_CAPACITY);
        if (capacity <= 0) {
            capacity = 1000;
        }
        int amount = Math.max(0, data.getInt(PressingTubDataProvider.KEY_AMOUNT));
        float ratio = Math.min(1.0F, (float) amount / capacity);

        ResourceLocation fluidId = ResourceLocation.tryParse(data.getString(PressingTubDataProvider.KEY_FLUID));
        Fluid fluid = fluidId == null ? Fluids.EMPTY : BuiltInRegistries.FLUID.get(fluidId);
        Component label;
        if (fluid == Fluids.EMPTY || amount == 0) {
            label = Component.literal("Liquid: Empty " + amount + "/" + capacity + " mB")
                    .withStyle(ChatFormatting.GRAY);
        } else {
            label = Component.literal("Liquid: ")
                    .append(new FluidStack(fluid, 1).getHoverName())
                    .append(Component.literal(" " + amount + "/" + capacity + " mB"));
        }

        IElementHelper elements = IElementHelper.get();
        tooltip.add(elements.progress(ratio, label, elements.progressStyle(), BoxStyle.getNestedBox(), true));
    }

    @Override
    public ResourceLocation getUid() {
        return ModPlugin.PRESSING_TUB;
    }
}
