package com.github.ysbbbbbb.kaleidoscopecookery.init;

import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
import com.google.common.collect.ImmutableSet;
import net.minecraft.world.entity.ai.village.poi.PoiType;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;

public class ModPoi {
    public static final DeferredRegister<PoiType> POI_TYPES = DeferredRegister.create(ForgeRegistries.POI_TYPES, KaleidoscopeCookery.MOD_ID);

    public static final RegistryObject<PoiType> STOVE = POI_TYPES.register("stove",
            () -> new PoiType(ImmutableSet.copyOf(
                    ModBlocks.STOVE.get()
                            .getStateDefinition()
                            .getPossibleStates()
            ), 1, 1));

    public static final RegistryObject<PoiType> POT = POI_TYPES.register("pot",
            () -> new PoiType(ImmutableSet.copyOf(
                    ModBlocks.POT.get()
                            .getStateDefinition()
                            .getPossibleStates()
            ), 1, 1));

    public static final RegistryObject<PoiType> STOCKPOT = POI_TYPES.register("stockpot",
            () -> new PoiType(ImmutableSet.copyOf(
                    ModBlocks.STOCKPOT.get()
                            .getStateDefinition()
                            .getPossibleStates()
            ), 1, 1));

    public static final RegistryObject<PoiType> CHOPPING_BOARD = POI_TYPES.register("chopping_board",
            () -> new PoiType(ImmutableSet.copyOf(
                    ModBlocks.CHOPPING_BOARD.get()
                            .getStateDefinition()
                            .getPossibleStates()
            ), 1, 1));
}
