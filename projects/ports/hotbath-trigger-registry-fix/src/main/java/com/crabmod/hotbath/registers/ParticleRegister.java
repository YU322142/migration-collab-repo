package com.crabmod.hotbath.registers;

import com.crabmod.hotbath.HotBath;
import net.minecraft.core.particles.ParticleType;
import net.minecraft.core.particles.SimpleParticleType;
import net.minecraft.core.registries.BuiltInRegistries;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public class ParticleRegister {
    public static final DeferredRegister<ParticleType<?>> PARTICLE_TYPES =
            DeferredRegister.create(BuiltInRegistries.PARTICLE_TYPE, HotBath.MOD_ID);

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> STEAM_PARTICLE =
            PARTICLE_TYPES.register("steam_particle", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> HOT_WATER_SPLASH =
            PARTICLE_TYPES.register("hot_water_splash", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> HONEY_WATER_SPLASH =
            PARTICLE_TYPES.register("honey_water_splash", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> MILK_WATER_SPLASH =
            PARTICLE_TYPES.register("milk_water_splash", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> HERBAL_WATER_SPLASH =
            PARTICLE_TYPES.register("herbal_water_splash", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> PEONY_WATER_SPLASH =
            PARTICLE_TYPES.register("peony_water_splash", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> ROSE_WATER_SPLASH =
            PARTICLE_TYPES.register("rose_water_splash", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> HOT_WATER_EFFECT =
            PARTICLE_TYPES.register("hot_water_effect", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> HONEY_BATH_EFFECT =
            PARTICLE_TYPES.register("honey_bath_effect", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> MILK_BATH_EFFECT =
            PARTICLE_TYPES.register("milk_bath_effect", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> HERBAL_BATH_EFFECT =
            PARTICLE_TYPES.register("herbal_bath_effect", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> PEONY_BATH_EFFECT =
            PARTICLE_TYPES.register("peony_bath_effect", () -> new SimpleParticleType(true));

    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> ROSE_BATH_EFFECT =
            PARTICLE_TYPES.register("rose_bath_effect", () -> new SimpleParticleType(true));

    // Bubbles
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> HOT_WATER_BUBBLE =
            PARTICLE_TYPES.register("hot_water_bubble", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> HONEY_BATH_BUBBLE =
            PARTICLE_TYPES.register("honey_bath_bubble", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> MILK_BATH_BUBBLE =
            PARTICLE_TYPES.register("milk_bath_bubble", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> HERBAL_BATH_BUBBLE =
            PARTICLE_TYPES.register("herbal_bath_bubble", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> PEONY_BATH_BUBBLE =
            PARTICLE_TYPES.register("peony_bath_bubble", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> ROSE_BATH_BUBBLE =
            PARTICLE_TYPES.register("rose_bath_bubble", () -> new SimpleParticleType(false));

    // Dripping (Hanging)
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> DRIPPING_HOT_WATER =
            PARTICLE_TYPES.register("dripping_hot_water", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> DRIPPING_HONEY_BATH =
            PARTICLE_TYPES.register("dripping_honey_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> DRIPPING_MILK_BATH =
            PARTICLE_TYPES.register("dripping_milk_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> DRIPPING_HERBAL_BATH =
            PARTICLE_TYPES.register("dripping_herbal_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> DRIPPING_PEONY_BATH =
            PARTICLE_TYPES.register("dripping_peony_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> DRIPPING_ROSE_BATH =
            PARTICLE_TYPES.register("dripping_rose_bath", () -> new SimpleParticleType(false));

    // Falling
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> FALLING_HOT_WATER =
            PARTICLE_TYPES.register("falling_hot_water", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> FALLING_HONEY_BATH =
            PARTICLE_TYPES.register("falling_honey_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> FALLING_MILK_BATH =
            PARTICLE_TYPES.register("falling_milk_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> FALLING_HERBAL_BATH =
            PARTICLE_TYPES.register("falling_herbal_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> FALLING_PEONY_BATH =
            PARTICLE_TYPES.register("falling_peony_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> FALLING_ROSE_BATH =
            PARTICLE_TYPES.register("falling_rose_bath", () -> new SimpleParticleType(false));

    // Landing
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> LANDING_HOT_WATER =
            PARTICLE_TYPES.register("landing_hot_water", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> LANDING_HONEY_BATH =
            PARTICLE_TYPES.register("landing_honey_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> LANDING_MILK_BATH =
            PARTICLE_TYPES.register("landing_milk_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> LANDING_HERBAL_BATH =
            PARTICLE_TYPES.register("landing_herbal_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> LANDING_PEONY_BATH =
            PARTICLE_TYPES.register("landing_peony_bath", () -> new SimpleParticleType(false));
    public static final DeferredHolder<ParticleType<?>, SimpleParticleType> LANDING_ROSE_BATH =
            PARTICLE_TYPES.register("landing_rose_bath", () -> new SimpleParticleType(false));

    public static void register(IEventBus eventBus) {
        PARTICLE_TYPES.register(eventBus);
    }
}
