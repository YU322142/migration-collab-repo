package org.xiyu.yee.xiyuslogin.config;

import net.neoforged.neoforge.common.ModConfigSpec;

import java.util.List;

public class XiyusLoginConfig {
    private static final ModConfigSpec.Builder BUILDER = new ModConfigSpec.Builder();

    // 冻结时间配置（秒）
    public static final ModConfigSpec.IntValue FREEZE_DURATION = BUILDER
            .comment("玩家注册或登录时的冻结时间（秒），期间玩家无法移动")
            .defineInRange("freezeDuration", 60, 10, 300);

    // 密码错误次数限制
    public static final ModConfigSpec.IntValue PASSWORDERROR = BUILDER
            .comment("允许密码错误的最大次数（超过该次数将拒绝继续登录尝试）")
            .defineInRange("passwordError", 3, 0, 10);

    // 最大密码长度
    public static final ModConfigSpec.IntValue MAX_PASSWORD_LENGTH = BUILDER
            .comment("密码的最大长度限制（字符数）")
            .defineInRange("maxPasswordLength", 32, 4, 64);

    // 最小密码长度
    public static final ModConfigSpec.IntValue MIN_PASSWORD_LENGTH = BUILDER
            .comment("密码的最小长度限制（字符数）")
            .defineInRange("minPasswordLength", 4, 1, 32);

    public static final ModConfigSpec.ConfigValue<List<? extends String>> LOGIN_ALIASES = BUILDER
            .comment("额外登录指令别名。默认 /login 和 /lg 始终保留；这里不要写 /，也不要包含空格。")
            .defineListAllowEmpty("loginAliases", List.of(), AuthCommandConfig::isValidAlias);

    public static final ModConfigSpec.ConfigValue<List<? extends String>> REGISTER_ALIASES = BUILDER
            .comment("额外注册指令别名。默认 /register 和 /reg 始终保留；这里不要写 /，也不要包含空格。")
            .defineListAllowEmpty("registerAliases", List.of(), AuthCommandConfig::isValidAlias);

    public static final ModConfigSpec.EnumValue<AuthViewMode> AUTH_VIEW_MODE = BUILDER
            .comment("Unauthenticated client view. INVENTORY_ONLY hides inventory only; FAKE_POSITION also sends fake coordinates; FLAT_CHUNK sends temporary flat fake chunks; VOID_UNLOADED sends fake coordinates and unloads nearby real chunks client-side.")
            .defineEnum("authViewMode", AuthViewMode.INVENTORY_ONLY);

    public static final ModConfigSpec.DoubleValue FAKE_POSITION_X = BUILDER
            .comment("未登录假视图坐标 X，仅 authViewMode 为 FAKE_POSITION 或 VOID_UNLOADED 时生效。")
            .defineInRange("fakePositionX", 0.5D, -3.0E7D, 3.0E7D);

    public static final ModConfigSpec.DoubleValue FAKE_POSITION_Y = BUILDER
            .comment("未登录假视图坐标 Y，仅 authViewMode 为 FAKE_POSITION 或 VOID_UNLOADED 时生效。")
            .defineInRange("fakePositionY", 80.0D, -2048.0D, 4096.0D);

    public static final ModConfigSpec.DoubleValue FAKE_POSITION_Z = BUILDER
            .comment("未登录假视图坐标 Z，仅 authViewMode 为 FAKE_POSITION 或 VOID_UNLOADED 时生效。")
            .defineInRange("fakePositionZ", 0.5D, -3.0E7D, 3.0E7D);

    public static final ModConfigSpec.IntValue FAKE_CHUNK_UNLOAD_RADIUS = BUILDER
            .comment("VOID_UNLOADED 模式下反复卸载玩家真实位置周围的客户端区块半径。数值越大越像虚空，但网络包更多。")
            .defineInRange("fakeChunkUnloadRadius", 3, 0, 10);

    public static final ModConfigSpec.IntValue FAKE_FLAT_CHUNK_RADIUS = BUILDER
            .comment("FLAT_CHUNK mode fake chunk radius around the fake position. 0 sends one chunk, 1 sends 3x3 chunks.")
            .defineInRange("fakeFlatChunkRadius", 1, 0, 4);

    public static final ModConfigSpec.IntValue FAKE_FLAT_PLATFORM_Y = BUILDER
            .comment("FLAT_CHUNK mode platform Y level. Keep it near fakePositionY so the client camera sees the flat view.")
            .defineInRange("fakeFlatPlatformY", 79, -2048, 4096);

    public static final ModConfigSpec.ConfigValue<String> FAKE_FLAT_BLOCK = BUILDER
            .comment("FLAT_CHUNK mode block id used for the fake flat layer. Unknown ids fall back to minecraft:bedrock.")
            .define("fakeFlatBlock", "minecraft:bedrock");

    public static final ModConfigSpec.BooleanValue PROTECT_UNAUTHENTICATED_PLAYERS = BUILDER
            .comment("未登录/注册玩家是否无敌。开启后会取消服务器对这类玩家的所有伤害，并清理火焰和摔落距离。")
            .define("protectUnauthenticatedPlayers", true);

    public static final ModConfigSpec.BooleanValue LEGALIZE_UNAUTHENTICATED_FLOATING = BUILDER
            .comment("未登录/注册玩家悬空时是否视为合法。开启后会在冻结期间禁用重力、清掉掉落距离，并重置服务端浮空踢出计数。")
            .define("legalizeUnauthenticatedFloating", true);

    public static final ModConfigSpec.BooleanValue BLIND_UNAUTHENTICATED_PLAYERS = BUILDER
            .comment("未登录/注册玩家是否施加失明效果。默认关闭以保持 EasyAuth 的可见世界行为。")
            .define("blindUnauthenticatedPlayers", false);

    public static final ModConfigSpec.BooleanValue ENABLE_IP_SESSION = BUILDER
            .comment("启用同一用户名 + 同一 IP 在有效期内重进自动恢复登录会话。")
            .define("enableIpSession", false);

    public static final ModConfigSpec.IntValue IP_SESSION_DURATION_SECONDS = BUILDER
            .comment("IP 登录会话有效期（秒）。超过后重新进服仍需登录；设为 0 等同关闭。")
            .defineInRange("ipSessionDurationSeconds", 300, 0, 86400);

    public static final ModConfigSpec.BooleanValue ENABLE_PASSWORD_RESET_COMMAND = BUILDER
            .comment("Enable the /psforget chat command. It is disabled by default because vanilla command input is retained in client history.")
            .define("enablePasswordResetCommand", false);
    
    public static final ModConfigSpec SPEC = BUILDER.build();

    public enum AuthViewMode {
        INVENTORY_ONLY,
        FAKE_POSITION,
        FLAT_CHUNK,
        VOID_UNLOADED
    }
}
