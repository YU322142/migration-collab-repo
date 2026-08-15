package com.crabmod.hotbath.util;

import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;

public class ResistanceBoostHandler {
    public static void applyResistanceBoost(int secondPerBoost, ServerPlayer player) {
        int duration = 20 * secondPerBoost;
        int amplifier = 0;
        boolean ambient = false;
        boolean showParticles = true;

        MobEffectInstance resistanceEffect =
                new MobEffectInstance(
                        MobEffects.DAMAGE_RESISTANCE, duration, amplifier, ambient, showParticles);
        player.addEffect(resistanceEffect);
    }
}
