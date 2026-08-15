package com.crabmod.hotbath.compat;

import net.neoforged.neoforge.common.NeoForge;

public class ColdSweatCompat {
    public static void init() {
        NeoForge.EVENT_BUS.register(ColdSweatEventHandler.class);
    }
}
