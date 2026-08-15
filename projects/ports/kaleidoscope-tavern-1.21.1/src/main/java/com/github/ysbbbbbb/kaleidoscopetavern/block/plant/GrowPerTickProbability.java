package com.github.ysbbbbbb.kaleidoscopetavern.block.plant;

import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.block.state.BlockState;

@FunctionalInterface
public interface GrowPerTickProbability {
    float getProbability(BlockState state, ServerLevel level, BlockPos pos, RandomSource random);
}
