package com.crabmod.hotbath.items;

import com.crabmod.hotbath.compat.*;
import net.minecraft.core.Holder;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.LivingEntity;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Drinking effects for bath water bottles
 */
public class BathWaterEffects {
    private static final Random RANDOM = new Random();

    /**
     * Hot Water Bottle Effect: Speed I for 45 seconds
     */
    public static void hotWaterEffect(LivingEntity entity) {
        entity.addEffect(new MobEffectInstance(MobEffects.MOVEMENT_SPEED, 45 * 20, 0, false, false, true));
        applyDrinkTemperatureEffects(entity);
    }

    public static void hotWaterSplashEffect(LivingEntity entity) {
        entity.addEffect(new MobEffectInstance(MobEffects.MOVEMENT_SPEED, 30 * 20, 1, false, false, true));
        applySplashTemperatureEffects(entity);
    }

    /**
     * Honey Bath Water Effect: Absorption I for 45 seconds
     */
    public static void honeyBathEffect(LivingEntity entity) {
        entity.addEffect(new MobEffectInstance(MobEffects.ABSORPTION, 45 * 20, 0, false, false, true));
        applyDrinkTemperatureEffects(entity);
    }

    public static void honeyBathSplashEffect(LivingEntity entity) {
        entity.addEffect(new MobEffectInstance(MobEffects.ABSORPTION, 30 * 20, 1, false, false, true));
        applySplashTemperatureEffects(entity);
    }

    /**
     * Milk Bath Water Effect: Remove 1 random harmful effect (weakened from removing all)
     */
    public static void milkBathEffect(LivingEntity entity) {
        removeNegativeEffects(entity, 1);
        applyDrinkTemperatureEffects(entity);
    }

    public static void milkBathSplashEffect(LivingEntity entity) {
        removeNegativeEffects(entity, 2);
        applySplashTemperatureEffects(entity);
    }

    private static void removeNegativeEffects(LivingEntity entity, int count) {
        List<MobEffectInstance> harmfulEffects = new ArrayList<>();
        
        for (MobEffectInstance effect : entity.getActiveEffects()) {
            Holder<MobEffect> effectHolder = effect.getEffect();
            if (isHarmfulEffect(effectHolder) && effectHolder != MobEffects.UNLUCK) {
                harmfulEffects.add(effect);
            }
        }
        
        for (int i = 0; i < count && !harmfulEffects.isEmpty(); i++) {
             MobEffectInstance effectToRemove = harmfulEffects.get(RANDOM.nextInt(harmfulEffects.size()));
             entity.removeEffect(effectToRemove.getEffect());
             harmfulEffects.remove(effectToRemove);
        }
    }

    /**
     * Herbal Bath Water Effect: Instant heal 3 hearts + Resistance I for 45 seconds
     */
    public static void herbalBathEffect(LivingEntity entity) {
        entity.heal(6.0F); // Instant heal 3 hearts
        entity.addEffect(new MobEffectInstance(MobEffects.DAMAGE_RESISTANCE, 45 * 20, 0, false, false, true));
        applyDrinkTemperatureEffects(entity);
    }

    public static void herbalBathSplashEffect(LivingEntity entity) {
        entity.heal(4.0F); // Instant heal 2 hearts
        entity.addEffect(new MobEffectInstance(MobEffects.DAMAGE_RESISTANCE, 30 * 20, 1, false, false, true));
        applySplashTemperatureEffects(entity);
    }

    /**
     * Peony Bath Water Effect: Luck I for 45 seconds
     */
    public static void peonyBathEffect(LivingEntity entity) {
        entity.addEffect(new MobEffectInstance(MobEffects.LUCK, 45 * 20, 0, false, false, true));
        applyDrinkTemperatureEffects(entity);
    }

    public static void peonyBathSplashEffect(LivingEntity entity) {
        entity.addEffect(new MobEffectInstance(MobEffects.LUCK, 30 * 20, 1, false, false, true));
        applySplashTemperatureEffects(entity);
    }

    /**
     * Rose Bath Water Effect: Strength I for 45 seconds
     */
    public static void roseBathEffect(LivingEntity entity) {
        entity.addEffect(new MobEffectInstance(MobEffects.DAMAGE_BOOST, 45 * 20, 0, false, false, true));
        applyDrinkTemperatureEffects(entity);
    }

    public static void roseBathSplashEffect(LivingEntity entity) {
        entity.addEffect(new MobEffectInstance(MobEffects.DAMAGE_BOOST, 30 * 20, 1, false, false, true));
        applySplashTemperatureEffects(entity);
    }

    /**
     * Apply temperature and thirst effects for ToughAsNails, Cold Sweat, and Legendary Survival Overhaul if mods are loaded
     */
    private static void applyDrinkTemperatureEffects(LivingEntity entity) {
        if (!(entity instanceof net.minecraft.world.entity.player.Player player)) {
            return;
        }
        
        // Apply ToughAsNails temperature effect (10 seconds, WARM) and restore thirst
        if (ToughAsNailsIntegration.isToughAsNailsLoaded()) {
            BathWaterBottleTANModifier.applyWarmEffect(player);
            ToughAsNailsThirstHelper.restoreThirst(player);
        }
        
        // Apply Cold Sweat temperature effect (20 seconds, 36°C)
        if (ColdSweatIntegration.isColdSweatLoaded()) {
            BathWaterBottleColdSweatModifier.applyWarmEffect(player);
        }
        
        // Apply Legendary Survival Overhaul temperature effect (5 seconds, 20.0)
        if (LegendarySurvivalOverhaulIntegration.isLSOLoaded()) {
            BathWaterBottleLSOModifier.applyWarmEffect(player);
        }
    }

    private static void applySplashTemperatureEffects(LivingEntity entity) {
        if (!(entity instanceof net.minecraft.world.entity.player.Player player)) {
            return;
        }
        
        // Apply ToughAsNails temperature effect (30 seconds, WARM)
        if (ToughAsNailsIntegration.isToughAsNailsLoaded()) {
            BathWaterBottleTANModifier.applySplashWarmEffect(player);
        }
        
        // Apply Cold Sweat temperature effect (10 seconds, 36°C)
        if (ColdSweatIntegration.isColdSweatLoaded()) {
            BathWaterBottleColdSweatModifier.applySplashWarmEffect(player);
        }
        
        // Apply Legendary Survival Overhaul temperature effect (10 seconds, Cold Resistance II)
        if (LegendarySurvivalOverhaulIntegration.isLSOLoaded()) {
            BathWaterBottleLSOModifier.applySplashWarmEffect(player);
        }
    }

    /**
     * Apply only temperature effects (no potion effects).
     * Used when player drinks from bath water sources using ToughAsNails' hand drinking feature.
     */
    public static void applyTemperatureEffectsOnly(net.minecraft.world.entity.player.Player player) {
        // Apply ToughAsNails temperature effect (10 seconds, WARM)
        if (ToughAsNailsIntegration.isToughAsNailsLoaded()) {
            BathWaterBottleTANModifier.applyWarmEffect(player);
        }
        
        // Apply Cold Sweat temperature effect (20 seconds, 36°C)
        if (ColdSweatIntegration.isColdSweatLoaded()) {
            BathWaterBottleColdSweatModifier.applyWarmEffect(player);
        }
        
        // Apply Legendary Survival Overhaul temperature effect (5 seconds, 20.0)
        if (LegendarySurvivalOverhaulIntegration.isLSOLoaded()) {
            BathWaterBottleLSOModifier.applyWarmEffect(player);
        }
    }

    /**
     * Check if effect is harmful.
     * Uses the effect's category to determine if it's beneficial or harmful,
     * which provides better compatibility with modded effects.
     */
    private static boolean isHarmfulEffect(Holder<MobEffect> effectHolder) {
        MobEffect effect = effectHolder.value();
        // Use the effect's category - HARMFUL effects are negative effects
        // This automatically supports modded effects that properly set their category
        return !effect.isBeneficial() && effectHolder != MobEffects.UNLUCK;
    }
}
