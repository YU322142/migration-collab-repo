package com.github.ysbbbbbb.kaleidoscopetavern.api.event;

import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;
import net.neoforged.bus.api.Event;
import net.neoforged.bus.api.ICancellableEvent;

/**
 * 种植葡萄事件，在玩家使用葡萄藤种植葡萄时触发，主要用于不同品种普通的种植逻辑
 * <p>
 * 该事件可取消；在多个监听器监听此事件时，取消后不再触发后续逻辑
 */
public final class PlantGrapeEvent extends Event implements ICancellableEvent {
    private final BlockState state;
    private final Level level;
    private final BlockPos pos;
    private final Player player;
    private final InteractionHand hand;
    private final BlockHitResult hitResult;

    public PlantGrapeEvent(BlockState state, Level level, BlockPos pos, Player player,
                           InteractionHand hand, BlockHitResult hitResult) {
        this.state = state;
        this.level = level;
        this.pos = pos;
        this.player = player;
        this.hand = hand;
        this.hitResult = hitResult;
    }

    public BlockState state() {
        return state;
    }

    public Level level() {
        return level;
    }

    public BlockPos pos() {
        return pos;
    }

    public Player player() {
        return player;
    }

    public InteractionHand hand() {
        return hand;
    }

    public BlockHitResult hitResult() {
        return hitResult;
    }
}
