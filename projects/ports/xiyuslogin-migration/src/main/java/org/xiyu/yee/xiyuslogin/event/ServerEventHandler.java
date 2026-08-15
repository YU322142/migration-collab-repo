package org.xiyu.yee.xiyuslogin.event;

import net.minecraft.commands.CommandSourceStack;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Player;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.neoforge.event.CommandEvent;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.ServerChatEvent;
import net.neoforged.neoforge.event.entity.player.PlayerEvent;
import net.neoforged.neoforge.event.server.ServerStartedEvent;
import net.neoforged.neoforge.event.server.ServerStoppingEvent;
import org.xiyu.yee.xiyuslogin.Xiyuslogin;
import org.xiyu.yee.xiyuslogin.command.AdminCommands;
import org.xiyu.yee.xiyuslogin.command.AuthCommands;
import org.xiyu.yee.xiyuslogin.config.AuthCommandConfig;
import org.xiyu.yee.xiyuslogin.config.LoginText;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginLanguageConfig;
import org.xiyu.yee.xiyuslogin.manager.AuthManager;
import org.xiyu.yee.xiyuslogin.manager.FreezeManager;

public class ServerEventHandler {
    
    @SubscribeEvent
    public static void onServerStarted(ServerStartedEvent event) {
        AuthManager.getInstance().initialize(event.getServer());
        Xiyuslogin.LOGGER.info("XiyusLogin authentication system initialized");
    }
    @SubscribeEvent
    public static void onPlayersay(ServerChatEvent event) {
        Player player = event.getPlayer();
        if(FreezeManager.isFrozen(player.getUUID())) {
            event.setCanceled(true);
        }
    }
    @SubscribeEvent
    public static void onPlayerCommand(CommandEvent event) {
        CommandSourceStack source = event.getParseResults().getContext().getSource();

        // 1. 仅处理玩家的命令（排除控制台等其他来源）
        if (!(source.getEntity() instanceof ServerPlayer player)) {
            return;
        }

        // 2. 检查玩家是否被冻结（未被冻结则不拦截）
        if (!FreezeManager.isFrozen(player.getUUID())) {
            return;
        }

        String command = event.getParseResults().getReader().getString().trim();
        String commandName = command.split("\\s+", 2)[0];

        if (!AuthCommandConfig.isAllowedFrozenCommand(commandName)) {
            event.setCanceled(true);
            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.FROZEN_COMMAND_BLOCKED));
        }
    }
    @SubscribeEvent
    public static void onServerStopping(ServerStoppingEvent event) {
        // 保存所有数据
        AuthManager.getInstance().getPlayerDataManager().saveData();
        
        // 关闭冻结管理器
        FreezeManager.getInstance().shutdown();
        
        Xiyuslogin.LOGGER.info("XiyusLogin data saved and systems shutdown");
    }
    
    @SubscribeEvent
    public static void onRegisterCommands(RegisterCommandsEvent event) {
        AuthCommands.register(event.getDispatcher());
        AdminCommands.register(event.getDispatcher());
        Xiyuslogin.LOGGER.info("XiyusLogin commands registered");
    }
    
    @SubscribeEvent
    public static void onPlayerJoin(PlayerEvent.PlayerLoggedInEvent event) {
        if (event.getEntity() instanceof ServerPlayer player) {
            AuthManager.getInstance().handlePlayerJoin(player);
        }
    }
    
    @SubscribeEvent
    public static void onPlayerLeave(PlayerEvent.PlayerLoggedOutEvent event) {
        if (event.getEntity() instanceof ServerPlayer player) {
            AuthManager.getInstance().handlePlayerLeave(player);
        }
    }
}
