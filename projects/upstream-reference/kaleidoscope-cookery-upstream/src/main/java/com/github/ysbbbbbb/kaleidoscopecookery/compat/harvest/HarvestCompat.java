package com.github.ysbbbbbb.kaleidoscopecookery.compat.harvest;

import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.fml.ModList;

public class HarvestCompat {
    public static final String ID = "harvest_with_ease";

    public static void init() {
        ModList.get().getModContainerById(ID).ifPresent(modContainer ->
                MinecraftForge.EVENT_BUS.addListener(CropHarvestEvent::onHarvest));
    }
}
