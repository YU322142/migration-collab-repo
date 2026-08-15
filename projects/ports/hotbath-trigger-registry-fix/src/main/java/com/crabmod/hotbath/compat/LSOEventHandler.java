package com.crabmod.hotbath.compat;

import com.crabmod.hotbath.HotBath;
import net.minecraft.world.entity.player.Player;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.neoforge.event.tick.PlayerTickEvent;

/**
 * Event handler for Legendary Survival Overhaul integration.
 * Handles tick-based updates for temperature modifiers.
 */
public class LSOEventHandler {

    @SubscribeEvent
    public static void onPlayerTick(PlayerTickEvent.Post event) {
        Player player = event.getEntity();
        
        // Only process on server side
        if (player.level().isClientSide()) {
            return;
        }

        // Tick the immersion modifier to apply/remove hot bath effects
        HotBathImmersionLSOModifier.tick(player);
    }
}
