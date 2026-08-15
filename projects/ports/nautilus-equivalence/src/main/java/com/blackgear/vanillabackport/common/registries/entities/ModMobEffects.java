package com.blackgear.vanillabackport.common.registries.entities;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.effect.MobEffectCategory;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModMobEffects {
    public static final DeferredRegister<MobEffect> EFFECTS =
        DeferredRegister.create(BuiltInRegistries.MOB_EFFECT, "minecraft");

    public static final DeferredHolder<MobEffect, MobEffect> BREATH_OF_THE_NAUTILUS =
        EFFECTS.register("breath_of_the_nautilus", NautilusBreathEffect::new);

    private ModMobEffects() {
    }

    private static final class NautilusBreathEffect extends MobEffect {
        private NautilusBreathEffect() {
            super(MobEffectCategory.BENEFICIAL, 0x00FFEE);
        }
    }
}
