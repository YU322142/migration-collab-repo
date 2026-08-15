package com.crabmod.hotbath.compat;

import net.neoforged.neoforge.common.NeoForge;

public class LSOCompat {
    public static void init() {
        NeoForge.EVENT_BUS.register(LSOEventHandler.class);
        NeoForge.EVENT_BUS.register(LSOThirstHandler.class);
    }
}
