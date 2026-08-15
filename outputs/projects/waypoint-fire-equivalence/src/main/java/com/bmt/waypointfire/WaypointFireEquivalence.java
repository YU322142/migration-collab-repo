package com.bmt.waypointfire;

import com.bmt.waypointfire.command.WaypointCommand;
import com.bmt.waypointfire.command.HexColorArgument;
import com.bmt.waypointfire.network.WaypointNetworking;
import com.bmt.waypointfire.server.WaypointManager;
import net.minecraft.commands.synchronization.ArgumentTypeInfo;
import net.minecraft.commands.synchronization.ArgumentTypeInfos;
import net.minecraft.commands.synchronization.SingletonArgumentInfo;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.ai.attributes.Attribute;
import net.minecraft.world.entity.ai.attributes.RangedAttribute;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.entity.EntityAttributeModificationEvent;
import net.neoforged.neoforge.event.entity.EntityJoinLevelEvent;
import net.neoforged.neoforge.event.entity.EntityLeaveLevelEvent;
import net.neoforged.neoforge.event.server.ServerStartingEvent;
import net.neoforged.neoforge.event.server.ServerStoppedEvent;
import net.neoforged.neoforge.event.tick.ServerTickEvent;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

@Mod(WaypointFireEquivalence.MOD_ID)
public final class WaypointFireEquivalence {
    public static final String MOD_ID = "waypoint_fire_equivalence";
    private static final DeferredRegister<Attribute> ATTRIBUTES = DeferredRegister.create(Registries.ATTRIBUTE, "minecraft");
    private static final DeferredRegister<ArgumentTypeInfo<?, ?>> COMMAND_ARGUMENT_TYPES =
        DeferredRegister.create(Registries.COMMAND_ARGUMENT_TYPE, MOD_ID);

    public static final DeferredHolder<ArgumentTypeInfo<?, ?>, SingletonArgumentInfo<HexColorArgument>> HEX_COLOR_ARGUMENT =
        COMMAND_ARGUMENT_TYPES.register(
            "hex_color",
            () -> ArgumentTypeInfos.registerByClass(
                HexColorArgument.class,
                SingletonArgumentInfo.contextFree(HexColorArgument::hexColor)
            )
        );

    public static final DeferredHolder<Attribute, Attribute> WAYPOINT_TRANSMIT_RANGE = ATTRIBUTES.register(
        "waypoint_transmit_range",
        () -> new RangedAttribute("attribute.name.waypoint_transmit_range", 0.0, 0.0, 60_000_000.0)
            .setSentiment(Attribute.Sentiment.NEUTRAL)
    );
    public static final DeferredHolder<Attribute, Attribute> WAYPOINT_RECEIVE_RANGE = ATTRIBUTES.register(
        "waypoint_receive_range",
        () -> new RangedAttribute("attribute.name.waypoint_receive_range", 0.0, 0.0, 60_000_000.0)
            .setSentiment(Attribute.Sentiment.NEUTRAL)
    );

    public WaypointFireEquivalence(IEventBus modBus) {
        CompatGameRules.bootstrap();
        ATTRIBUTES.register(modBus);
        COMMAND_ARGUMENT_TYPES.register(modBus);
        modBus.addListener(this::addAttributes);
        modBus.addListener(WaypointNetworking::register);

        NeoForge.EVENT_BUS.addListener(this::serverStarting);
        NeoForge.EVENT_BUS.addListener(this::entityJoin);
        NeoForge.EVENT_BUS.addListener(this::entityLeave);
        NeoForge.EVENT_BUS.addListener(this::serverTick);
        NeoForge.EVENT_BUS.addListener(this::registerCommands);
        NeoForge.EVENT_BUS.addListener(this::serverStopped);
    }

    private void addAttributes(EntityAttributeModificationEvent event) {
        Holder<Attribute> transmit = WAYPOINT_TRANSMIT_RANGE;
        Holder<Attribute> receive = WAYPOINT_RECEIVE_RANGE;
        for (EntityType<? extends net.minecraft.world.entity.LivingEntity> type : event.getTypes()) {
            event.add(type, transmit, type == EntityType.PLAYER ? 60_000_000.0 : 0.0);
            event.add(type, receive, type == EntityType.PLAYER ? 60_000_000.0 : 0.0);
        }
    }

    private void serverStarting(ServerStartingEvent event) {
        CompatGameRules.migrateLoadedRules(event.getServer());
    }

    private void entityJoin(EntityJoinLevelEvent event) {
        WaypointManager.entityJoined(event.getEntity(), event.getLevel());
    }

    private void entityLeave(EntityLeaveLevelEvent event) {
        WaypointManager.entityLeft(event.getEntity(), event.getLevel());
    }

    private void serverTick(ServerTickEvent.Post event) {
        WaypointManager.tick(event.getServer());
    }

    private void registerCommands(RegisterCommandsEvent event) {
        WaypointCommand.register(event.getDispatcher());
    }

    private void serverStopped(ServerStoppedEvent event) {
        WaypointManager.clear();
    }
}
