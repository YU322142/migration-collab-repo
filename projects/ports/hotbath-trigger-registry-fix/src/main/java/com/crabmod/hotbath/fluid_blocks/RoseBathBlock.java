package com.crabmod.hotbath.fluid_blocks;

import net.minecraft.world.level.material.FlowingFluid;

import java.util.function.Supplier;

/**
 * Rose Bath Block
 */
public class RoseBathBlock extends AbstractHotbathBlock {
    public RoseBathBlock(Supplier<? extends FlowingFluid> supplier, Properties properties) {
        super(supplier, properties);
    }
}
