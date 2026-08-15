package com.crabmod.hotbath.util;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerPlayer;

public class HungerRegenHandler {
    public static void regenHunger(
            int regenHungerNumber, float perSecondsNumber, ServerPlayer player) {
        CompoundTag playerData = player.getPersistentData();
        String hungerRegenTimerKey = "hungerRegenTimer";

        int hungerRegenTimer = playerData.getInt(hungerRegenTimerKey) + 1;
        playerData.putInt(hungerRegenTimerKey, hungerRegenTimer);

        int ticksPerRegen =
                (int) (perSecondsNumber * 20); // Calculate the number of ticks required to recover

        if (hungerRegenTimer >= ticksPerRegen) { // Regenerate based on the given number of seconds
            int currentFoodLevel = player.getFoodData().getFoodLevel();
            int maxFoodLevel = 20;

            if (currentFoodLevel < maxFoodLevel) {
                player.getFoodData().eat(regenHungerNumber, 0);
            }
            playerData.putInt(hungerRegenTimerKey, 0);
        }
    }
}
