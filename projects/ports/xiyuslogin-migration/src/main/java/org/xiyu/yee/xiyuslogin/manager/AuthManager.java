package org.xiyu.yee.xiyuslogin.manager;

import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.HoverEvent;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import org.xiyu.yee.xiyuslogin.Xiyuslogin;
import org.xiyu.yee.xiyuslogin.config.AuthCommandConfig;
import org.xiyu.yee.xiyuslogin.config.LoginText;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginConfig;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginLanguageConfig;
import org.xiyu.yee.xiyuslogin.data.PlayerDataManager;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class AuthManager {
    private static AuthManager instance;
    private PlayerDataManager playerDataManager;
    private final FreezeManager freezeManager;
    private final Map<UUID, Boolean> authenticatedPlayers = new ConcurrentHashMap<>();
    private final Map<UUID, Integer> passwordErrors = new ConcurrentHashMap<>();
    private final Map<String, Long> ipSessions = new ConcurrentHashMap<>();

    private AuthManager() {
        this.freezeManager = FreezeManager.getInstance();
    }

    public static AuthManager getInstance() {
        if (instance == null) {
            instance = new AuthManager();
        }
        return instance;
    }

    public void initialize(MinecraftServer server) {
        this.playerDataManager = new PlayerDataManager(server);
        this.freezeManager.setServer(server);
    }

    public void handlePlayerJoin(ServerPlayer player) {
        String username = player.getName().getString();
        UUID uuid = player.getUUID();

        authenticatedPlayers.remove(uuid);
        passwordErrors.remove(uuid);

        Xiyuslogin.LOGGER.info("Player {} ({}) joining server", username, uuid);

        PlayerDataManager.PlayerData playerData = playerDataManager.getPlayerData(username);
        boolean isRegistered = playerData != null && playerData.hasPassword();
        if (playerData != null && playerData.isLegacyPremiumAutoLogin()
                && playerData.getUuid() != null && playerData.getUuid().equals(uuid)
                && player.getServer() != null && player.getServer().usesAuthentication()) {
            authenticatedPlayers.put(uuid, true);
            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.SESSION_RESTORED));
            Xiyuslogin.LOGGER.info("Restored premium authentication for player {} ({})", username, uuid);
            return;
        }
        Xiyuslogin.LOGGER.debug("Player {} registration status: {}", username, isRegistered);

        if (isRegistered && hasValidIpSession(username, player)) {
            authenticatedPlayers.put(uuid, true);
            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.SESSION_RESTORED));
            Xiyuslogin.LOGGER.info("Restored IP session for player {} ({}) from {}", username, uuid, player.getIpAddress());
            return;
        }

        freezeManager.freezePlayer(uuid);
        if (isRegistered) {
            player.sendSystemMessage(LoginText.component(
                    XiyusLoginLanguageConfig.WELCOME_LOGIN,
                    "login_commands", AuthCommandConfig.loginCommandUsages()
            ));
            sendForgetPasswordMessage(player);
        } else {
            player.sendSystemMessage(LoginText.component(
                    XiyusLoginLanguageConfig.WELCOME_REGISTER,
                    "register_commands", AuthCommandConfig.registerCommandUsages()
            ));
        }
    }

    private void sendForgetPasswordMessage(ServerPlayer player) {
        MutableComponent forgetPasswordMessage = LoginText.component(XiyusLoginLanguageConfig.FORGET_PASSWORD_PREFIX)
                .setStyle(Style.EMPTY
                        .withClickEvent(new ClickEvent(
                                ClickEvent.Action.SUGGEST_COMMAND,
                                LoginText.text(XiyusLoginLanguageConfig.FORGET_PASSWORD_SUGGEST_COMMAND)
                        ))
                        .withHoverEvent(new HoverEvent(
                                HoverEvent.Action.SHOW_TEXT,
                                LoginText.component(XiyusLoginLanguageConfig.FORGET_PASSWORD_HOVER)
                        ))
                )
                .append(LoginText.component(XiyusLoginLanguageConfig.FORGET_PASSWORD_SUFFIX));

        player.sendSystemMessage(forgetPasswordMessage);
    }

    public boolean registerPlayer(ServerPlayer player, String password, String confirmPassword) {
        String username = player.getName().getString();
        UUID uuid = player.getUUID();

        if (password.length() < XiyusLoginConfig.MIN_PASSWORD_LENGTH.get()) {
            player.sendSystemMessage(LoginText.component(
                    XiyusLoginLanguageConfig.PASSWORD_TOO_SHORT,
                    "min", XiyusLoginConfig.MIN_PASSWORD_LENGTH.get()
            ));
            return false;
        }

        if (password.length() > XiyusLoginConfig.MAX_PASSWORD_LENGTH.get()) {
            player.sendSystemMessage(LoginText.component(
                    XiyusLoginLanguageConfig.PASSWORD_TOO_LONG,
                    "max", XiyusLoginConfig.MAX_PASSWORD_LENGTH.get()
            ));
            return false;
        }

        if (!password.equals(confirmPassword)) {
            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.PASSWORD_MISMATCH));
            return false;
        }

        if (playerDataManager.isPlayerRegistered(username)) {
            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.USERNAME_REGISTERED));
            return false;
        }

        if (playerDataManager.registerPlayer(username, password, uuid)) {
            authenticatedPlayers.put(uuid, true);
            passwordErrors.remove(uuid);
            rememberIpSession(username, player);
            freezeManager.unfreezePlayer(uuid);

            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.REGISTER_SUCCESS));
            Xiyuslogin.LOGGER.info("Player {} registered successfully", username);
            return true;
        } else {
            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.REGISTER_FAILED));
            return false;
        }
    }

    public boolean loginPlayer(ServerPlayer player, String password) {
        String username = player.getName().getString();
        UUID uuid = player.getUUID();

        if (!playerDataManager.isPlayerRegistered(username)) {
            player.sendSystemMessage(LoginText.component(
                    XiyusLoginLanguageConfig.USERNAME_NOT_REGISTERED_WITH_COMMAND,
                    "register_command", AuthCommandConfig.firstRegisterCommand()
            ));
            return false;
        }

        if (playerDataManager.loginPlayer(username, password)) {
            authenticatedPlayers.put(uuid, true);
            passwordErrors.remove(uuid);
            rememberIpSession(username, player);
            freezeManager.unfreezePlayer(uuid);

            PlayerDataManager.PlayerData playerData = playerDataManager.getPlayerData(username);
            if (playerData != null) {
                playerData.setLastLoginTime(LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME));
                playerData.incrementLoginCount();
                playerDataManager.saveData();
            }

            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.LOGIN_SUCCESS));
            Xiyuslogin.LOGGER.info("Player {} logged in successfully", username);
            return true;
        }

        int attempts = passwordErrors.merge(uuid, 1, Integer::sum);
        int maxAttempts = XiyusLoginConfig.PASSWORDERROR.get();
        if (attempts == 1) {
            player.sendSystemMessage(LoginText.component(
                    XiyusLoginLanguageConfig.PASSWORD_ERROR_FIRST,
                    "max", maxAttempts
            ));
        } else {
            player.sendSystemMessage(LoginText.component(
                    XiyusLoginLanguageConfig.PASSWORD_ERROR_COUNT,
                    "count", attempts
            ));
        }

        if (attempts > maxAttempts) {
            player.connection.disconnect(LoginText.component(
                    XiyusLoginLanguageConfig.PASSWORD_ERROR_KICK,
                    "max", maxAttempts
            ));
            passwordErrors.remove(uuid);
        }
        return false;
    }

    public void handlePlayerQuit(ServerPlayer player) {
        UUID uuid = player.getUUID();
        authenticatedPlayers.remove(uuid);
        passwordErrors.remove(uuid);
        freezeManager.unfreezePlayer(uuid);
    }

    public void handlePlayerLeave(ServerPlayer player) {
        handlePlayerQuit(player);
    }

    public boolean isAuthenticated(UUID uuid) {
        return authenticatedPlayers.getOrDefault(uuid, false);
    }

    public void setPlayerAuthenticated(UUID uuid, boolean authenticated) {
        if (authenticated) {
            authenticatedPlayers.put(uuid, true);
            passwordErrors.remove(uuid);
        } else {
            authenticatedPlayers.remove(uuid);
        }
    }

    public PlayerDataManager getPlayerDataManager() {
        return playerDataManager;
    }

    public FreezeManager getFreezeManager() {
        return freezeManager;
    }

    public void rememberIpSession(ServerPlayer player) {
        rememberIpSession(player.getName().getString(), player);
    }

    public void clearIpSessions(String username) {
        String prefix = username.toLowerCase() + "|";
        ipSessions.keySet().removeIf(key -> key.startsWith(prefix));
    }

    public boolean submitPasswordResetRequest(ServerPlayer player, String reason, String newPassword) {
        String username = player.getName().getString();
        UUID uuid = player.getUUID();

        if (!playerDataManager.isPlayerRegistered(username)) {
            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.USERNAME_NOT_REGISTERED));
            return false;
        }

        if (newPassword.length() < XiyusLoginConfig.MIN_PASSWORD_LENGTH.get()
                || newPassword.length() > XiyusLoginConfig.MAX_PASSWORD_LENGTH.get()) {
            player.sendSystemMessage(LoginText.component(
                    XiyusLoginLanguageConfig.PASSWORD_RESET_LENGTH,
                    "min", XiyusLoginConfig.MIN_PASSWORD_LENGTH.get(),
                    "max", XiyusLoginConfig.MAX_PASSWORD_LENGTH.get()
            ));
            return false;
        }

        String safeReason = PlayerDataManager.redactResetReason(reason, newPassword);
        playerDataManager.addPasswordResetRequest(username, safeReason, newPassword, uuid);

        player.sendSystemMessage(LoginText.component(
                XiyusLoginLanguageConfig.PASSWORD_RESET_SUBMITTED,
                "reason", safeReason
        ));

        Xiyuslogin.LOGGER.info("Password reset request submitted by {} ({})", username, uuid);
        return true;
    }

    private boolean hasValidIpSession(String username, ServerPlayer player) {
        if (!XiyusLoginConfig.ENABLE_IP_SESSION.get() || XiyusLoginConfig.IP_SESSION_DURATION_SECONDS.get() <= 0) {
            return false;
        }

        String key = ipSessionKey(username, player);
        Long expiresAt = ipSessions.get(key);
        long now = System.currentTimeMillis();
        if (expiresAt == null) {
            return false;
        }

        if (expiresAt <= now) {
            ipSessions.remove(key);
            return false;
        }
        return true;
    }

    private void rememberIpSession(String username, ServerPlayer player) {
        if (!XiyusLoginConfig.ENABLE_IP_SESSION.get() || XiyusLoginConfig.IP_SESSION_DURATION_SECONDS.get() <= 0) {
            return;
        }

        long expiresAt = System.currentTimeMillis() + XiyusLoginConfig.IP_SESSION_DURATION_SECONDS.get() * 1000L;
        ipSessions.put(ipSessionKey(username, player), expiresAt);
    }

    private String ipSessionKey(String username, ServerPlayer player) {
        return username.toLowerCase() + "|" + player.getIpAddress();
    }
}
