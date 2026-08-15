package com.github.ysbbbbbb.kaleidoscopetavern.api.blockentity;

import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;

import javax.annotation.Nullable;

/**
 * 龙头提取行为接口。
 * <p>
 * 你可以在模组初始化流程或相关事件中，将方块与对应行为注册到
 * {@code TapBehaviorManager}，从而为不同方块提供自定义提取逻辑。
 * <p>
 * 注册入口：
 * {@code com.github.ysbbbbbb.kaleidoscopetavern.game.tap.TapBehaviorManager#register(
 * net.minecraft.world.level.block.Block,
 * com.github.ysbbbbbb.kaleidoscopetavern.api.blockentity.ITapBehavior)}
 */
public interface ITapBehavior {
    /**
     * 工具方法，用于生成一个接出后的粒子效果
     */
    static void sendParticles(Level level, BlockPos tapPos) {
        if (level instanceof ServerLevel serverLevel) {
            serverLevel.sendParticles(
                    ParticleTypes.WAX_OFF,
                    tapPos.getX() + 0.5,
                    tapPos.getY() - 0.5,
                    tapPos.getZ() + 0.5,
                    10, 0.25, 0.25, 0.25, 0.1
            );
        }
    }

    /**
     *
     * @param level            当前所处的世界
     * @param player           执行提取操作的玩家，可能为空（比如红石自动化控制等情况）
     * @param tapPos           水龙头所处的位置
     * @param tapState         龙头的方块状态
     * @param sourceState      龙头紧贴的那个方块状态
     * @param destinationState 龙头下方方块的方块状态
     * @return 是否满足条件
     */
    boolean isMatch(
            Level level, @Nullable Player player,
            BlockPos tapPos, BlockState tapState,
            BlockState sourceState, BlockState destinationState
    );

    /**
     * 龙头打开时的逻辑
     *
     * @param level            当前所处的世界
     * @param player           执行提取操作的玩家，可能为空（比如红石自动化控制等情况）
     * @param tapPos           水龙头所处的位置
     * @param tapState         龙头的方块状态
     * @param sourceState      龙头紧贴的那个方块状态
     * @param destinationState 龙头下方方块的方块状态
     * @return 可能产生的龙头的粒子效果，返回 null 则没有粒子效果
     */
    @Nullable
    ParticleOptions onStartExtract(
            Level level, @Nullable Player player,
            BlockPos tapPos, BlockState tapState,
            BlockState sourceState, BlockState destinationState
    );

    /**
     * 龙头关闭时的逻辑
     *
     * @param level            当前所处的世界
     * @param tapPos           水龙头所处的位置
     * @param tapState         龙头的方块状态
     * @param sourceState      龙头紧贴的那个方块状态
     * @param destinationState 龙头下方方块的方块状态
     */
    void onEndExtract(
            Level level,
            BlockPos tapPos, BlockState tapState,
            BlockState sourceState, BlockState destinationState
    );
}
