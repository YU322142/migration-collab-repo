package com.bmt.waypointfire.client;

import com.bmt.waypointfire.WaypointFireEquivalence;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.RegisterGuiLayersEvent;

@EventBusSubscriber(modid = WaypointFireEquivalence.MOD_ID, bus = EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
public final class WaypointClientEvents {
    private WaypointClientEvents() {}

    @SubscribeEvent
    public static void registerGuiLayer(RegisterGuiLayersEvent event) {
        event.registerAboveAll(
            ResourceLocation.fromNamespaceAndPath(WaypointFireEquivalence.MOD_ID, "locator_bar"),
            WaypointHud::render
        );
    }
}
