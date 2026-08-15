package com.crabmod.hotbath.fluid_details;

import com.crabmod.hotbath.HotBath;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.world.level.material.Fluid;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.common.SoundActions;
import net.neoforged.neoforge.fluids.FluidType;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;
import net.neoforged.neoforge.registries.NeoForgeRegistries;

import java.util.function.Supplier;

import static com.crabmod.hotbath.fluid_details.FluidsColor.DEFAULT_FOG_COLOR;

public class HotbathFluidType {
    public static final ResourceLocation WATER_STILL_RL = ResourceLocation.parse("block/water_still");
    public static final ResourceLocation WATER_FLOWING_RL =
            ResourceLocation.parse("block/water_flow");
    public static final ResourceLocation WATER_OVERLAY_RL =
            ResourceLocation.parse("block/water_overlay");

    public static final DeferredRegister<FluidType> FLUID_TYPES =
            DeferredRegister.create(NeoForgeRegistries.Keys.FLUID_TYPES, HotBath.MOD_ID);

    public static DeferredHolder<FluidType, FluidType> getHotBathFluidType(
            String name,
            int color,
            ResourceLocation STILL_RL_TEXTURE,
            ResourceLocation FLOWING_RL_TEXTURE,
            Supplier<? extends ParticleOptions> dripParticle,
            Supplier<? extends ParticleOptions> bubbleParticle,
            Supplier<? extends ParticleOptions> splashParticle,
            Supplier<? extends Fluid> fluidSupplier) {
        return register(
                name,
                FluidType.Properties.create()
                        .lightLevel(2)
                        .density(15)
                        .viscosity(5)
                        .canExtinguish(true)
                        .supportsBoating(true)
                        .fallDistanceModifier(0.0F)
                        .canDrown(true)
                        .canSwim(true)
                        .sound(SoundActions.BUCKET_FILL, SoundEvents.BUCKET_FILL)
                        .sound(SoundActions.BUCKET_EMPTY, SoundEvents.BUCKET_EMPTY)
                        .sound(SoundActions.FLUID_VAPORIZE, SoundEvents.FIRE_EXTINGUISH)
                        .canHydrate(true),
                color,
                STILL_RL_TEXTURE,
                FLOWING_RL_TEXTURE,
                dripParticle,
                bubbleParticle,
                splashParticle,
                (Supplier<Fluid>) fluidSupplier);
    }

    private static DeferredHolder<FluidType, FluidType> register(
            String name,
            FluidType.Properties properties,
            int FLUID_COLOR,
            ResourceLocation STILL_RL_TEXTURE,
            ResourceLocation FLOWING_RL_TEXTURE,
            Supplier<? extends ParticleOptions> dripParticle,
            Supplier<? extends ParticleOptions> bubbleParticle,
            Supplier<? extends ParticleOptions> splashParticle,
            Supplier<Fluid> fluidSupplier) {
        return FLUID_TYPES.register(
                name,
                () ->
                        new BaseFluidType(
                                STILL_RL_TEXTURE,
                                FLOWING_RL_TEXTURE,
                                WATER_OVERLAY_RL,
                                FLUID_COLOR,
                                DEFAULT_FOG_COLOR,
                                properties,
                                dripParticle,
                                bubbleParticle,
                                splashParticle,
                                fluidSupplier));
    }

    public static void register(IEventBus eventBus) {
        FLUID_TYPES.register(eventBus);
    }
}
