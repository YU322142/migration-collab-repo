package com.crabmod.hotbath.compat;

import com.crabmod.hotbath.util.CustomFluidHandler;
import net.minecraft.world.entity.player.Player;

import java.util.UUID;

/**
 * Temperature modifier for bath water bottle effects in Legendary Survival Overhaul.
 * When a player drinks a bath water bottle, they get HOT_DRINK effect for 5 seconds.
 * Effect is stronger (Level 3) if drinking while bathing, otherwise normal (Level 1).
 */
public class BathWaterBottleLSOModifier {

    /**
     * Apply warm effect to player for 5 seconds using HOT_DRINK potion effect.
     * Stronger effect if player is currently bathing.
     */
    public static void applyWarmEffect(Player player) {
        // Check if player is in hot bath for boosted effect
        boolean isBathing = CustomFluidHandler.isPlayerInHotBathBlock(player);
        
        LSOApiHelper.applyBottleTemperatureEffect(player, isBathing);
    }

    /**
     * Apply warm effect to player for 10 seconds (for splash potions)
     */
    public static void applySplashWarmEffect(Player player) {
        LSOApiHelper.applySplashTemperatureEffect(player);
    }
}
