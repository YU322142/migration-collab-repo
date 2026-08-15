package com.bmt.waypointfire.client;

import com.bmt.waypointfire.network.WaypointDeltaPayload;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

public final class ClientWaypointState {
    private static final Map<UUID, WaypointDeltaPayload> WAYPOINTS = new HashMap<>();

    private ClientWaypointState() {}

    public static void apply(WaypointDeltaPayload payload) {
        switch (payload.operation()) {
            case ADD, UPDATE -> WAYPOINTS.put(payload.id(), payload);
            case REMOVE -> WAYPOINTS.remove(payload.id());
            case CLEAR -> WAYPOINTS.clear();
        }
    }

    public static void clear() {
        WAYPOINTS.clear();
    }

    static Iterable<WaypointDeltaPayload> entries() {
        return WAYPOINTS.values();
    }
}
