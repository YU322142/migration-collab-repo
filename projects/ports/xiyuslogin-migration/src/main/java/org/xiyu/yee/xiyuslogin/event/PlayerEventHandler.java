package org.xiyu.yee.xiyuslogin.event;

import net.minecraft.server.level.ServerPlayer;
import net.neoforged.bus.api.EventPriority;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.neoforge.event.tick.PlayerTickEvent;
import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;
import net.neoforged.neoforge.event.level.BlockEvent;
import net.neoforged.neoforge.event.ServerChatEvent;
import net.neoforged.neoforge.event.entity.living.LivingDamageEvent;
import net.neoforged.neoforge.event.entity.living.LivingIncomingDamageEvent;
import net.neoforged.neoforge.event.entity.player.AttackEntityEvent;
import org.xiyu.yee.xiyuslogin.config.AuthCommandConfig;
import org.xiyu.yee.xiyuslogin.config.LoginText;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginConfig;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginLanguageConfig;
import org.xiyu.yee.xiyuslogin.manager.AuthManager;
import org.xiyu.yee.xiyuslogin.manager.FreezeManager;

public class PlayerEventHandler {
    
    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onPlayerTick(PlayerTickEvent.Post event) {
        if (event.getEntity() instanceof ServerPlayer player) {
            FreezeManager freezeManager = FreezeManager.getInstance();
            if (freezeManager.isFrozen(player.getUUID())) {
                freezeManager.preventMovement(player);
            }
        }
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onIncomingDamage(LivingIncomingDamageEvent event) {
        if (!XiyusLoginConfig.PROTECT_UNAUTHENTICATED_PLAYERS.get()) {
            return;
        }

        if (event.getEntity() instanceof ServerPlayer player
                && !AuthManager.getInstance().isAuthenticated(player.getUUID())) {
            event.setCanceled(true);
            event.setAmount(0.0F);
            FreezeManager.getInstance().stabilizeUnauthenticatedPlayer(player);
        }
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onLivingDamagePre(LivingDamageEvent.Pre event) {
        if (!XiyusLoginConfig.PROTECT_UNAUTHENTICATED_PLAYERS.get()) {
            return;
        }

        if (event.getEntity() instanceof ServerPlayer player
                && !AuthManager.getInstance().isAuthenticated(player.getUUID())) {
            event.setNewDamage(0.0F);
            FreezeManager.getInstance().stabilizeUnauthenticatedPlayer(player);
        }
    }
    
    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onPlayerInteractRightClick(PlayerInteractEvent.RightClickBlock event) {
        if (event.getEntity() instanceof ServerPlayer player) {
            if (!AuthManager.getInstance().isAuthenticated(player.getUUID())) {
                event.setCanceled(true);
            }
        }
    }
    
    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onPlayerInteractLeftClick(PlayerInteractEvent.LeftClickBlock event) {
        if (event.getEntity() instanceof ServerPlayer player) {
            if (!AuthManager.getInstance().isAuthenticated(player.getUUID())) {
                event.setCanceled(true);
            }
        }
    }
    
    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onPlayerInteractItem(PlayerInteractEvent.RightClickItem event) {
        if (event.getEntity() instanceof ServerPlayer player) {
            if (!AuthManager.getInstance().isAuthenticated(player.getUUID())) {
                event.setCanceled(true);
            }
        }
    }
    
    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onBlockBreak(BlockEvent.BreakEvent event) {
        if (event.getPlayer() instanceof ServerPlayer player) {
            if (!AuthManager.getInstance().isAuthenticated(player.getUUID())) {
                event.setCanceled(true);
            }
        }
    }
    
    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onBlockPlace(BlockEvent.EntityPlaceEvent event) {
        if (event.getEntity() instanceof ServerPlayer player) {
            if (!AuthManager.getInstance().isAuthenticated(player.getUUID())) {
                event.setCanceled(true);
            }
        }
    }
    
    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onPlayerChat(ServerChatEvent event) {
        ServerPlayer player = event.getPlayer();
        String message = event.getMessage().getString(); // 使用getMessage().getString()方法获取文本
        
        if (!AuthManager.getInstance().isAuthenticated(player.getUUID())) {
            // 检查是否为允许的验证指令
            if (isAuthCommand(message)) {
                return; // 允许验证指令通过
            }
            
            // 阻止其他聊天消息
            event.setCanceled(true);
            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.AUTH_CHAT_BLOCKED));
        }
    }
    
    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onPlayerAttack(AttackEntityEvent event) {
        if (event.getEntity() instanceof ServerPlayer player) {
            if (!AuthManager.getInstance().isAuthenticated(player.getUUID())) {
                // 未验证玩家不能攻击
                event.setCanceled(true);
            }
        }
    }
    
    private static boolean isAuthCommand(String message) {
        String trimmed = message.trim();
        if (!trimmed.startsWith("/")) {
            return false;
        }

        String commandName = trimmed.split("\\s+", 2)[0];
        return AuthCommandConfig.isAllowedFrozenCommand(commandName);
    }
}
