package com.bmt.happyghast_equivalence;

import net.neoforged.fml.common.Mod;
import net.neoforged.bus.api.IEventBus;

/** Common entry point. Behavior is isolated in registry hooks and mixins. */
@Mod(HappyGhastEquivalence.MOD_ID)
public final class HappyGhastEquivalence {
    public static final String MOD_ID = "happyghast_equivalence";

    public HappyGhastEquivalence(IEventBus modEventBus) {
        modEventBus.addListener(MigratedRideStats::register);
    }
}
