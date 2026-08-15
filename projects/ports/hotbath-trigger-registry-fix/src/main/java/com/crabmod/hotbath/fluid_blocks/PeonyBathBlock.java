package com.crabmod.hotbath.fluid_blocks;

import net.minecraft.world.level.material.FlowingFluid;

import java.util.function.Supplier;

/**
 * Peony Bath Block
 */
public class PeonyBathBlock extends AbstractHotbathBlock {
    public PeonyBathBlock(Supplier<? extends FlowingFluid> supplier, Properties properties) {
        super(supplier, properties);
    }
}
