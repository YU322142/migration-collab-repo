package org.xiyu.yee.xiyuslogin.command;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.EntityArgument;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.HoverEvent;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;
import net.minecraft.server.level.ServerPlayer;
import org.xiyu.yee.xiyuslogin.config.LoginText;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginLanguageConfig;
import org.xiyu.yee.xiyuslogin.data.PlayerDataManager;
import org.xiyu.yee.xiyuslogin.manager.AuthManager;
import org.xiyu.yee.xiyuslogin.manager.FreezeManager;

import java.util.Map;

public class AdminCommands {

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("xiyuslogin")
                .requires(source -> source.hasPermission(4))
                .then(Commands.literal("reload")
                        .executes(AdminCommands::reload))
                .then(Commands.literal("info")
                        .then(Commands.argument("player", StringArgumentType.string())
                                .executes(AdminCommands::playerInfo)))
                .then(Commands.literal("resetpassword")
                        .then(Commands.argument("player", StringArgumentType.string())
                                .then(Commands.argument("newPassword", StringArgumentType.string())
                                        .executes(AdminCommands::resetPassword))))
                .then(Commands.literal("unregister")
                        .then(Commands.argument("player", StringArgumentType.string())
                                .executes(AdminCommands::unregister)))
                .then(Commands.literal("resetrequests")
                        .executes(AdminCommands::listResetRequests))
                .then(Commands.literal("approve")
                        .then(Commands.argument("username", StringArgumentType.string())
                                .executes(AdminCommands::approveReset)))
                .then(Commands.literal("reject")
                        .then(Commands.argument("username", StringArgumentType.string())
                                .executes(AdminCommands::rejectReset)))
                .then(Commands.literal("forceauth")
                        .then(Commands.argument("player", EntityArgument.player())
                                .executes(AdminCommands::forceAuth))));
    }

    private static int reload(CommandContext<CommandSourceStack> context) {
        context.getSource().sendSuccess(() -> LoginText.component(XiyusLoginLanguageConfig.ADMIN_RELOAD_UNIMPLEMENTED), false);
        return 1;
    }

    private static int playerInfo(CommandContext<CommandSourceStack> context) {
        String playerName = StringArgumentType.getString(context, "player");
        AuthManager authManager = AuthManager.getInstance();
        PlayerDataManager.PlayerData playerData = authManager.getPlayerDataManager().getPlayerData(playerName);

        if (playerData == null) {
            context.getSource().sendFailure(LoginText.component(
                    XiyusLoginLanguageConfig.ADMIN_PLAYER_NOT_REGISTERED,
                    "player", playerName
            ));
            return 0;
        }

        String registeredAt = playerData.getRegistrationTime() != null
                ? playerData.getRegistrationTime()
                : LoginText.text(XiyusLoginLanguageConfig.ADMIN_UNKNOWN_TIME);
        String lastLogin = playerData.getLastLoginTime() != null
                ? playerData.getLastLoginTime()
                : LoginText.text(XiyusLoginLanguageConfig.ADMIN_NEVER_LOGIN);

        context.getSource().sendSuccess(() -> LoginText.component(
                XiyusLoginLanguageConfig.ADMIN_PLAYER_INFO,
                "player", playerData.getUsername(),
                "uuid", playerData.getUuid(),
                "registered_at", registeredAt,
                "last_login", lastLogin,
                "login_count", playerData.getLoginCount()
        ), false);
        return 1;
    }

    private static int resetPassword(CommandContext<CommandSourceStack> context) {
        String playerName = StringArgumentType.getString(context, "player");
        String newPassword = StringArgumentType.getString(context, "newPassword");

        AuthManager authManager = AuthManager.getInstance();
        PlayerDataManager.PlayerData playerData = authManager.getPlayerDataManager().getPlayerData(playerName);

        if (playerData == null) {
            context.getSource().sendFailure(LoginText.component(
                    XiyusLoginLanguageConfig.ADMIN_PLAYER_NOT_REGISTERED,
                    "player", playerName
            ));
            return 0;
        }

        if (authManager.getPlayerDataManager().resetPassword(playerName, newPassword)) {
            authManager.clearIpSessions(playerName);
            context.getSource().sendSuccess(() -> LoginText.component(
                    XiyusLoginLanguageConfig.ADMIN_RESET_PASSWORD_SUCCESS,
                    "player", playerName
            ), false);
            return 1;
        } else {
            context.getSource().sendFailure(LoginText.component(XiyusLoginLanguageConfig.ADMIN_RESET_PASSWORD_FAILED));
            return 0;
        }
    }

    private static int unregister(CommandContext<CommandSourceStack> context) {
        context.getSource().sendSuccess(() -> LoginText.component(XiyusLoginLanguageConfig.ADMIN_UNREGISTER_UNIMPLEMENTED), false);
        return 1;
    }

    private static int listResetRequests(CommandContext<CommandSourceStack> context) {
        AuthManager authManager = AuthManager.getInstance();
        Map<String, PlayerDataManager.PasswordResetRequest> requests =
                authManager.getPlayerDataManager().getPasswordResetRequests();

        if (requests.isEmpty()) {
            context.getSource().sendSuccess(() -> LoginText.component(XiyusLoginLanguageConfig.ADMIN_NO_RESET_REQUESTS), false);
            return 1;
        }

        MutableComponent message = LoginText.component(XiyusLoginLanguageConfig.ADMIN_RESET_REQUESTS_HEADER);

        for (Map.Entry<String, PlayerDataManager.PasswordResetRequest> entry : requests.entrySet()) {
            PlayerDataManager.PasswordResetRequest request = entry.getValue();

            MutableComponent requestLine = LoginText.component(
                    XiyusLoginLanguageConfig.ADMIN_RESET_REQUEST_LINE,
                    "player", request.getUsername(),
                    "time", request.getRequestTime(),
                    "reason", request.getReason(),
                    "new_password", LoginText.text(XiyusLoginLanguageConfig.ADMIN_RESET_PASSWORD_HIDDEN)
            );

            MutableComponent approveButton = LoginText.component(XiyusLoginLanguageConfig.ADMIN_APPROVE_BUTTON)
                    .setStyle(Style.EMPTY
                            .withClickEvent(new ClickEvent(
                                    ClickEvent.Action.RUN_COMMAND,
                                    "/xiyuslogin approve " + request.getUsername()
                            ))
                            .withHoverEvent(new HoverEvent(
                                    HoverEvent.Action.SHOW_TEXT,
                                    LoginText.component(
                                            XiyusLoginLanguageConfig.ADMIN_APPROVE_HOVER,
                                            "player", request.getUsername()
                                    )
                            ))
                    );

            MutableComponent rejectButton = LoginText.component(XiyusLoginLanguageConfig.ADMIN_REJECT_BUTTON)
                    .setStyle(Style.EMPTY
                            .withClickEvent(new ClickEvent(
                                    ClickEvent.Action.RUN_COMMAND,
                                    "/xiyuslogin reject " + request.getUsername()
                            ))
                            .withHoverEvent(new HoverEvent(
                                    HoverEvent.Action.SHOW_TEXT,
                                    LoginText.component(
                                            XiyusLoginLanguageConfig.ADMIN_REJECT_HOVER,
                                            "player", request.getUsername()
                                    )
                            ))
                    );

            requestLine.append(approveButton)
                    .append(rejectButton)
                    .append(LoginText.component(XiyusLoginLanguageConfig.ADMIN_RESET_REQUEST_SEPARATOR));
            message.append(requestLine);
        }

        context.getSource().sendSuccess(() -> message, false);
        return 1;
    }

    private static int approveReset(CommandContext<CommandSourceStack> context) {
        String username = StringArgumentType.getString(context, "username");
        AuthManager authManager = AuthManager.getInstance();

        if (authManager.getPlayerDataManager().approvePasswordReset(username)) {
            authManager.clearIpSessions(username);
            context.getSource().sendSuccess(() -> LoginText.component(
                    XiyusLoginLanguageConfig.ADMIN_APPROVE_SUCCESS,
                    "player", username
            ), false);

            ServerPlayer player = context.getSource().getServer().getPlayerList().getPlayerByName(username);
            if (player != null) {
                player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.ADMIN_APPROVE_NOTIFY));
            }

            return 1;
        } else {
            context.getSource().sendFailure(LoginText.component(XiyusLoginLanguageConfig.ADMIN_APPROVE_NOT_FOUND));
            return 0;
        }
    }

    private static int rejectReset(CommandContext<CommandSourceStack> context) {
        String username = StringArgumentType.getString(context, "username");
        AuthManager authManager = AuthManager.getInstance();

        if (authManager.getPlayerDataManager().rejectPasswordReset(username)) {
            context.getSource().sendSuccess(() -> LoginText.component(
                    XiyusLoginLanguageConfig.ADMIN_REJECT_SUCCESS,
                    "player", username
            ), false);

            ServerPlayer player = context.getSource().getServer().getPlayerList().getPlayerByName(username);
            if (player != null) {
                player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.ADMIN_REJECT_NOTIFY));
            }

            return 1;
        } else {
            context.getSource().sendFailure(LoginText.component(XiyusLoginLanguageConfig.ADMIN_REJECT_NOT_FOUND));
            return 0;
        }
    }

    private static int forceAuth(CommandContext<CommandSourceStack> context) {
        try {
            if (context.getSource().getEntity() instanceof ServerPlayer executor
                    && FreezeManager.isFrozen(executor.getUUID())) {
                context.getSource().sendFailure(LoginText.component(XiyusLoginLanguageConfig.FROZEN_COMMAND_BLOCKED));
                return 0;
            }

            ServerPlayer player = EntityArgument.getPlayer(context, "player");
            AuthManager authManager = AuthManager.getInstance();
            authManager.setPlayerAuthenticated(player.getUUID(), true);
            authManager.rememberIpSession(player);
            authManager.getFreezeManager().unfreezePlayer(player.getUUID());

            context.getSource().sendSuccess(() -> LoginText.component(
                    XiyusLoginLanguageConfig.ADMIN_FORCE_AUTH_SUCCESS,
                    "player", player.getName().getString()
            ), false);

            player.sendSystemMessage(LoginText.component(XiyusLoginLanguageConfig.ADMIN_FORCE_AUTH_NOTIFY));
            return 1;
        } catch (Exception e) {
            context.getSource().sendFailure(LoginText.component(
                    XiyusLoginLanguageConfig.ADMIN_FORCE_AUTH_FAILED,
                    "error", e.getMessage()
            ));
            return 0;
        }
    }
}
