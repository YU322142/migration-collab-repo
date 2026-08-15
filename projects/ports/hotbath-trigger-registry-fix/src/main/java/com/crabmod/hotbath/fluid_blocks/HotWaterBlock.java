package com.crabmod.hotbath.fluid_blocks;

import net.minecraft.world.level.material.FlowingFluid;

import java.util.function.Supplier;

/**
 * Hot Water Block
 */
public class HotWaterBlock extends AbstractHotbathBlock {
    public HotWaterBlock(Supplier<? extends FlowingFluid> supplier, Properties properties) {
        super(supplier, properties);
    }
}
