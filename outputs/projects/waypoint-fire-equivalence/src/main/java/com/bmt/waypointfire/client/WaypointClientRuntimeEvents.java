package com.bmt.waypointfire.client;

import com.bmt.waypointfire.WaypointFireEquivalence;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.ClientPlayerNetworkEvent;

@EventBusSubscriber(modid = WaypointFireEquivalence.MOD_ID, bus = EventBusSubscriber.Bus.GAME, value = Dist.CLIENT)
public final class WaypointClientRuntimeEvents {
    private WaypointClientRuntimeEvents() {}

    @SubscribeEvent
    public static void loggingOut(ClientPlayerNetworkEvent.LoggingOut event) {
        ClientWaypointState.clear();
    }
}
