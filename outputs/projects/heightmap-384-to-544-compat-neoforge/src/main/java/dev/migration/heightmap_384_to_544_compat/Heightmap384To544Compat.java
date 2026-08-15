package dev.migration.heightmap_384_to_544_compat;

import com.mojang.logging.LogUtils;
import net.minecraft.world.level.ChunkPos;
import net.neoforged.fml.common.Mod;
import org.slf4j.Logger;

import java.util.concurrent.atomic.AtomicInteger;

@Mod(Heightmap384To544Compat.MOD_ID)
public final class Heightmap384To544Compat {
    public static final String MOD_ID = "heightmap_384_to_544_compat";
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final int MAX_REJECTION_WARNINGS = 8;
    private static final AtomicInteger REJECTION_WARNINGS = new AtomicInteger();
    private static final AtomicInteger CONVERSION_NOTICES = new AtomicInteger();

    public Heightmap384To544Compat() {
        LOGGER.info(
                "Heightmap 384-to-544 compatibility enabled: legacy 37-long arrays are repacked in memory; no chunk is forced dirty"
        );
    }

    public static void noteConversion(ChunkPos chunkPos) {
        if (CONVERSION_NOTICES.getAndIncrement() == 0) {
            LOGGER.info(
                    "Repacked a legacy 384-height heightmap for chunk {} into the 544-height layout; further successful conversions are quiet",
                    chunkPos
            );
        }
    }

    public static void warnRejected(ChunkPos chunkPos, String diagnostic) {
        int warningIndex = REJECTION_WARNINGS.getAndIncrement();
        if (warningIndex < MAX_REJECTION_WARNINGS) {
            LOGGER.warn(
                    "Left heightmap data unchanged for chunk {} and deferred to vanilla: {}",
                    chunkPos,
                    diagnostic
            );
        } else if (warningIndex == MAX_REJECTION_WARNINGS) {
            LOGGER.warn("Further malformed legacy heightmap diagnostics are suppressed");
        }
    }
}
