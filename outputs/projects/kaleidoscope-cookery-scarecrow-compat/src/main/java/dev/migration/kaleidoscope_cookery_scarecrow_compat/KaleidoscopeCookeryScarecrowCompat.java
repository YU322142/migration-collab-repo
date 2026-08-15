package dev.migration.kaleidoscope_cookery_scarecrow_compat;

import com.mojang.logging.LogUtils;
import net.neoforged.fml.common.Mod;
import org.slf4j.Logger;

@Mod(KaleidoscopeCookeryScarecrowCompat.MOD_ID)
public final class KaleidoscopeCookeryScarecrowCompat {
    public static final String MOD_ID = "kaleidoscope_cookery_scarecrow_compat";
    private static final Logger LOGGER = LogUtils.getLogger();

    public KaleidoscopeCookeryScarecrowCompat() {
        LOGGER.info("Kaleidoscope Cookery legacy Scarecrow NBT compatibility enabled");
    }
}

