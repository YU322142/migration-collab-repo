package com.crabmod.hotbath.fluid_blocks;

import net.minecraft.world.level.material.FlowingFluid;

import java.util.function.Supplier;

/**
 * Milk Bath Block
 */
public class MilkBathBlock extends AbstractHotbathBlock {
    public MilkBathBlock(Supplier<? extends FlowingFluid> supplier, Properties properties) {
        super(supplier, properties);
    }
}
