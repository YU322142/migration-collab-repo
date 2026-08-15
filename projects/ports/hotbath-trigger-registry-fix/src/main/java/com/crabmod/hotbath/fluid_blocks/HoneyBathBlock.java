package com.crabmod.hotbath.fluid_blocks;

import net.minecraft.world.level.material.FlowingFluid;

import java.util.function.Supplier;

// ** Honey Bath Block */
public class HoneyBathBlock extends AbstractHotbathBlock {
    public HoneyBathBlock(Supplier<? extends FlowingFluid> supplier, Properties properties) {
        super(supplier, properties);
    }
}
