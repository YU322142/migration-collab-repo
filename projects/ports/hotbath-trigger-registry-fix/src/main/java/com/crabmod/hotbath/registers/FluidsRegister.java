package com.crabmod.hotbath.registers;

import com.crabmod.hotbath.HotBath;
import com.crabmod.hotbath.fluid_blocks.HerbalBathBlock;
import com.crabmod.hotbath.fluid_blocks.HoneyBathBlock;
import com.crabmod.hotbath.fluid_blocks.HotWaterBlock;
import com.crabmod.hotbath.fluid_blocks.MilkBathBlock;
import com.crabmod.hotbath.fluid_blocks.PeonyBathBlock;
import com.crabmod.hotbath.fluid_blocks.RoseBathBlock;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.material.FlowingFluid;
import net.minecraft.world.level.material.Fluid;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.fluids.BaseFlowingFluid;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

import static com.crabmod.hotbath.fluid_details.FluidsColor.HERBAL_BATH_COLOR;
import static com.crabmod.hotbath.fluid_details.FluidsColor.HONEY_BATH_COLOR;
import static com.crabmod.hotbath.fluid_details.FluidsColor.HOT_WATER_COLOR;
import static com.crabmod.hotbath.fluid_details.FluidsColor.MILK_BATH_COLOR;
import static com.crabmod.hotbath.fluid_details.FluidsColor.PEONY_BATH_COLOR;
import static com.crabmod.hotbath.fluid_details.FluidsColor.ROSE_BATH_COLOR;
import static com.crabmod.hotbath.fluid_details.FluidsTexture.*;
import static com.crabmod.hotbath.fluid_details.HotbathFluidType.getHotBathFluidType;

/**
 * FluidsRegister
 */
public class FluidsRegister {
    public static final DeferredRegister<Fluid> FLUIDS =
            DeferredRegister.create(BuiltInRegistries.FLUID, HotBath.MOD_ID);

    public static final DeferredHolder<Fluid, FlowingFluid> HOT_WATER_FLUID =
            FLUIDS.register(
                    "hot_water_fluid",
                    () -> new BaseFlowingFluid.Source(FluidsRegister.HOT_WATER_PROPERTIES));
    public static final DeferredHolder<Fluid, FlowingFluid> HOT_WATER_FLOWING =
            FLUIDS.register(
                    "hot_water_flowing",
                    () -> new BaseFlowingFluid.Flowing(FluidsRegister.HOT_WATER_PROPERTIES));

    public static final DeferredHolder<Block, LiquidBlock> HOT_WATER_BLOCK =
            BlocksRegister.BLOCKS.register(
                    "hot_water_block",
                    () ->
                            new HotWaterBlock(
                                    HOT_WATER_FLUID,
                                    Block.Properties.ofFullCopy(Blocks.WATER)
                                            .noCollission()
                                            .strength(1000.0F)
                                            .noOcclusion()));

    public static final BaseFlowingFluid.Properties HOT_WATER_PROPERTIES =
            new BaseFlowingFluid.Properties(
                    getHotBathFluidType(
                            "hot_water_fluid_type",
                            HOT_WATER_COLOR,
                            HOT_WATER_STILL_TEXTURE,
                            HOT_WATER_FLOWING_TEXTURE,
                            ParticleRegister.DRIPPING_HOT_WATER,
                            ParticleRegister.HOT_WATER_BUBBLE,
                            ParticleRegister.HOT_WATER_SPLASH,
                            () -> HOT_WATER_FLUID.get()),
                    HOT_WATER_FLUID,
                    HOT_WATER_FLOWING)
                    .slopeFindDistance(2)
                    .levelDecreasePerBlock(2)
                    .block(HOT_WATER_BLOCK)
                    .bucket(ItemRegister.HOT_WATER_BUCKET);

    public static final DeferredHolder<Fluid, FlowingFluid> HONEY_BATH_FLUID =
            FLUIDS.register(
                    "honey_bath_fluid",
                    () -> new BaseFlowingFluid.Source(FluidsRegister.HONEY_BATH_PROPERTIES));

    public static final DeferredHolder<Fluid, FlowingFluid> HONEY_BATH_FLOWING =
            FLUIDS.register(
                    "honey_bath_flowing",
                    () -> new BaseFlowingFluid.Flowing(FluidsRegister.HONEY_BATH_PROPERTIES));

    public static final DeferredHolder<Block, LiquidBlock> HONEY_BATH_BLOCK =
            BlocksRegister.BLOCKS.register(
                    "honey_bath_block",
                    () ->
                            new HoneyBathBlock(
                                    HONEY_BATH_FLUID,
                                    Block.Properties.ofFullCopy(Blocks.WATER)
                                            .noCollission()
                                            .strength(1000.0F)
                                            .noOcclusion()));

    public static final BaseFlowingFluid.Properties HONEY_BATH_PROPERTIES =
            new BaseFlowingFluid.Properties(
                    getHotBathFluidType(
                            "honey_bath_fluid_type",
                            HONEY_BATH_COLOR,
                            HONEY_BATH_STILL_TEXTURE,
                            HONEY_BATH_FLOWING_TEXTURE,
                            ParticleRegister.DRIPPING_HONEY_BATH,
                            ParticleRegister.HONEY_BATH_BUBBLE,
                            ParticleRegister.HONEY_WATER_SPLASH,
                            () -> HONEY_BATH_FLUID.get()),
                    HONEY_BATH_FLUID,
                    HONEY_BATH_FLOWING)
                    .slopeFindDistance(2)
                    .levelDecreasePerBlock(2)
                    .block(HONEY_BATH_BLOCK)
                    .bucket(ItemRegister.HONEY_BATH_BUCKET);

    public static final DeferredHolder<Fluid, FlowingFluid> MILK_BATH_FLUID =
            FLUIDS.register(
                    "milk_bath_fluid",
                    () -> new BaseFlowingFluid.Source(FluidsRegister.MILK_BATH_PROPERTIES));

    public static final DeferredHolder<Fluid, FlowingFluid> MILK_BATH_FLOWING =
            FLUIDS.register(
                    "milk_bath_flowing",
                    () -> new BaseFlowingFluid.Flowing(FluidsRegister.MILK_BATH_PROPERTIES));

    public static final DeferredHolder<Block, LiquidBlock> MILK_BATH_BLOCK =
            BlocksRegister.BLOCKS.register(
                    "milk_bath_block",
                    () ->
                            new MilkBathBlock(
                                    MILK_BATH_FLUID,
                                    Block.Properties.ofFullCopy(Blocks.WATER)
                                            .noCollission()
                                            .strength(1000.0F)
                                            .noOcclusion()));
    public static final BaseFlowingFluid.Properties MILK_BATH_PROPERTIES =
            new BaseFlowingFluid.Properties(
                    getHotBathFluidType(
                            "milk_bath_fluid_type",
                            MILK_BATH_COLOR,
                            MILK_BATH_STILL_TEXTURE,
                            MILK_BATH_FLOWING_TEXTURE,
                            ParticleRegister.DRIPPING_MILK_BATH,
                            ParticleRegister.MILK_BATH_BUBBLE,
                            ParticleRegister.MILK_WATER_SPLASH,
                            () -> MILK_BATH_FLUID.get()),
                    MILK_BATH_FLUID,
                    MILK_BATH_FLOWING)
                    .slopeFindDistance(2)
                    .levelDecreasePerBlock(2)
                    .block(MILK_BATH_BLOCK)
                    .bucket(ItemRegister.MILK_BATH_BUCKET);

    public static final DeferredHolder<Fluid, FlowingFluid> HERBAL_BATH_FLUID =
            FLUIDS.register(
                    "herbal_bath_fluid",
                    () -> new BaseFlowingFluid.Source(FluidsRegister.HERBAL_BATH_PROPERTIES));

    public static final DeferredHolder<Fluid, FlowingFluid> HERBAL_BATH_FLOWING =
            FLUIDS.register(
                    "herbal_bath_flowing",
                    () -> new BaseFlowingFluid.Flowing(FluidsRegister.HERBAL_BATH_PROPERTIES));
    public static final DeferredHolder<Block, LiquidBlock> HERBAL_BATH_BLOCK =
            BlocksRegister.BLOCKS.register(
                    "herbal_bath_block",
                    () ->
                            new HerbalBathBlock(
                                    HERBAL_BATH_FLUID,
                                    Block.Properties.ofFullCopy(Blocks.WATER)
                                            .noCollission()
                                            .strength(1000.0F)
                                            .noOcclusion()));

    public static final BaseFlowingFluid.Properties HERBAL_BATH_PROPERTIES =
            new BaseFlowingFluid.Properties(
                    getHotBathFluidType(
                            "herbal_bath_fluid_type",
                            HERBAL_BATH_COLOR,
                            HERBAL_BATH_STILL_TEXTURE,
                            HERBAL_BATH_FLOWING_TEXTURE,
                            ParticleRegister.DRIPPING_HERBAL_BATH,
                            ParticleRegister.HERBAL_BATH_BUBBLE,
                            ParticleRegister.HERBAL_WATER_SPLASH,
                            () -> HERBAL_BATH_FLUID.get()),
                    HERBAL_BATH_FLUID,
                    HERBAL_BATH_FLOWING)
                    .slopeFindDistance(2)
                    .levelDecreasePerBlock(2)
                    .block(HERBAL_BATH_BLOCK)
                    .bucket(ItemRegister.HERBAL_BATH_BUCKET);

    public static final DeferredHolder<Fluid, FlowingFluid> PEONY_BATH_FLUID =
            FLUIDS.register(
                    "peony_bath_fluid",
                    () -> new BaseFlowingFluid.Source(FluidsRegister.PEONY_BATH_PROPERTIES));

    public static final DeferredHolder<Fluid, FlowingFluid> PEONY_BATH_FLOWING =
            FLUIDS.register(
                    "peony_bath_flowing",
                    () -> new BaseFlowingFluid.Flowing(FluidsRegister.PEONY_BATH_PROPERTIES));

    public static final DeferredHolder<Block, LiquidBlock> PEONY_BATH_BLOCK =
            BlocksRegister.BLOCKS.register(
                    "peony_bath_block",
                    () ->
                            new PeonyBathBlock(
                                    PEONY_BATH_FLUID,
                                    Block.Properties.ofFullCopy(Blocks.WATER)
                                            .noCollission()
                                            .strength(1000.0F)
                                            .noOcclusion()));

    public static final BaseFlowingFluid.Properties PEONY_BATH_PROPERTIES =
            new BaseFlowingFluid.Properties(
                    getHotBathFluidType(
                            "peony_bath_fluid_type",
                            PEONY_BATH_COLOR,
                            PEONY_BATH_STILL_TEXTURE,
                            PEONY_BATH_FLOWING_TEXTURE,
                            ParticleRegister.DRIPPING_PEONY_BATH,
                            ParticleRegister.PEONY_BATH_BUBBLE,
                            ParticleRegister.PEONY_WATER_SPLASH,
                            () -> PEONY_BATH_FLUID.get()),
                    PEONY_BATH_FLUID,
                    PEONY_BATH_FLOWING)
                    .slopeFindDistance(2)
                    .levelDecreasePerBlock(2)
                    .block(PEONY_BATH_BLOCK)
                    .bucket(ItemRegister.PEONY_BATH_BUCKET);

    public static final DeferredHolder<Fluid, FlowingFluid> ROSE_BATH_FLUID =
            FLUIDS.register(
                    "rose_bath_fluid",
                    () -> new BaseFlowingFluid.Source(FluidsRegister.ROSE_BATH_PROPERTIES));

    public static final DeferredHolder<Fluid, FlowingFluid> ROSE_BATH_FLOWING =
            FLUIDS.register(
                    "rose_bath_flowing",
                    () -> new BaseFlowingFluid.Flowing(FluidsRegister.ROSE_BATH_PROPERTIES));

    public static final DeferredHolder<Block, LiquidBlock> ROSE_BATH_BLOCK =
            BlocksRegister.BLOCKS.register(
                    "rose_bath_block",
                    () ->
                            new RoseBathBlock(
                                    ROSE_BATH_FLUID,
                                    Block.Properties.ofFullCopy(Blocks.WATER)
                                            .noCollission()
                                            .strength(1000.0F)
                                            .noOcclusion()));

    public static final BaseFlowingFluid.Properties ROSE_BATH_PROPERTIES =
            new BaseFlowingFluid.Properties(
                    getHotBathFluidType(
                            "rose_bath_fluid_type",
                            ROSE_BATH_COLOR,
                            ROSE_BATH_STILL_TEXTURE,
                            ROSE_BATH_FLOWING_TEXTURE,
                            ParticleRegister.DRIPPING_ROSE_BATH,
                            ParticleRegister.ROSE_BATH_BUBBLE,
                            ParticleRegister.ROSE_WATER_SPLASH,
                            () -> ROSE_BATH_FLUID.get()),
                    ROSE_BATH_FLUID,
                    ROSE_BATH_FLOWING)
                    .slopeFindDistance(2)
                    .levelDecreasePerBlock(2)
                    .block(ROSE_BATH_BLOCK)
                    .bucket(ItemRegister.ROSE_BATH_BUCKET);

    public static void register(IEventBus eventBus) {
        FLUIDS.register(eventBus);
    }
}
