package com.crabmod.hotbath.util;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.core.BlockPos;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;

public class SoundHandler {
    public static void playEnterWaterSound(Player player, RandomSource rand) {
        player
                .level()
                .playSound(
                        player,
                        player.blockPosition(),
                        SoundEvents.PLAYER_SPLASH,
                        SoundSource.PLAYERS,
                        rand.nextFloat() * 0.5F,
                        rand.nextFloat() * 0.5F + 0.75F);
    }

    public static void playUnderwaterEnterSound(Player player, RandomSource rand) {
        player
                .level()
                .playSound(
                        player,
                        player.blockPosition(),
                        SoundEvents.AMBIENT_UNDERWATER_ENTER,
                        SoundSource.BLOCKS,
                        rand.nextFloat() * 0.5F,
                        rand.nextFloat() * 0.5F + 0.75F);
    }

    public static void playUnderwaterLoopSound(Player player, RandomSource rand) {
        player
                .level()
                .playSound(
                        player,
                        player.blockPosition(),
                        SoundEvents.AMBIENT_UNDERWATER_LOOP,
                        SoundSource.PLAYERS,
                        1.0F,
                        rand.nextFloat() * 0.5F + 0.75F);
    }

    public static void playExitWaterSound(Player player, RandomSource rand) {
        player
                .level()
                .playSound(
                        player,
                        player.blockPosition(),
                        SoundEvents.AMBIENT_UNDERWATER_EXIT,
                        SoundSource.PLAYERS,
                        rand.nextFloat() * 0.5F + 0.75F,
                        rand.nextFloat() * 0.5F + 0.75F);
    }

    public static void stopUnderwaterLoopSound(Player player) {
        if (player instanceof LocalPlayer) {
            // Get the client's sound manager
            SoundManager soundManager = Minecraft.getInstance().getSoundManager();

            // Stop the underwater loop sound for the player locally
            soundManager.stop(SoundEvents.AMBIENT_UNDERWATER_LOOP.getLocation(), SoundSource.PLAYERS);
        }
    }

    public static void playAmbientWaterSound(Level worldIn, BlockPos pos, RandomSource rand) {
        if (rand.nextInt(64) == 0) {
            double maxDistance = 3.0D;
            double maxDistanceSquared = maxDistance * maxDistance;

            for (var player : worldIn.players()) {
                double distanceSquared = player.distanceToSqr(pos.getX(), pos.getY(), pos.getZ());
                if (distanceSquared > maxDistanceSquared) {
                    continue;
                }

                double distance = Math.sqrt(distanceSquared);
                float volume = (float) ((maxDistance - distance) / maxDistance);

                if (volume > 0) {
                    worldIn.playSound(
                            player,
                            pos,
                            SoundEvents.WATER_AMBIENT,
                            SoundSource.BLOCKS,
                            volume,
                            rand.nextFloat() * 0.5F + 0.75F);
                }
            }
        }
    }
}
