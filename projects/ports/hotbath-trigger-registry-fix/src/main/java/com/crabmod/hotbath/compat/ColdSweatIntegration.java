package com.crabmod.hotbath.compat;

import net.neoforged.fml.ModList;

/**
 * Integration with Cold Sweat mod
 */
public class ColdSweatIntegration {
    private static final String COLD_SWEAT_MOD_ID = "cold_sweat";

    public static boolean isColdSweatLoaded() {
        return ModList.get().isLoaded(COLD_SWEAT_MOD_ID);
    }
}
