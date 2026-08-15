package com.crabmod.hotbath.compat;

import net.minecraft.core.Holder;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.effect.MobEffectInstance;
import sfiomn.legendarysurvivaloverhaul.registry.MobEffectRegistry;
import sfiomn.legendarysurvivaloverhaul.api.temperature.TemperatureUtil;
import sfiomn.legendarysurvivaloverhaul.api.thirst.ThirstUtil;

import java.util.UUID;

/**
 * Helper class for LSO API calls. Only loaded when LSO is present.
 */
public class LSOApiHelper {
    
    // Bottle effect: HOT_DRINK potion (suitable for drinking)
    private static final int HOT_DRINK_BOTTLE_DURATION = 300; // 15 seconds
    private static final int HOT_DRINK_BOTTLE_AMPLIFIER = 0; // Level 1 (normal)
    private static final int HOT_DRINK_BOTTLE_AMPLIFIER_BOOSTED = 2; // Level 3 (when bathing)
    
    // Immersion effect: Cold resistance for temperature comfort
    private static final int COLD_RESISTANCE_AMPLIFIER = 2; // Level 3 for strong resistance
    private static final int MAX_RESISTANCE_DURATION = 6000; // 5 minutes max
    
    // Thermal comfort effect: Constant temperature in cold environments
    private static final int THERMAL_COMFORT_DURATION = 200; // 10 seconds
    private static final float COLD_TEMPERATURE_THRESHOLD = 16.0f; // Below NORMAL zone (16-24)
    
    private static final int HYDRATION = 5;
    private static final float SATURATION = 0.5f;
    
    /**
     * Apply HOT_DRINK effect for bottle (Level 1 or Level 3 if bathing, 15 seconds)
     * @param isBathing Whether player is currently in hot bath (for boosted effect)
     */
    public static void applyBottleTemperatureEffect(Player player, boolean isBathing) {
        MobEffect hotDrink = MobEffectRegistry.HOT_DRINk.get();
        Holder<MobEffect> hotDrinkHolder = BuiltInRegistries.MOB_EFFECT.wrapAsHolder(hotDrink);
        
        // Use stronger effect if bathing
        int amplifier = isBathing ? HOT_DRINK_BOTTLE_AMPLIFIER_BOOSTED : HOT_DRINK_BOTTLE_AMPLIFIER;
        
        MobEffectInstance effect = new MobEffectInstance(
            hotDrinkHolder,
            HOT_DRINK_BOTTLE_DURATION,
            amplifier,
            false,
            true,
            true
        );
        player.addEffect(effect);
    }
    
    /**
     * Update cold resistance effect by adding duration
     * Called every 10 seconds of bathing to add 1 minute of resistance
     * @param player The player to update
     * @param durationToAdd Duration in ticks to add to the effect
     */
    public static void updateImmersionResistanceEffect(Player player, int durationToAdd) {
        MobEffect coldResistance = MobEffectRegistry.COLD_RESISTANCE.get();
        Holder<MobEffect> coldResistanceHolder = BuiltInRegistries.MOB_EFFECT.wrapAsHolder(coldResistance);
        
        // Get current effect duration, or 0 if not present
        int currentDuration = 0;
        if (player.hasEffect(coldResistanceHolder)) {
            MobEffectInstance currentEffect = player.getEffect(coldResistanceHolder);
            if (currentEffect != null) {
                currentDuration = currentEffect.getDuration();
            }
        }
        
        // Add duration, capped at maximum (5 minutes)
        int newDuration = Math.min(currentDuration + durationToAdd, MAX_RESISTANCE_DURATION);
        
        MobEffectInstance effect = new MobEffectInstance(
            coldResistanceHolder,
            newDuration,
            COLD_RESISTANCE_AMPLIFIER,
            false,
            true,
            true
        );
        player.addEffect(effect);
    }
    
    /**
     * Apply thermal comfort (temperature immunity) in cold environments
     * Provides constant temperature effect for 10 seconds
     * Only applies if player is in cold environment (< 16°C)
     */
    public static void applyThermalComfortEffect(Player player) {
        float currentTemp = TemperatureUtil.getPlayerTargetTemperature(player);
        
        // Only apply if in cold environment
        if (currentTemp >= COLD_TEMPERATURE_THRESHOLD) {
            return;
        }
        
        MobEffect tempImmunity = MobEffectRegistry.TEMPERATURE_IMMUNITY.get();
        Holder<MobEffect> tempImmunityHolder = BuiltInRegistries.MOB_EFFECT.wrapAsHolder(tempImmunity);
        
        MobEffectInstance effect = new MobEffectInstance(
            tempImmunityHolder,
            THERMAL_COMFORT_DURATION,
            0,
            false,
            true,
            true
        );
        player.addEffect(effect);
    }
    
    /**
     * Add thirst and saturation to player
     */
    public static void addThirst(Player player) {
        ThirstUtil.takeDrink(player, HYDRATION, SATURATION);
    }
    
    /**
     * Get thirst values for tooltip
     */
    public static int getHydration() {
        return HYDRATION;
    }
    
    public static float getSaturation() {
        return SATURATION;
    }
    
    /**
     * Apply COLD_RESISTANCE effect for splash bottle (Level 2, 30 seconds)
     */
    public static void applySplashTemperatureEffect(Player player) {
        MobEffect coldResistance = MobEffectRegistry.COLD_RESISTANCE.get();
        Holder<MobEffect> coldResistanceHolder = BuiltInRegistries.MOB_EFFECT.wrapAsHolder(coldResistance);
        
        MobEffectInstance effect = new MobEffectInstance(
            coldResistanceHolder,
            600, // 30 seconds
            1, // Level 2 (Amplifier 1)
            false,
            false,
            true
        );
        player.addEffect(effect);
    }
}
