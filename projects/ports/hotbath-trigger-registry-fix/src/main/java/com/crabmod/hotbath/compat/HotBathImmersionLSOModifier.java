package com.crabmod.hotbath.compat;

import com.crabmod.hotbath.util.CustomFluidHandler;
import net.minecraft.world.entity.player.Player;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Temperature modifier that applies when the player is inside a Hot Bath block.
 * Provides two effects:
 * 1. Cold resistance: accumulates every 10 seconds (each 10s adds 1 min, max 5 min)
 * 2. Thermal comfort: after 10 seconds in bath, provides temperature immunity in cold areas
 *    (refreshed every tick, lasts 10 seconds after leaving)
 */
public class HotBathImmersionLSOModifier {

    // Track players currently in bath and their bathing duration
    private static final Map<UUID, Integer> BATH_TIMERS = new ConcurrentHashMap<>();
    
    private static final int UPDATE_INTERVAL = 200; // 10 seconds in ticks
    private static final int RESISTANCE_GAIN_PER_UPDATE = 1200; // 1 minute in ticks
    private static final int THERMAL_COMFORT_START_DELAY = 200; // Start thermal comfort after 10 seconds

    /**
     * Check if a player is currently in bath
     */
    public static boolean isPlayerInBath(UUID playerUUID) {
        return BATH_TIMERS.containsKey(playerUUID);
    }

    /**
     * Accumulate cold resistance effect while in bath
     * Also applies thermal comfort (temperature immunity) after 10 seconds in cold environments
     * Updates effect every 10 seconds
     * Should be called from player tick event
     */
    public static void tick(Player player) {
        UUID playerUUID = player.getUUID();
        boolean isInBath = CustomFluidHandler.isPlayerInHotBathBlock(player);

        if (isInBath) {
            // Increment timer
            int timer = BATH_TIMERS.getOrDefault(playerUUID, 0);
            timer++;
            BATH_TIMERS.put(playerUUID, timer);
            
            // Every 10 seconds, update the cold resistance effect
            if (timer % UPDATE_INTERVAL == 0) {
                LSOApiHelper.updateImmersionResistanceEffect(player, RESISTANCE_GAIN_PER_UPDATE);
            }
            
            // After 10 seconds, start applying thermal comfort every tick (in cold environments)
            if (timer >= THERMAL_COMFORT_START_DELAY) {
                LSOApiHelper.applyThermalComfortEffect(player);
            }
        } else {
            // Player left bath, remove timer
            BATH_TIMERS.remove(playerUUID);
        }
    }

    /**
     * Clean up when player logs out or dies
     */
    public static void cleanup(Player player) {
        BATH_TIMERS.remove(player.getUUID());
        // Cold resistance effect will naturally expire
    }
}
