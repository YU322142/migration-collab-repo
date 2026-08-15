package com.crabmod.hotbath.util;

import com.crabmod.hotbath.fluid_blocks.AbstractHotbathBlock;
import com.crabmod.hotbath.fluid_blocks.HerbalBathBlock;
import com.crabmod.hotbath.fluid_blocks.HoneyBathBlock;
import com.crabmod.hotbath.fluid_blocks.HotWaterBlock;
import com.crabmod.hotbath.fluid_blocks.MilkBathBlock;
import com.crabmod.hotbath.fluid_blocks.PeonyBathBlock;
import com.crabmod.hotbath.fluid_blocks.RoseBathBlock;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;

public class CustomFluidHandler {

    public static boolean isPlayerHeadInHotBath(Player player) {
        BlockPos playerEyePos = BlockPos.containing(player.getEyePosition());
        BlockState stateAtPlayerPos = player.level().getBlockState(playerEyePos);
        return stateAtPlayerPos.getBlock() instanceof AbstractHotbathBlock;
    }

    public static boolean isPlayerInHotBathBlock(Player player) {
        BlockPos playerPos = player.blockPosition();
        BlockState stateAtPlayerPos = player.level().getBlockState(playerPos);
        return stateAtPlayerPos.getBlock() instanceof AbstractHotbathBlock;
    }

    public static boolean isPlayerInHerbalBathBlock(Player player) {
        BlockPos playerPos = player.blockPosition();
        BlockState stateAtPlayerPos = player.level().getBlockState(playerPos);
        return stateAtPlayerPos.getBlock() instanceof HerbalBathBlock;
    }

    public static boolean isPlayerInHoneyBathBlock(Player player) {
        BlockPos playerPos = player.blockPosition();
        BlockState stateAtPlayerPos = player.level().getBlockState(playerPos);
        return stateAtPlayerPos.getBlock() instanceof HoneyBathBlock;
    }

    public static boolean isPlayerInHotWaterBlock(Player player) {
        BlockPos playerPos = player.blockPosition();
        BlockState stateAtPlayerPos = player.level().getBlockState(playerPos);
        return stateAtPlayerPos.getBlock() instanceof HotWaterBlock;
    }

    public static boolean isPlayerInPeonyBathBlock(Player player) {
        BlockPos playerPos = player.blockPosition();
        BlockState stateAtPlayerPos = player.level().getBlockState(playerPos);
        return stateAtPlayerPos.getBlock() instanceof PeonyBathBlock;
    }

    public static boolean isPlayerInMilkBathBlock(Player player) {
        BlockPos playerPos = player.blockPosition();
        BlockState stateAtPlayerPos = player.level().getBlockState(playerPos);
        Block currentBlock = stateAtPlayerPos.getBlock();
        return stateAtPlayerPos.getBlock() instanceof MilkBathBlock;
    }

    public static boolean isPlayerInRoseBathBlock(Player player) {
        BlockPos playerPos = player.blockPosition();
        BlockState stateAtPlayerPos = player.level().getBlockState(playerPos);
        return stateAtPlayerPos.getBlock() instanceof RoseBathBlock;
    }

    public static boolean isEntityInHerbalBathBlock(Entity entity) {
        BlockPos entityPos = entity.blockPosition();
        BlockState stateAtEntityPos = entity.level().getBlockState(entityPos);
        return stateAtEntityPos.getBlock() instanceof HerbalBathBlock;
    }
}
