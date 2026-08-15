package com.github.ysbbbbbb.kaleidoscopetavern.game.tap.impl;

import com.github.ysbbbbbb.kaleidoscopetavern.api.blockentity.ITapBehavior;
import com.github.ysbbbbbb.kaleidoscopetavern.block.brew.BarrelBlock;
import com.github.ysbbbbbb.kaleidoscopetavern.block.brew.TapBlock;
import com.github.ysbbbbbb.kaleidoscopetavern.blockentity.brew.BarrelBlockEntity;
import com.github.ysbbbbbb.kaleidoscopetavern.init.ModItems;
import com.github.ysbbbbbb.kaleidoscopetavern.init.ModParticles;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.AttachFace;

import javax.annotation.Nullable;

public class BarrelTapBehavior implements ITapBehavior {
    @Override
    public boolean isMatch(
            Level level, @Nullable Player player,
            BlockPos tapPos, BlockState tapState,
            BlockState sourceState, BlockState destinationState
    ) {
        Direction tapFacing = tapState.getValue(TapBlock.FACING);
        if (!isValidConnection(sourceState, tapFacing)) {
            return false;
        }
        BlockPos relative = tapPos.relative(tapFacing.getOpposite());
        BlockState barrelState = level.getBlockState(relative);
        BarrelBlockEntity barrelEntity = BarrelBlock.getBarrelEntity(level, relative, barrelState);
        if (barrelEntity == null) {
            return false;
        }
        return barrelEntity.canTapExtract(level, tapPos, player);
    }

    @Override
    public ParticleOptions onStartExtract(
            Level level, @Nullable Player player,
            BlockPos tapPos, BlockState tapState,
            BlockState sourceState, BlockState destinationState
    ) {
        Direction tapFacing = tapState.getValue(TapBlock.FACING);
        BlockPos relative = tapPos.relative(tapFacing.getOpposite());
        BlockState barrelState = level.getBlockState(relative);
        BarrelBlockEntity barrelEntity = BarrelBlock.getBarrelEntity(level, relative, barrelState);
        if (barrelEntity == null) {
            return null;
        }

        // 播放滴水粒子效果
        ParticleOptions particle = ModParticles.WATER_TAP_DRIP.get();
        // 燃烧瓶很特殊
        // FIXME: 应该用 tag 来决定粒子的效果？
        if (barrelEntity.getOutput().getStackInSlot(0).is(ModItems.MOLOTOV.get())) {
            particle = ModParticles.LAVA_TAP_DRIP.get();
        }
        return particle;
    }

    @Override
    public void onEndExtract(
            Level level,
            BlockPos tapPos, BlockState tapState,
            BlockState sourceState, BlockState destinationState
    ) {
        Direction tapFacing = tapState.getValue(TapBlock.FACING);
        BlockPos relative = tapPos.relative(tapFacing.getOpposite());
        BlockState barrelState = level.getBlockState(relative);

        BarrelBlockEntity barrelEntity = BarrelBlock.getBarrelEntity(level, relative, barrelState);
        if (barrelEntity == null) {
            return;
        }
        barrelEntity.doTapExtract(level, tapPos);

        // 播放酒瓶转化效果
        level.playSound(null, tapPos.below(), SoundEvents.BREWING_STAND_BREW, SoundSource.BLOCKS, 1.0F, 1.0F);
        ITapBehavior.sendParticles(level, tapPos);
    }

    private boolean isValidConnection(BlockState barrelState, Direction tapFacing) {
        Direction barrelFacing = barrelState.getValue(BarrelBlock.FACING);
        AttachFace layer = barrelState.getValue(BarrelBlock.LAYER);
        int index = barrelState.getValue(BarrelBlock.INDEX);
        // 必须紧贴桶第二层正面
        if (layer == AttachFace.WALL) {
            if (barrelFacing == Direction.NORTH && index == 1) {
                return tapFacing == Direction.NORTH;
            } else if (barrelFacing == Direction.SOUTH && index == 7) {
                return tapFacing == Direction.SOUTH;
            } else if (barrelFacing == Direction.WEST && index == 3) {
                return tapFacing == Direction.WEST;
            } else if (barrelFacing == Direction.EAST && index == 5) {
                return tapFacing == Direction.EAST;
            }
        }
        return false;
    }
}
