package com.crabmod.hotbath.util;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerPlayer;

public class HealthRegenHandler {
    public static void regenHealth(
            float regenHealthNumber, double perSecondsNumber, ServerPlayer player) {

        CompoundTag playerData = player.getPersistentData();
        String healthRegenTimerKey = "healthRegenTimer";

        int healthRegenTimer = playerData.getInt(healthRegenTimerKey) + 1;
        playerData.putInt(healthRegenTimerKey, healthRegenTimer);

        if (healthRegenTimer >= 20 * perSecondsNumber) {
            float currentHealth = player.getHealth();
            float maxHealth = player.getMaxHealth();

            if (currentHealth < maxHealth) {
                player.setHealth(Math.min(currentHealth + regenHealthNumber, maxHealth));
            }
            playerData.putInt(healthRegenTimerKey, 0);
        }
    }
}
