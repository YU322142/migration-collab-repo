package com.bmt.waypointfire.server;

import com.bmt.waypointfire.CompatGameRules;
import com.bmt.waypointfire.ParitySemantics;
import com.bmt.waypointfire.WaypointFireEquivalence;
import com.bmt.waypointfire.WaypointIcon;
import com.bmt.waypointfire.WaypointIconCarrier;
import com.bmt.waypointfire.network.WaypointDeltaPayload;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.OptionalInt;
import java.util.Set;
import java.util.UUID;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.phys.Vec3;
import net.neoforged.neoforge.network.PacketDistributor;

public final class WaypointManager {
    private static final double ANGLE_ONLY_DISTANCE = 332.0;
    private static final double ANGLE_UPDATE_THRESHOLD_DEGREES = 0.5;
    private static final Map<ResourceKey<Level>, Set<LivingEntity>> TRACKED = new HashMap<>();
    private static final Map<UUID, Map<UUID, SentWaypoint>> SENT = new HashMap<>();

    private WaypointManager() {}

    public static void entityJoined(Entity entity, Level level) {
        if (!level.isClientSide() && entity instanceof LivingEntity living && hasTransmitRange(living)) {
            track(living);
        }
    }

    public static void entityLeft(Entity entity, Level level) {
        if (!level.isClientSide() && entity instanceof LivingEntity living) {
            Set<LivingEntity> entities = TRACKED.get(level.dimension());
            if (entities != null) {
                entities.remove(living);
            }
        }
    }

    public static void transmitRangeChanged(LivingEntity entity) {
        if (entity.level().isClientSide()) {
            return;
        }
        if (hasTransmitRange(entity)) {
            track(entity);
        } else {
            Set<LivingEntity> entities = TRACKED.get(entity.level().dimension());
            if (entities != null) {
                entities.remove(entity);
            }
        }
    }

    public static void tick(MinecraftServer server) {
        Set<UUID> online = new HashSet<>();
        for (ServerPlayer receiver : server.getPlayerList().getPlayers()) {
            online.add(receiver.getUUID());
            updateReceiver(receiver);
        }
        SENT.keySet().removeIf(id -> !online.contains(id));
        purgeRemovedEntities();
    }

    public static void clear() {
        TRACKED.clear();
        SENT.clear();
    }

    public static Set<LivingEntity> activeIn(ServerLevel level) {
        Set<LivingEntity> active = new HashSet<>();
        for (LivingEntity entity : TRACKED.getOrDefault(level.dimension(), Set.of())) {
            if (isTransmitting(entity)) {
                active.add(entity);
            }
        }
        return active;
    }

    public static void iconChanged(LivingEntity entity) {
        if (entity.level() instanceof ServerLevel level) {
            for (ServerPlayer receiver : level.players()) {
                Map<UUID, SentWaypoint> receiverState = SENT.get(receiver.getUUID());
                if (receiverState != null) {
                    receiverState.remove(entity.getUUID());
                }
            }
        }
    }

    private static void updateReceiver(ServerPlayer receiver) {
        Map<UUID, SentWaypoint> previous = SENT.computeIfAbsent(receiver.getUUID(), ignored -> new HashMap<>());
        Map<UUID, SentWaypoint> desired = new HashMap<>();

        if (!receiver.serverLevel().getGameRules().getBoolean(CompatGameRules.LOCATOR_BAR)
            || (!receiver.isSpectator() && effectiveReceiveRange(receiver) <= 0.0)) {
            clearReceiver(receiver, previous);
            return;
        }

        for (LivingEntity transmitter : TRACKED.getOrDefault(receiver.level().dimension(), Set.of())) {
            if (!isVisibleTo(transmitter, receiver)) {
                continue;
            }
            SentWaypoint old = previous.get(transmitter.getUUID());
            SentWaypoint next = describe(transmitter, receiver, old);
            desired.put(transmitter.getUUID(), next);
            if (old == null) {
                PacketDistributor.sendToPlayer(receiver, next.toPayload(WaypointDeltaPayload.Operation.ADD));
            } else if (!old.equals(next)) {
                PacketDistributor.sendToPlayer(receiver, next.toPayload(WaypointDeltaPayload.Operation.UPDATE));
            }
        }

        for (UUID removed : difference(previous.keySet(), desired.keySet())) {
            PacketDistributor.sendToPlayer(receiver, WaypointDeltaPayload.remove(removed));
        }
        previous.clear();
        previous.putAll(desired);
    }

    private static boolean isVisibleTo(LivingEntity transmitter, ServerPlayer receiver) {
        if (transmitter == receiver || transmitter.isRemoved() || !transmitter.isAlive()) {
            return false;
        }
        double transmit = effectiveTransmitRange(transmitter);
        double receive = effectiveReceiveRange(receiver);
        return ParitySemantics.waypointVisible(
            receiver.isSpectator(),
            transmitter.isSpectator(),
            transmitter.isInvisibleTo(receiver),
            transmit,
            receive,
            transmitter.distanceTo(receiver)
        );
    }

    private static boolean isTransmitting(LivingEntity entity) {
        return !entity.isRemoved() && entity.isAlive() && effectiveTransmitRange(entity) > 0.0;
    }

    private static double effectiveTransmitRange(LivingEntity entity) {
        if (entity.hasEffect(MobEffects.INVISIBILITY)
            || (entity instanceof ServerPlayer player && player.isCrouching())) {
            return 0.0;
        }
        return entity.getAttributeValue(WaypointFireEquivalence.WAYPOINT_TRANSMIT_RANGE);
    }

    private static double effectiveReceiveRange(ServerPlayer player) {
        return player.getAttributeValue(WaypointFireEquivalence.WAYPOINT_RECEIVE_RANGE);
    }

    private static SentWaypoint describe(LivingEntity entity, ServerPlayer receiver, SentWaypoint old) {
        WaypointIcon icon = effectiveIcon(entity);
        double distance = entity.distanceTo(receiver);
        WaypointDeltaPayload.PositionMode mode;
        BlockPos pos = entity.blockPosition();
        float angle = bearingDegrees(receiver.position(), entity.position());

        if (distance > ANGLE_ONLY_DISTANCE) {
            mode = WaypointDeltaPayload.PositionMode.ANGLE;
            if (old != null && old.mode == mode && angularDifference(old.angleDegrees, angle) <= ANGLE_UPDATE_THRESHOLD_DEGREES) {
                angle = old.angleDegrees;
            }
            pos = BlockPos.ZERO;
        } else if (!receiver.getChunkTrackingView().contains(new ChunkPos(pos))) {
            mode = WaypointDeltaPayload.PositionMode.CHUNK;
            ChunkPos chunk = new ChunkPos(pos);
            pos = new BlockPos(chunk.getMiddleBlockX(), 0, chunk.getMiddleBlockZ());
            angle = 0.0F;
        } else {
            mode = WaypointDeltaPayload.PositionMode.EXACT;
            if (old != null && old.mode == mode && old.blockPosition().equals(pos)) {
                pos = old.blockPosition();
            }
            angle = 0.0F;
        }

        return new SentWaypoint(entity.getUUID(), icon, mode, pos.getX(), pos.getY(), pos.getZ(), angle);
    }

    private static float bearingDegrees(Vec3 from, Vec3 to) {
        double dx = to.x - from.x;
        double dz = to.z - from.z;
        return (float) Math.toDegrees(Math.atan2(-dx, dz));
    }

    private static double angularDifference(float left, float right) {
        double delta = Math.abs(left - right) % 360.0;
        return Math.min(delta, 360.0 - delta);
    }

    private static Set<UUID> difference(Set<UUID> left, Set<UUID> right) {
        Set<UUID> result = new HashSet<>(left);
        result.removeAll(right);
        return result;
    }

    private static void clearReceiver(ServerPlayer receiver, Map<UUID, SentWaypoint> previous) {
        if (!previous.isEmpty()) {
            PacketDistributor.sendToPlayer(receiver, new WaypointDeltaPayload(
                WaypointDeltaPayload.Operation.CLEAR,
                new UUID(0L, 0L),
                WaypointIcon.DEFAULT_STYLE,
                false,
                0,
                WaypointDeltaPayload.PositionMode.EXACT,
                0,
                0,
                0,
                0.0F
            ));
            previous.clear();
        }
    }

    private static void purgeRemovedEntities() {
        Iterator<Map.Entry<ResourceKey<Level>, Set<LivingEntity>>> levels = TRACKED.entrySet().iterator();
        while (levels.hasNext()) {
            Set<LivingEntity> entities = levels.next().getValue();
            entities.removeIf(entity -> entity.isRemoved() || !entity.isAlive());
            if (entities.isEmpty()) {
                levels.remove();
            }
        }
    }

    private static boolean hasTransmitRange(LivingEntity entity) {
        return entity.getAttributeValue(WaypointFireEquivalence.WAYPOINT_TRANSMIT_RANGE) > 0.0;
    }

    private static void track(LivingEntity entity) {
        TRACKED.computeIfAbsent(
            entity.level().dimension(),
            ignored -> java.util.Collections.newSetFromMap(new IdentityHashMap<>())
        ).add(entity);
    }

    private static WaypointIcon effectiveIcon(LivingEntity entity) {
        WaypointIcon stored = ((WaypointIconCarrier) entity).waypointFire$getIcon();
        if (stored.color().isPresent() || entity.getTeam() == null) {
            return stored;
        }
        Integer teamColor = entity.getTeam().getColor().getColor();
        if (teamColor == null) {
            return stored;
        }
        // Vanilla uses a visible dark gray instead of pure black on the locator HUD.
        int visibleColor = teamColor == 0 ? 0x303030 : teamColor;
        return new WaypointIcon(stored.style(), OptionalInt.of(visibleColor));
    }

    private record SentWaypoint(
        UUID id,
        WaypointIcon icon,
        WaypointDeltaPayload.PositionMode mode,
        int x,
        int y,
        int z,
        float angleDegrees
    ) {
        private BlockPos blockPosition() {
            return new BlockPos(x, y, z);
        }

        private WaypointDeltaPayload toPayload(WaypointDeltaPayload.Operation operation) {
            return new WaypointDeltaPayload(
                operation,
                id,
                icon.style(),
                icon.color().isPresent(),
                icon.color().orElse(0),
                mode,
                x,
                y,
                z,
                angleDegrees
            );
        }
    }
}
