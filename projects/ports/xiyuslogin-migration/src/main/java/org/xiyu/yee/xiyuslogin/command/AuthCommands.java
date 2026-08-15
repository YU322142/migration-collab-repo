package org.xiyu.yee.xiyuslogin.command;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.builder.LiteralArgumentBuilder;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.server.level.ServerPlayer;
import org.xiyu.yee.xiyuslogin.config.AuthCommandConfig;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginConfig;
import org.xiyu.yee.xiyuslogin.manager.AuthManager;

public class AuthCommands {

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        for (String command : AuthCommandConfig.getLoginCommands()) {
            dispatcher.register(loginCommand(command));
        }

        for (String command : AuthCommandConfig.getRegisterCommands()) {
            dispatcher.register(registerCommand(command));
        }

        if (XiyusLoginConfig.ENABLE_PASSWORD_RESET_COMMAND.get()) {
            dispatcher.register(Commands.literal("psforget")
                    .then(Commands.argument("reason", StringArgumentType.string())
                            .then(Commands.argument("newPassword", StringArgumentType.string())
                                    .executes(AuthCommands::passwordForget))));
        }
    }

    private static LiteralArgumentBuilder<CommandSourceStack> loginCommand(String command) {
        return Commands.literal(command)
                .then(Commands.argument("password", StringArgumentType.string())
                        .executes(AuthCommands::login));
    }

    private static LiteralArgumentBuilder<CommandSourceStack> registerCommand(String command) {
        return Commands.literal(command)
                .then(Commands.argument("password", StringArgumentType.string())
                        .then(Commands.argument("confirmPassword", StringArgumentType.string())
                                .executes(AuthCommands::register)));
    }

    private static int login(CommandContext<CommandSourceStack> context) {
        if (!(context.getSource().getEntity() instanceof ServerPlayer player)) {
            return 0;
        }

        String password = StringArgumentType.getString(context, "password");
        AuthManager.getInstance().loginPlayer(player, password);
        return 1;
    }

    private static int register(CommandContext<CommandSourceStack> context) {
        if (!(context.getSource().getEntity() instanceof ServerPlayer player)) {
            return 0;
        }

        String password = StringArgumentType.getString(context, "password");
        String confirmPassword = StringArgumentType.getString(context, "confirmPassword");

        AuthManager.getInstance().registerPlayer(player, password, confirmPassword);
        return 1;
    }

    private static int passwordForget(CommandContext<CommandSourceStack> context) {
        if (!(context.getSource().getEntity() instanceof ServerPlayer player)) {
            return 0;
        }

        String reason = StringArgumentType.getString(context, "reason");
        String newPassword = StringArgumentType.getString(context, "newPassword");

        AuthManager.getInstance().submitPasswordResetRequest(player, reason, newPassword);
        return 1;
    }
}
