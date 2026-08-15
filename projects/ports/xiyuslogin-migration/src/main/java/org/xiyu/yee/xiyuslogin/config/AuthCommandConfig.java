package org.xiyu.yee.xiyuslogin.config;

import org.xiyu.yee.xiyuslogin.Xiyuslogin;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public final class AuthCommandConfig {
    private static final Pattern WHITESPACE = Pattern.compile("\\s");
    private static final List<String> DEFAULT_LOGIN_COMMANDS = List.of("login", "lg");
    private static final List<String> DEFAULT_REGISTER_COMMANDS = List.of("register", "reg");
    private static final String PASSWORD_RESET_COMMAND = "psforget";

    private AuthCommandConfig() {
    }

    public static boolean isValidAlias(Object value) {
        if (!(value instanceof String alias)) {
            return false;
        }

        String trimmed = alias.trim();
        return !trimmed.isEmpty()
                && trimmed.equals(alias)
                && !trimmed.startsWith("/")
                && !WHITESPACE.matcher(trimmed).find();
    }

    public static List<String> getLoginCommands() {
        return normalize(DEFAULT_LOGIN_COMMANDS, XiyusLoginConfig.LOGIN_ALIASES.get());
    }

    public static List<String> getRegisterCommands() {
        return normalize(DEFAULT_REGISTER_COMMANDS, XiyusLoginConfig.REGISTER_ALIASES.get());
    }

    public static Set<String> getAllowedFrozenCommands() {
        LinkedHashSet<String> commands = new LinkedHashSet<>();
        commands.addAll(getLoginCommands());
        commands.addAll(getRegisterCommands());
        commands.add(PASSWORD_RESET_COMMAND);
        return commands;
    }

    public static boolean isAllowedFrozenCommand(String commandName) {
        String normalized = normalizeCommandName(commandName);
        return getAllowedFrozenCommands().contains(normalized);
    }

    public static String firstRegisterCommand() {
        return "/" + getRegisterCommands().get(0);
    }

    public static String loginCommandUsages() {
        return commandUsages(getLoginCommands(), LoginText.text(XiyusLoginLanguageConfig.LOGIN_COMMAND_ARGUMENTS));
    }

    public static String registerCommandUsages() {
        return commandUsages(getRegisterCommands(), LoginText.text(XiyusLoginLanguageConfig.REGISTER_COMMAND_ARGUMENTS));
    }

    public static String normalizeCommandName(String commandName) {
        String normalized = commandName == null ? "" : commandName.trim().toLowerCase(Locale.ROOT);
        return normalized.startsWith("/") ? normalized.substring(1) : normalized;
    }

    private static List<String> normalize(Collection<String> defaults, List<? extends String> aliases) {
        LinkedHashSet<String> commands = new LinkedHashSet<>(defaults);
        for (String alias : aliases) {
            if (!isValidAlias(alias)) {
                Xiyuslogin.LOGGER.warn("Ignoring invalid auth command alias '{}'", alias);
                continue;
            }
            commands.add(alias.toLowerCase(Locale.ROOT));
        }
        return List.copyOf(commands);
    }

    private static String commandUsages(Collection<String> commands, String arguments) {
        String suffix = arguments == null || arguments.isBlank() ? "" : " " + arguments;
        return commands.stream()
                .map(command -> "/" + command + suffix)
                .collect(Collectors.joining(LoginText.text(XiyusLoginLanguageConfig.COMMAND_USAGE_SEPARATOR)));
    }
}
