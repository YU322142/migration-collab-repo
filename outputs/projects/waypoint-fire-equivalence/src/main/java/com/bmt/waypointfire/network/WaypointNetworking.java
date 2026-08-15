package com.bmt.waypointfire.network;

import com.bmt.waypointfire.client.ClientWaypointState;
import net.neoforged.neoforge.network.event.RegisterPayloadHandlersEvent;

public final class WaypointNetworking {
    private WaypointNetworking() {}

    public static void register(RegisterPayloadHandlersEvent event) {
        event.registrar("waypoint_fire_equivalence").versioned("1")
            .playToClient(
                WaypointDeltaPayload.TYPE,
                WaypointDeltaPayload.STREAM_CODEC,
                (payload, context) -> context.enqueueWork(() -> ClientWaypointState.apply(payload))
            );
    }
}
