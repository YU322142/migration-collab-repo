package org.xiyu.yee.xiyuslogin.manager;

import net.minecraft.core.NonNullList;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.protocol.game.ClientboundForgetLevelChunkPacket;
import net.minecraft.network.protocol.game.ClientboundContainerSetContentPacket;
import net.minecraft.network.protocol.game.ClientboundLevelChunkWithLightPacket;
import net.minecraft.network.protocol.game.ClientboundSetEntityMotionPacket;
import net.minecraft.network.protocol.game.ClientboundPlayerPositionPacket;
import net.minecraft.network.protocol.game.ClientboundSetChunkCacheCenterPacket;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.chunk.LevelChunkSection;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.phys.Vec3;
import org.xiyu.yee.xiyuslogin.Xiyuslogin;
import org.xiyu.yee.xiyuslogin.config.LoginText;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginConfig;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginLanguageConfig;

import java.util.EnumSet;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class FreezeManager {
    private static final int FAKE_TELEPORT_ID = -1;
    private static FreezeManager instance;
    private static final Map<UUID, FrozenPlayerData> frozenPlayers = new ConcurrentHashMap<>();
    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2);
    private MinecraftServer server;

    private FreezeManager() {
    }

    public static FreezeManager getInstance() {
        if (instance == null) {
            instance = new FreezeManager();
        }
        return instance;
    }

    public void setServer(MinecraftServer server) {
        this.server = server;
    }

    public void freezePlayer(UUID playerId) {
        if (frozenPlayers.containsKey(playerId)) {
            return;
        }

        FrozenPlayerData frozenData = new FrozenPlayerData(playerId);
        frozenPlayers.put(playerId, frozenData);

        ServerPlayer player = getPlayerById(playerId);
        if (player != null) {
            applyFrozenPlayerState(player, frozenData);
            syncFrozenClientView(player);
            applyFreezeEffects(player);
        }

        frozenData.effectTask = scheduler.scheduleAtFixedRate(() -> runOnServerThread(() -> {
            ServerPlayer onlinePlayer = getPlayerById(playerId);
            if (onlinePlayer != null && frozenPlayers.containsKey(playerId)) {
                applyFrozenPlayerState(onlinePlayer, frozenData);
                syncFrozenClientView(onlinePlayer);
                applyFreezeEffects(onlinePlayer);
            }
        }), 500, 500, TimeUnit.MILLISECONDS);

        frozenData.timeoutTask = scheduler.schedule(() -> runOnServerThread(() -> {
            if (frozenPlayers.containsKey(playerId)) {
                ServerPlayer timeoutPlayer = getPlayerById(playerId);
                if (timeoutPlayer != null) {
                    timeoutPlayer.connection.disconnect(LoginText.component(
                            XiyusLoginLanguageConfig.FREEZE_TIMEOUT,
                            "seconds", XiyusLoginConfig.FREEZE_DURATION.get()
                    ));
                }
                AuthManager.getInstance().setPlayerAuthenticated(playerId, false);
                unfreezePlayer(playerId);
            }
        }), XiyusLoginConfig.FREEZE_DURATION.get(), TimeUnit.SECONDS);

        Xiyuslogin.LOGGER.debug("Player {} frozen", playerId);
    }

    public void unfreezePlayer(UUID playerId) {
        FrozenPlayerData frozenData = frozenPlayers.remove(playerId);
        if (frozenData != null) {
            if (frozenData.effectTask != null && !frozenData.effectTask.isCancelled()) {
                frozenData.effectTask.cancel(false);
            }
            if (frozenData.timeoutTask != null && !frozenData.timeoutTask.isCancelled()) {
                frozenData.timeoutTask.cancel(false);
            }

            ServerPlayer player = getPlayerById(playerId);
            if (player != null) {
                restoreFrozenPlayerState(player, frozenData);
                removeAllEffects(player);
                syncActualInventoryView(player);
            }
            Xiyuslogin.LOGGER.debug("Player {} unfrozen", playerId);
        }
    }

    public static boolean isFrozen(UUID playerId) {
        return frozenPlayers.containsKey(playerId);
    }

    public void preventMovement(ServerPlayer player) {
        if (!isFrozen(player.getUUID())) {
            return;
        }

        player.connection.send(new ClientboundSetEntityMotionPacket(player.getId(), Vec3.ZERO));
        player.setDeltaMovement(Vec3.ZERO);
        player.hurtMarked = true;
        stabilizeUnauthenticatedPlayer(player);

        applyFreezeEffects(player);
        syncFrozenClientView(player);
    }

    public void stabilizeUnauthenticatedPlayer(ServerPlayer player) {
        if (XiyusLoginConfig.PROTECT_UNAUTHENTICATED_PLAYERS.get()) {
            player.clearFire();
        }

        if (XiyusLoginConfig.PROTECT_UNAUTHENTICATED_PLAYERS.get()
                || XiyusLoginConfig.LEGALIZE_UNAUTHENTICATED_FLOATING.get()) {
            player.resetFallDistance();
        }
    }

    public void syncFrozenClientView(ServerPlayer player) {
        syncFrozenInventoryView(player);
        syncFakeWorldView(player);
    }

    public void syncFrozenInventoryView(ServerPlayer player) {
        if (player == null) {
            return;
        }

        try {
            int slotCount = player.containerMenu.slots.size();
            NonNullList<ItemStack> emptyItems = NonNullList.withSize(slotCount, ItemStack.EMPTY);
            player.connection.send(new ClientboundContainerSetContentPacket(
                    player.containerMenu.containerId,
                    player.containerMenu.incrementStateId(),
                    emptyItems,
                    ItemStack.EMPTY
            ));
        } catch (Exception e) {
            Xiyuslogin.LOGGER.error("Failed to send empty inventory to player {}: {}",
                    player.getName().getString(), e.getMessage());
        }
    }

    private void syncFakeWorldView(ServerPlayer player) {
        XiyusLoginConfig.AuthViewMode mode = XiyusLoginConfig.AUTH_VIEW_MODE.get();
        if (mode == XiyusLoginConfig.AuthViewMode.INVENTORY_ONLY) {
            return;
        }

        double x = XiyusLoginConfig.FAKE_POSITION_X.get();
        double y = XiyusLoginConfig.FAKE_POSITION_Y.get();
        double z = XiyusLoginConfig.FAKE_POSITION_Z.get();
        player.connection.send(new ClientboundPlayerPositionPacket(
                x,
                y,
                z,
                player.getYRot(),
                player.getXRot(),
                java.util.Set.of(),
                FAKE_TELEPORT_ID
        ));

        int fakeChunkX = (int) Math.floor(x) >> 4;
        int fakeChunkZ = (int) Math.floor(z) >> 4;
        player.connection.send(new ClientboundSetChunkCacheCenterPacket(fakeChunkX, fakeChunkZ));

        if (mode == XiyusLoginConfig.AuthViewMode.FLAT_CHUNK) {
            sendFlatFakeChunks(player, fakeChunkX, fakeChunkZ);
        } else if (mode == XiyusLoginConfig.AuthViewMode.VOID_UNLOADED) {
            unloadRealChunksFromClient(player);
        }
    }

    private void sendFlatFakeChunks(ServerPlayer player, int centerChunkX, int centerChunkZ) {
        ServerLevel level = player.serverLevel();
        int radius = XiyusLoginConfig.FAKE_FLAT_CHUNK_RADIUS.get();
        int minY = level.dimensionType().minY();
        int maxY = minY + level.dimensionType().height() - 1;
        int platformY = Math.max(minY, Math.min(maxY, XiyusLoginConfig.FAKE_FLAT_PLATFORM_Y.get()));
        BlockState floorState = resolveFakeFlatBlock().defaultBlockState();

        for (int dx = -radius; dx <= radius; dx++) {
            for (int dz = -radius; dz <= radius; dz++) {
                ChunkPos chunkPos = new ChunkPos(centerChunkX + dx, centerChunkZ + dz);
                try {
                    LevelChunk fakeChunk = createFlatClientOnlyChunk(level, chunkPos, platformY, floorState);
                    player.connection.send(new ClientboundLevelChunkWithLightPacket(fakeChunk, level.getLightEngine(), null, null));
                } catch (Exception e) {
                    Xiyuslogin.LOGGER.warn("Failed to send fake flat chunk {} to player {}: {}",
                            chunkPos, player.getName().getString(), e.getMessage());
                }
            }
        }
    }

    private LevelChunk createFlatClientOnlyChunk(ServerLevel level, ChunkPos chunkPos, int platformY, BlockState floorState) {
        LevelChunk chunk = new LevelChunk(level, chunkPos);
        int sectionIndex = chunk.getSectionIndex(platformY);
        if (sectionIndex >= 0 && sectionIndex < chunk.getSections().length) {
            LevelChunkSection section = chunk.getSection(sectionIndex);
            int localY = platformY & 15;
            for (int x = 0; x < 16; x++) {
                for (int z = 0; z < 16; z++) {
                    section.setBlockState(x, localY, z, floorState, false);
                }
            }
            Heightmap.primeHeightmaps(chunk, EnumSet.of(
                    Heightmap.Types.WORLD_SURFACE,
                    Heightmap.Types.MOTION_BLOCKING
            ));
        }
        return chunk;
    }

    private Block resolveFakeFlatBlock() {
        ResourceLocation blockId = ResourceLocation.tryParse(XiyusLoginConfig.FAKE_FLAT_BLOCK.get());
        if (blockId != null) {
            Block block = BuiltInRegistries.BLOCK.get(blockId);
            if (block != Blocks.AIR) {
                return block;
            }
        }
        return Blocks.BEDROCK;
    }

    private void unloadRealChunksFromClient(ServerPlayer player) {
        int radius = XiyusLoginConfig.FAKE_CHUNK_UNLOAD_RADIUS.get();
        if (radius <= 0) {
            return;
        }

        ChunkPos center = player.chunkPosition();
        for (int dx = -radius; dx <= radius; dx++) {
            for (int dz = -radius; dz <= radius; dz++) {
                player.connection.send(new ClientboundForgetLevelChunkPacket(new ChunkPos(center.x + dx, center.z + dz)));
            }
        }
    }

    private void syncActualInventoryView(ServerPlayer player) {
        try {
            syncActualPositionView(player);
            player.getInventory().setChanged();
            player.inventoryMenu.broadcastFullState();
            if (player.containerMenu != player.inventoryMenu) {
                player.containerMenu.broadcastFullState();
            }
            Xiyuslogin.LOGGER.debug("Synced actual inventory for player {}", player.getName().getString());
        } catch (Exception e) {
            Xiyuslogin.LOGGER.error("Failed to sync actual inventory for player {}: {}",
                    player.getName().getString(), e.getMessage());
        }
    }

    private void syncActualPositionView(ServerPlayer player) {
        if (XiyusLoginConfig.AUTH_VIEW_MODE.get() == XiyusLoginConfig.AuthViewMode.INVENTORY_ONLY) {
            return;
        }

        player.connection.teleport(player.getX(), player.getY(), player.getZ(), player.getYRot(), player.getXRot());
        player.connection.send(new ClientboundSetChunkCacheCenterPacket(player.chunkPosition().x, player.chunkPosition().z));
    }

    private void applyFrozenPlayerState(ServerPlayer player, FrozenPlayerData frozenData) {
        stabilizeUnauthenticatedPlayer(player);
        if (XiyusLoginConfig.LEGALIZE_UNAUTHENTICATED_FLOATING.get() && !frozenData.noGravityApplied) {
            frozenData.previousNoGravity = player.isNoGravity();
            frozenData.noGravityApplied = true;
            player.setNoGravity(true);
        }
    }

    private void restoreFrozenPlayerState(ServerPlayer player, FrozenPlayerData frozenData) {
        if (frozenData.noGravityApplied) {
            player.setNoGravity(frozenData.previousNoGravity);
        }
        player.resetFallDistance();
    }

    private void applyFreezeEffects(ServerPlayer player) {
        if (!player.hasEffect(MobEffects.INVISIBILITY)
                || player.getEffect(MobEffects.INVISIBILITY).getDuration() <= 10) {
            player.addEffect(new MobEffectInstance(MobEffects.INVISIBILITY, 20, 0, false, false));
        }

        if (!player.hasEffect(MobEffects.DAMAGE_RESISTANCE)
                || player.getEffect(MobEffects.DAMAGE_RESISTANCE).getDuration() <= 10) {
            player.addEffect(new MobEffectInstance(MobEffects.DAMAGE_RESISTANCE, 20, 255, false, false));
        }

        if (XiyusLoginConfig.BLIND_UNAUTHENTICATED_PLAYERS.get()
                && (!player.hasEffect(MobEffects.BLINDNESS)
                || player.getEffect(MobEffects.BLINDNESS).getDuration() <= 10)) {
            player.addEffect(new MobEffectInstance(MobEffects.BLINDNESS, 80, 255, false, false));
        }
    }

    private void removeAllEffects(ServerPlayer player) {
        player.removeEffect(MobEffects.NIGHT_VISION);
        player.removeEffect(MobEffects.INVISIBILITY);
        player.removeEffect(MobEffects.DAMAGE_RESISTANCE);
        if (XiyusLoginConfig.BLIND_UNAUTHENTICATED_PLAYERS.get()) {
            player.removeEffect(MobEffects.BLINDNESS);
        }
    }

    private ServerPlayer getPlayerById(UUID playerId) {
        if (server != null && server.getPlayerList() != null) {
            return server.getPlayerList().getPlayer(playerId);
        }
        return null;
    }

    private void runOnServerThread(Runnable task) {
        if (server != null) {
            server.execute(task);
        } else {
            task.run();
        }
    }

    public void shutdown() {
        scheduler.shutdown();
        try {
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                scheduler.shutdownNow();
            }
        } catch (InterruptedException e) {
            scheduler.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    private static class FrozenPlayerData {
        private final UUID playerId;
        private final long freezeTime;
        private boolean noGravityApplied;
        private boolean previousNoGravity;
        public ScheduledFuture<?> effectTask;
        public ScheduledFuture<?> timeoutTask;

        public FrozenPlayerData(UUID playerId) {
            this.playerId = playerId;
            this.freezeTime = System.currentTimeMillis();
        }

        public UUID getPlayerId() {
            return playerId;
        }

        public long getFreezeTime() {
            return freezeTime;
        }
    }
}
