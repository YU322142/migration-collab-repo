package com.crabmod.hotbath.compat;

import net.neoforged.fml.ModList;

/**
 * Integration with Tough As Nails mod
 */
public class ToughAsNailsIntegration {
    private static final String TAN_MOD_ID = "toughasnails";

    public static boolean isToughAsNailsLoaded() {
        return ModList.get().isLoaded(TAN_MOD_ID);
    }
}
