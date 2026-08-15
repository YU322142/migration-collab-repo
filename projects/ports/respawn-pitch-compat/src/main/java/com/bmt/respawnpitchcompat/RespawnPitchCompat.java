package com.bmt.respawnpitchcompat;

import net.minecraft.core.BlockPos;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.block.BedBlock;
import net.minecraft.world.level.block.RespawnAnchorBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.portal.DimensionTransition;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.entity.player.PlayerRespawnPositionEvent;

@Mod(RespawnPitchCompat.MOD_ID)
public final class RespawnPitchCompat {
    public static final String MOD_ID = "respawn_pitch_compat";

    public RespawnPitchCompat(IEventBus modBus) {
        NeoForge.EVENT_BUS.addListener(RespawnPitchCompat::onRespawnPosition);
    }

    private static void onRespawnPosition(PlayerRespawnPositionEvent event) {
        ServerPlayer player = (ServerPlayer) event.getEntity();
        RespawnPitchAccess access = (RespawnPitchAccess) player;
        BlockPos respawnPos = player.getRespawnPosition();
        if (event.isFromEndFight()
                || respawnPos == null
                || !player.isRespawnForced()
                || !access.respawnPitchCompat$hasPitch()) {
            return;
        }

        DimensionTransition transition = event.getDimensionTransition();
        if (transition.missingRespawnBlock()) {
            return;
        }

        MinecraftServer server = player.getServer();
        ServerLevel respawnLevel = server == null ? null : server.getLevel(player.getRespawnDimension());
        if (respawnLevel == null) {
            return;
        }

        BlockState state = respawnLevel.getBlockState(respawnPos);
        if (state.getBlock() instanceof BedBlock || state.getBlock() instanceof RespawnAnchorBlock) {
            return;
        }

        event.setDimensionTransition(new DimensionTransition(
                transition.newLevel(),
                transition.pos(),
                transition.speed(),
                transition.yRot(),
                access.respawnPitchCompat$getPitch(),
                transition.missingRespawnBlock(),
                transition.postDimensionTransition()));
    }
}
