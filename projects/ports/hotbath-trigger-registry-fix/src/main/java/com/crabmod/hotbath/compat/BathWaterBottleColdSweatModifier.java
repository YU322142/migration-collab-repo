package com.crabmod.hotbath.compat;

import com.momosoftworks.coldsweat.api.temperature.modifier.TempModifier;
import com.momosoftworks.coldsweat.api.util.Temperature;
import com.momosoftworks.coldsweat.util.world.WorldHelper;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

/**
 * Temperature modifier for bath water bottle effects in Cold Sweat.
 * When a player drinks a bath water bottle, they temporarily get warm temperature (36°C) for 20 seconds.
 */
public class BathWaterBottleColdSweatModifier extends TempModifier {
    
    // Track players who have drunk bath water and when the effect expires
    private static final Map<UUID, Long> WARM_PLAYERS = new ConcurrentHashMap<>();
    
    // Duration of the warm effect in milliseconds (20 seconds)
    private static final long WARM_DURATION_MS = 20_000;
    
    // Target temperature in Celsius
    private static final double TARGET_TEMP_C = 36.0;

    /**
     * Apply warm effect to player for 20 seconds
     * If already active, reset to 20 seconds (not stacking, just resetting duration)
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
    protected Function<Double, Double> calculate(LivingEntity entity, Temperature.Trait trait) {
        // We only modify the WORLD temperature trait
        if (trait != Temperature.Trait.WORLD) {
            return temp -> temp;
        }

        // Only apply to players
        if (!(entity instanceof Player player)) {
            return temp -> temp;
        }

        UUID playerUUID = player.getUUID();
        Long expireTime = WARM_PLAYERS.get(playerUUID);
        
        if (expireTime != null) {
            long currentTime = System.currentTimeMillis();
            
            // Check if effect has expired
            if (currentTime > expireTime) {
                WARM_PLAYERS.remove(playerUUID);
                return temp -> temp;
            }
            
            // Effect is still active
            Level level = entity.level();
            BlockPos pos = entity.blockPosition();
            
            // Calculate target temperature in Minecraft units
            double targetTempMC = Temperature.convert(TARGET_TEMP_C, Temperature.Units.C, Temperature.Units.MC, true);
            
            // Get the current world temperature
            double worldTempMC = WorldHelper.getBiomeTemperature(level, level.getBiome(pos));
            
            // Only apply if target temperature is higher than world temperature
            // If the environment is already warmer, no effect
            if (targetTempMC > worldTempMC) {
                // Return a function that returns the target temperature
                return temp -> Math.max(temp, targetTempMC);
            }
        }
        
        // No active effect or environment is warmer
        return temp -> temp;
    }
}
