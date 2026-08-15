package com.bmt.waypointfire.network;

import com.bmt.waypointfire.WaypointFireEquivalence;
import java.util.UUID;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;

public record WaypointDeltaPayload(
    Operation operation,
    UUID id,
    ResourceLocation style,
    boolean hasColor,
    int color,
    PositionMode mode,
    int x,
    int y,
    int z,
    float angleDegrees
) implements CustomPacketPayload {
    public static final Type<WaypointDeltaPayload> TYPE = new Type<>(
        ResourceLocation.fromNamespaceAndPath(WaypointFireEquivalence.MOD_ID, "waypoint_delta")
    );
    public static final StreamCodec<RegistryFriendlyByteBuf, WaypointDeltaPayload> STREAM_CODEC = StreamCodec.ofMember(
        WaypointDeltaPayload::write,
        WaypointDeltaPayload::new
    );

    public WaypointDeltaPayload(RegistryFriendlyByteBuf buffer) {
        this(
            buffer.readEnum(Operation.class),
            buffer.readUUID(),
            buffer.readResourceLocation(),
            buffer.readBoolean(),
            buffer.readInt(),
            buffer.readEnum(PositionMode.class),
            buffer.readInt(),
            buffer.readInt(),
            buffer.readInt(),
            buffer.readFloat()
        );
    }

    private void write(RegistryFriendlyByteBuf buffer) {
        buffer.writeEnum(operation);
        buffer.writeUUID(id);
        buffer.writeResourceLocation(style);
        buffer.writeBoolean(hasColor);
        buffer.writeInt(color);
        buffer.writeEnum(mode);
        buffer.writeInt(x);
        buffer.writeInt(y);
        buffer.writeInt(z);
        buffer.writeFloat(angleDegrees);
    }

    public static WaypointDeltaPayload remove(UUID id) {
        return new WaypointDeltaPayload(
            Operation.REMOVE,
            id,
            ResourceLocation.withDefaultNamespace("default"),
            false,
            0,
            PositionMode.EXACT,
            0,
            0,
            0,
            0.0F
        );
    }

    @Override
    public Type<? extends CustomPacketPayload> type() {
        return TYPE;
    }

    public enum Operation {
        ADD,
        UPDATE,
        REMOVE,
        CLEAR
    }

    public enum PositionMode {
        EXACT,
        CHUNK,
        ANGLE
    }
}
