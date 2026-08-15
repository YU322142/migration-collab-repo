package com.bmt.kaleidoscope_nether.migration;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.material.Fluid;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.fluids.BaseFlowingFluid;
import net.neoforged.neoforge.fluids.FluidType;
import net.neoforged.neoforge.registries.DeferredRegister;
import net.neoforged.neoforge.registries.NeoForgeRegistries;

import java.util.function.Supplier;

public final class NetherJuiceFluids {
    private static final String NAMESPACE = KaleidoscopeNetherEquivalence.NETHER_ID;
    private static final DeferredRegister<FluidType> FLUID_TYPES =
            DeferredRegister.create(NeoForgeRegistries.FLUID_TYPES, NAMESPACE);
    private static final DeferredRegister<Fluid> FLUIDS =
            DeferredRegister.create(BuiltInRegistries.FLUID, NAMESPACE);

    private static final ResourceLocation WARPED_ID = KaleidoscopeNetherEquivalence.netherId("warped_juice");
    private static final ResourceLocation CRIMSON_ID = KaleidoscopeNetherEquivalence.netherId("crimson_juice");

    private static final Supplier<FluidType> WARPED_TYPE = FLUID_TYPES.register("warped_juice",
            () -> new NetherJuiceFluidType(WARPED_ID));
    private static final Supplier<FluidType> CRIMSON_TYPE = FLUID_TYPES.register("crimson_juice",
            () -> new NetherJuiceFluidType(CRIMSON_ID));

    private static final Supplier<BaseFlowingFluid.Source> WARPED = FLUIDS.register("warped_juice",
            () -> new BaseFlowingFluid.Source(warpedProperties()));
    private static final Supplier<BaseFlowingFluid.Flowing> FLOWING_WARPED = FLUIDS.register("flowing_warped_juice",
            () -> new BaseFlowingFluid.Flowing(warpedProperties()));
    private static final Supplier<BaseFlowingFluid.Source> CRIMSON = FLUIDS.register("crimson_juice",
            () -> new BaseFlowingFluid.Source(crimsonProperties()));
    private static final Supplier<BaseFlowingFluid.Flowing> FLOWING_CRIMSON = FLUIDS.register("flowing_crimson_juice",
            () -> new BaseFlowingFluid.Flowing(crimsonProperties()));

    private NetherJuiceFluids() {
    }

    public static void register(IEventBus modBus) {
        FLUID_TYPES.register(modBus);
        FLUIDS.register(modBus);
    }

    private static BaseFlowingFluid.Properties warpedProperties() {
        return new BaseFlowingFluid.Properties(WARPED_TYPE, WARPED, FLOWING_WARPED)
                .slopeFindDistance(4)
                .levelDecreasePerBlock(1)
                .tickRate(20);
    }

    private static BaseFlowingFluid.Properties crimsonProperties() {
        return new BaseFlowingFluid.Properties(CRIMSON_TYPE, CRIMSON, FLOWING_CRIMSON)
                .slopeFindDistance(4)
                .levelDecreasePerBlock(1)
                .tickRate(20);
    }
}
