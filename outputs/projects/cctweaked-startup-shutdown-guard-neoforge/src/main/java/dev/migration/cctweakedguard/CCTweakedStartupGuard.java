package dev.migration.cctweakedguard;

import com.mojang.logging.LogUtils;
import net.neoforged.fml.common.Mod;
import org.slf4j.Logger;

@Mod(CCTweakedStartupGuard.MOD_ID)
public final class CCTweakedStartupGuard {
    public static final String MOD_ID = "cctweaked_startup_guard";
    public static final long ORIGINAL_STARTUP_TIMEOUT_SECONDS = 30L;
    public static final long EXTENDED_STARTUP_TIMEOUT_SECONDS = 120L;
    public static final long NORMAL_LUA_TIMEOUT_MILLIS = 7_000L;
    public static final long NORMAL_LUA_ABORT_GRACE_MILLIS = 1_500L;
    public static final long ORIGINAL_SHUTDOWN_TIMEOUT_SECONDS = 1L;
    public static final long EXTENDED_SHUTDOWN_TIMEOUT_SECONDS = 30L;

    private static final Logger LOGGER = LogUtils.getLogger();

    public CCTweakedStartupGuard() {
        LOGGER.info("CC:Tweaked 1.120.0 startup/shutdown guard enabled");
    }
}
