package com.crabmod.hotbath.util;

import net.minecraft.core.Holder;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.effect.MobEffectCategory;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;

import java.util.ArrayList;
import java.util.List;

public class EffectRemovalHandler {
    public static void removeNegativeEffectsExceptUnluck(ServerPlayer player) {
        List<MobEffectInstance> activeEffects = new ArrayList<>(player.getActiveEffects());

        for (MobEffectInstance effectInstance : activeEffects) {
            Holder<MobEffect> effectHolder = effectInstance.getEffect();

            if (isHarmfulEffect(effectHolder) && effectHolder != MobEffects.UNLUCK) {
                player.removeEffect(effectHolder);
            }
        }
    }

    private static boolean isHarmfulEffect(Holder<MobEffect> effect) {
        return effect.value().getCategory() == MobEffectCategory.HARMFUL && effect != MobEffects.BAD_OMEN;
    }

    public static void removeNegativeEffectsExceptSlowAndUnluck(ServerPlayer player) {
        List<MobEffectInstance> activeEffects = new ArrayList<>(player.getActiveEffects());

        for (MobEffectInstance effectInstance : activeEffects) {
            Holder<MobEffect> effectHolder = effectInstance.getEffect();

            if (isHarmfulEffect(effectHolder)
                    && effectHolder != MobEffects.UNLUCK
                    && effectHolder != MobEffects.MOVEMENT_SLOWDOWN) {
                player.removeEffect(effectInstance.getEffect());
            }
        }
    }

    public static void removeNegativeEffects(ServerPlayer player) {
        List<MobEffectInstance> activeEffects = new ArrayList<>(player.getActiveEffects());

        for (MobEffectInstance effectInstance : activeEffects) {
            Holder<MobEffect> effectHolder = effectInstance.getEffect();

            if (isHarmfulEffect(effectHolder)) {
                player.removeEffect(effectInstance.getEffect());
            }
        }
    }

    public static void removeBadOmen(ServerPlayer player) {
        player.removeEffect(MobEffects.BAD_OMEN);
    }
}
