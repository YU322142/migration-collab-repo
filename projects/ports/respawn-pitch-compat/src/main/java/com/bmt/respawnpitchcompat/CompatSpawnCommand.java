package com.bmt.respawnpitchcompat;

import com.mojang.brigadier.CommandDispatcher;
import java.util.Collection;
import java.util.Collections;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.AngleArgument;
import net.minecraft.commands.arguments.EntityArgument;
import net.minecraft.commands.arguments.coordinates.BlockPosArgument;
import net.minecraft.commands.arguments.coordinates.Coordinates;
import net.minecraft.commands.arguments.coordinates.RotationArgument;
import net.minecraft.commands.arguments.coordinates.WorldCoordinates;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Mth;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec2;

public final class CompatSpawnCommand {
    private CompatSpawnCommand() {
    }

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("spawnpoint")
                .requires(source -> source.hasPermission(2))
                .executes(context -> setSpawn(
                        context.getSource(),
                        Collections.singleton(context.getSource().getPlayerOrException()),
                        BlockPos.containing(context.getSource().getPosition()),
                        WorldCoordinates.current()))
                .then(Commands.argument("targets", EntityArgument.players())
                        .executes(context -> setSpawn(
                                context.getSource(),
                                EntityArgument.getPlayers(context, "targets"),
                                BlockPos.containing(context.getSource().getPosition()),
                                WorldCoordinates.current()))
                        .then(Commands.argument("pos", BlockPosArgument.blockPos())
                                .executes(context -> setSpawn(
                                        context.getSource(),
                                        EntityArgument.getPlayers(context, "targets"),
                                        BlockPosArgument.getSpawnablePos(context, "pos"),
                                        WorldCoordinates.current()))
                                .then(Commands.argument("angle", AngleArgument.angle())
                                        .executes(context -> setSpawnResolved(
                                                context.getSource(),
                                                EntityArgument.getPlayers(context, "targets"),
                                                BlockPosArgument.getSpawnablePos(context, "pos"),
                                                AngleArgument.getAngle(context, "angle"),
                                                0.0F)))
                                .then(Commands.argument("rotation", RotationArgument.rotation())
                                        .executes(context -> setSpawn(
                                                context.getSource(),
                                                EntityArgument.getPlayers(context, "targets"),
                                                BlockPosArgument.getSpawnablePos(context, "pos"),
                                                RotationArgument.getRotation(context, "rotation")))))));
    }

    private static int setSpawn(
            CommandSourceStack source,
            Collection<ServerPlayer> players,
            BlockPos pos,
            Coordinates rotation) {
        Vec2 resolved = rotation.getRotation(source);
        return setSpawnResolved(
                source,
                players,
                pos,
                Mth.wrapDegrees(resolved.y),
                Mth.clamp(resolved.x, -90.0F, 90.0F));
    }

    private static int setSpawnResolved(
            CommandSourceStack source,
            Collection<ServerPlayer> players,
            BlockPos pos,
            float yaw,
            float pitch) {
        ResourceKey<Level> dimension = source.getLevel().dimension();

        for (ServerPlayer player : players) {
            RespawnPitchAccess access = (RespawnPitchAccess) player;
            long revision = access.respawnPitchCompat$getRevision();
            player.setRespawnPosition(dimension, pos, yaw, true, false);
            if (access.respawnPitchCompat$getRevision() != revision) {
                access.respawnPitchCompat$setPitch(pitch, true);
            }
        }

        String dimensionName = dimension.location().toString();
        if (players.size() == 1) {
            source.sendSuccess(() -> Component.translatable(
                    "commands.spawnpoint.success.single.new",
                    pos.getX(), pos.getY(), pos.getZ(), yaw, pitch,
                    dimensionName, players.iterator().next().getDisplayName()), true);
        } else {
            source.sendSuccess(() -> Component.translatable(
                    "commands.spawnpoint.success.multiple.new",
                    pos.getX(), pos.getY(), pos.getZ(), yaw, pitch, dimensionName, players.size()), true);
        }
        return players.size();
    }
}
