package com.crabmod.hotbath.compat;

import net.minecraft.world.entity.player.Player;
import toughasnails.api.temperature.IPlayerTemperatureModifier;
import toughasnails.api.temperature.TemperatureLevel;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Player temperature modifier for bath water bottle effects.
 * When a player drinks a bath water bottle, they temporarily get WARM temperature.
 */
public class BathWaterBottleTANModifier implements IPlayerTemperatureModifier {
    
    // Track players who have drunk bath water and when the effect expires
    private static final Map<UUID, Long> WARM_PLAYERS = new ConcurrentHashMap<>();
    
    // Duration of the warm effect in milliseconds (10 seconds)
    private static final long WARM_DURATION_MS = 10_000;

    /**
     * Apply warm effect to player for 10 seconds
     * If already active, reset to 10 seconds (not stacking, just resetting duration)
     */
    public static void applyWarmEffect(Player player) {
        WARM_PLAYERS.put(player.getUUID(), System.currentTimeMillis() + WARM_DURATION_MS);
    }

    /**
     * Apply warm effect to player for 30 seconds (for splash potions)
     */
    public static void applySplashWarmEffect(Player player) {
        WARM_PLAYERS.put(player.getUUID(), System.currentTimeMillis() + 30_000);
    }

    @Override
    public TemperatureLevel modify(Player player, TemperatureLevel current) {
        UUID playerUUID = player.getUUID();
        Long expireTime = WARM_PLAYERS.get(playerUUID);
        
        if (expireTime != null) {
            long currentTime = System.currentTimeMillis();
            
            // Check if effect has expired
            if (currentTime > expireTime) {
                WARM_PLAYERS.remove(playerUUID);
                return current;
            }
            
            // Effect is still active, return WARM
            return TemperatureLevel.WARM;
        }
        
        // No active effect for this player
        return current;
    }
}
