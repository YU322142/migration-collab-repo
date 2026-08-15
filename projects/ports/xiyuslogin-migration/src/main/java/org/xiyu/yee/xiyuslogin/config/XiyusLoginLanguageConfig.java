package org.xiyu.yee.xiyuslogin.config;

import net.neoforged.neoforge.common.ModConfigSpec;

public class XiyusLoginLanguageConfig {
    private static final ModConfigSpec.Builder BUILDER = new ModConfigSpec.Builder();

    public static final ModConfigSpec.ConfigValue<String> LOGIN_COMMAND_ARGUMENTS = define("loginCommandArguments", "<密码>");
    public static final ModConfigSpec.ConfigValue<String> REGISTER_COMMAND_ARGUMENTS = define("registerCommandArguments", "<密码> <确认密码>");
    public static final ModConfigSpec.ConfigValue<String> COMMAND_USAGE_SEPARATOR = define("commandUsageSeparator", " 或 ");

    public static final ModConfigSpec.ConfigValue<String> WELCOME_LOGIN = define("welcomeLogin", "&e欢迎回来！请输入密码登录：{login_commands}");
    public static final ModConfigSpec.ConfigValue<String> WELCOME_REGISTER = define("welcomeRegister", "&a欢迎！请注册账户：{register_commands}");
    public static final ModConfigSpec.ConfigValue<String> FORGET_PASSWORD_PREFIX = define("forgetPasswordPrefix", "&6忘记密码？");
    public static final ModConfigSpec.ConfigValue<String> FORGET_PASSWORD_SUGGEST_COMMAND = define("forgetPasswordSuggestCommand", "/psforget \"忘记原因\" 新密码");
    public static final ModConfigSpec.ConfigValue<String> FORGET_PASSWORD_HOVER = define("forgetPasswordHover", "&e点击申请重置密码\\n&7格式：/psforget \"忘记原因\" 新密码");
    public static final ModConfigSpec.ConfigValue<String> FORGET_PASSWORD_SUFFIX = define("forgetPasswordSuffix", " &e点我申请重置");

    public static final ModConfigSpec.ConfigValue<String> PASSWORD_TOO_SHORT = define("passwordTooShort", "&c密码太短！最少需要 {min} 个字符。");
    public static final ModConfigSpec.ConfigValue<String> PASSWORD_TOO_LONG = define("passwordTooLong", "&c密码太长！最多允许 {max} 个字符。");
    public static final ModConfigSpec.ConfigValue<String> PASSWORD_MISMATCH = define("passwordMismatch", "&c两次输入的密码不一致！");
    public static final ModConfigSpec.ConfigValue<String> USERNAME_REGISTERED = define("usernameRegistered", "&c该用户名已被注册！");
    public static final ModConfigSpec.ConfigValue<String> REGISTER_SUCCESS = define("registerSuccess", "&a注册成功！欢迎加入服务器！");
    public static final ModConfigSpec.ConfigValue<String> REGISTER_FAILED = define("registerFailed", "&c注册失败！请重试。");
    public static final ModConfigSpec.ConfigValue<String> USERNAME_NOT_REGISTERED_WITH_COMMAND = define("usernameNotRegisteredWithCommand", "&c该用户名未注册！请使用 {register_command} 注册。");
    public static final ModConfigSpec.ConfigValue<String> USERNAME_NOT_REGISTERED = define("usernameNotRegistered", "&c该用户名未注册！");
    public static final ModConfigSpec.ConfigValue<String> LOGIN_SUCCESS = define("loginSuccess", "&a登录成功！欢迎回来！");
    public static final ModConfigSpec.ConfigValue<String> SESSION_RESTORED = define("sessionRestored", "&a已恢复登录会话，欢迎回来！");
    public static final ModConfigSpec.ConfigValue<String> PASSWORD_ERROR_FIRST = define("passwordErrorFirst", "&c密码错误！超过{max}次自动断开连接！");
    public static final ModConfigSpec.ConfigValue<String> PASSWORD_ERROR_COUNT = define("passwordErrorCount", "&c密码错误！第{count}次！");
    public static final ModConfigSpec.ConfigValue<String> PASSWORD_ERROR_KICK = define("passwordErrorKick", "&c密码错误次数过多，错误次数请不要超过 {max}，否则自动断开连接。");
    public static final ModConfigSpec.ConfigValue<String> PASSWORD_RESET_LENGTH = define("passwordResetLength", "&c新密码长度必须在 {min} 到 {max} 个字符之间！");
    public static final ModConfigSpec.ConfigValue<String> PASSWORD_RESET_SUBMITTED = define("passwordResetSubmitted", "&a密码重置请求已提交！请等待管理员审核。\\n&7原因：{reason}");
    public static final ModConfigSpec.ConfigValue<String> AUTH_CHAT_BLOCKED = define("authChatBlocked", "&c你需要先完成身份验证才能发送聊天消息！");
    public static final ModConfigSpec.ConfigValue<String> FROZEN_COMMAND_BLOCKED = define("frozenCommandBlocked", "&c你已被冻结，无法执行此命令！");
    public static final ModConfigSpec.ConfigValue<String> FREEZE_TIMEOUT = define("freezeTimeout", "&c验证超时！请在 {seconds} 秒内完成注册或登录。");

    public static final ModConfigSpec.ConfigValue<String> ADMIN_RELOAD_UNIMPLEMENTED = define("adminReloadUnimplemented", "&a配置重载功能暂未实现");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_PLAYER_NOT_REGISTERED = define("adminPlayerNotRegistered", "&c玩家 {player} 未注册");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_PLAYER_INFO = define("adminPlayerInfo", "&6=== 玩家信息：{player} ===\\n&fUUID: &e{uuid}\\n&f注册时间: &e{registered_at}\\n&f最后登录: &e{last_login}\\n&f登录次数: &e{login_count}");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_UNKNOWN_TIME = define("adminUnknownTime", "未知");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_NEVER_LOGIN = define("adminNeverLogin", "从未登录");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_RESET_PASSWORD_SUCCESS = define("adminResetPasswordSuccess", "&a已为玩家 {player} 重置密码");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_RESET_PASSWORD_FAILED = define("adminResetPasswordFailed", "&c重置密码失败");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_UNREGISTER_UNIMPLEMENTED = define("adminUnregisterUnimplemented", "&e注销功能暂未实现");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_NO_RESET_REQUESTS = define("adminNoResetRequests", "&e当前没有密码重置请求");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_RESET_REQUESTS_HEADER = define("adminResetRequestsHeader", "&6=== 密码重置请求列表 ===\\n");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_RESET_REQUEST_LINE = define("adminResetRequestLine", "&f玩家: &e{player} &f时间: &e{time}\\n&f原因: &7{reason}\\n");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_RESET_PASSWORD_HIDDEN = define("adminResetPasswordHidden", "&8[hidden]");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_APPROVE_BUTTON = define("adminApproveButton", "&a[批准]");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_APPROVE_HOVER = define("adminApproveHover", "&a批准 {player} 的密码重置请求");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_REJECT_BUTTON = define("adminRejectButton", " &c[拒绝]");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_REJECT_HOVER = define("adminRejectHover", "&c拒绝 {player} 的密码重置请求");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_RESET_REQUEST_SEPARATOR = define("adminResetRequestSeparator", "\\n&8========================================\\n");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_APPROVE_SUCCESS = define("adminApproveSuccess", "&a已批准玩家 {player} 的密码重置请求");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_APPROVE_NOTIFY = define("adminApproveNotify", "&a您的密码重置请求已被批准！新密码已生效。");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_APPROVE_NOT_FOUND = define("adminApproveNotFound", "&c未找到该玩家的密码重置请求");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_REJECT_SUCCESS = define("adminRejectSuccess", "&c已拒绝玩家 {player} 的密码重置请求");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_REJECT_NOTIFY = define("adminRejectNotify", "&c您的密码重置请求已被拒绝。");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_REJECT_NOT_FOUND = define("adminRejectNotFound", "&c未找到该玩家的密码重置请求");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_FORCE_AUTH_SUCCESS = define("adminForceAuthSuccess", "&a已强制验证玩家 {player}");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_FORCE_AUTH_NOTIFY = define("adminForceAuthNotify", "&a管理员已为您完成身份验证！");
    public static final ModConfigSpec.ConfigValue<String> ADMIN_FORCE_AUTH_FAILED = define("adminForceAuthFailed", "&c强制验证失败：{error}");

    public static final ModConfigSpec SPEC = BUILDER.build();

    private static ModConfigSpec.ConfigValue<String> define(String path, String defaultValue) {
        return BUILDER.define(path, defaultValue);
    }
}
