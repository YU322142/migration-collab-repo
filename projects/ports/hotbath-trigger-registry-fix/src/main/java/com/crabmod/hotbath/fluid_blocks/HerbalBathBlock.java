package com.crabmod.hotbath.fluid_blocks;

import net.minecraft.world.level.material.FlowingFluid;

import java.util.function.Supplier;

/**
 * Herbal Bath Block
 */
public class HerbalBathBlock extends AbstractHotbathBlock {

    public HerbalBathBlock(Supplier<? extends FlowingFluid> supplier, Properties properties) {
        super(supplier, properties);
    }
}
