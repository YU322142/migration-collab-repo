package com.bmt.waypointfire.command;

import com.bmt.waypointfire.WaypointIcon;
import com.bmt.waypointfire.WaypointIconCarrier;
import com.bmt.waypointfire.server.WaypointManager;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import com.mojang.brigadier.exceptions.SimpleCommandExceptionType;
import java.util.OptionalInt;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.ColorArgument;
import net.minecraft.commands.arguments.EntityArgument;
import net.minecraft.commands.arguments.ResourceLocationArgument;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;

public final class WaypointCommand {
    private static final SimpleCommandExceptionType INVALID = new SimpleCommandExceptionType(Component.translatable("commands.waypoint.invalid"));

    private WaypointCommand() {}

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("waypoint")
            .requires(source -> source.hasPermission(2))
            .then(Commands.literal("list").executes(context -> list(context.getSource())))
            .then(Commands.literal("modify")
                .then(Commands.argument("waypoint", EntityArgument.entity())
                    .then(Commands.literal("color")
                        .then(Commands.argument("color", ColorArgument.color())
                            .executes(context -> setNamedColor(
                                context.getSource(),
                                getLiving(EntityArgument.getEntity(context, "waypoint")),
                                ColorArgument.getColor(context, "color")
                            )))
                        .then(Commands.literal("hex")
                            .then(Commands.argument("color", HexColorArgument.hexColor())
                                .executes(context -> setColor(
                                    context.getSource(),
                                    getLiving(EntityArgument.getEntity(context, "waypoint")),
                                    HexColorArgument.getHexColor(context, "color")
                                ))))
                        .then(Commands.literal("reset")
                            .executes(context -> resetColor(
                                context.getSource(),
                                getLiving(EntityArgument.getEntity(context, "waypoint"))
                            ))))
                    .then(Commands.literal("style")
                        .then(Commands.literal("reset")
                            .executes(context -> setStyle(
                                context.getSource(),
                                getLiving(EntityArgument.getEntity(context, "waypoint")),
                                WaypointIcon.DEFAULT_STYLE
                            )))
                        .then(Commands.literal("set")
                            .then(Commands.argument("style", ResourceLocationArgument.id())
                                .executes(context -> setStyle(
                                    context.getSource(),
                                    getLiving(EntityArgument.getEntity(context, "waypoint")),
                                    ResourceLocationArgument.getId(context, "style")
                                ))))))));
    }

    private static int list(CommandSourceStack source) {
        var active = WaypointManager.activeIn(source.getLevel());
        if (active.isEmpty()) {
            source.sendSuccess(() -> Component.translatable("commands.waypoint.list.empty"), false);
            return 0;
        }
        Component names = Component.empty();
        boolean first = true;
        for (LivingEntity entity : active) {
            if (!first) {
                names = names.copy().append(Component.literal(", "));
            }
            names = names.copy().append(entity.getDisplayName());
            first = false;
        }
        Component result = names;
        source.sendSuccess(() -> Component.literal(active.size() + ": ").append(result), false);
        return active.size();
    }

    private static int setNamedColor(CommandSourceStack source, LivingEntity entity, ChatFormatting color) {
        Integer value = color.getColor();
        if (value == null) {
            return resetColor(source, entity);
        }
        return setColor(source, entity, value);
    }

    private static int setColor(CommandSourceStack source, LivingEntity entity, int color) {
        WaypointIcon old = icon(entity);
        setIcon(entity, new WaypointIcon(old.style(), OptionalInt.of(color)));
        source.sendSuccess(() -> Component.translatable("commands.waypoint.modify.color"), false);
        return 0;
    }

    private static int resetColor(CommandSourceStack source, LivingEntity entity) {
        WaypointIcon old = icon(entity);
        setIcon(entity, new WaypointIcon(old.style(), OptionalInt.empty()));
        source.sendSuccess(() -> Component.translatable("commands.waypoint.modify.color.reset"), false);
        return 0;
    }

    private static int setStyle(CommandSourceStack source, LivingEntity entity, ResourceLocation style) {
        WaypointIcon old = icon(entity);
        setIcon(entity, new WaypointIcon(style, old.color()));
        source.sendSuccess(() -> Component.translatable("commands.waypoint.modify.style"), false);
        return 0;
    }

    private static LivingEntity getLiving(Entity entity) throws CommandSyntaxException {
        if (entity instanceof LivingEntity living) {
            return living;
        }
        throw INVALID.create();
    }

    private static WaypointIcon icon(LivingEntity entity) {
        return ((WaypointIconCarrier) entity).waypointFire$getIcon();
    }

    private static void setIcon(LivingEntity entity, WaypointIcon icon) {
        ((WaypointIconCarrier) entity).waypointFire$setIcon(icon);
        WaypointManager.iconChanged(entity);
    }
}
