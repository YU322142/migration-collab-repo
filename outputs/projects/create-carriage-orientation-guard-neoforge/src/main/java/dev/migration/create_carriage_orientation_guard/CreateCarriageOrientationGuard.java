package dev.migration.create_carriage_orientation_guard;

import com.mojang.logging.LogUtils;
import net.minecraft.core.Direction;
import net.neoforged.fml.common.Mod;
import org.slf4j.Logger;

import java.util.UUID;

@Mod(CreateCarriageOrientationGuard.MOD_ID)
public final class CreateCarriageOrientationGuard {
    public static final String MOD_ID = "create_carriage_orientation_guard";
    private static final Logger LOGGER = LogUtils.getLogger();

    public CreateCarriageOrientationGuard() {
        LOGGER.info("Create 6.0.10 carriage orientation runtime guard enabled");
    }

    public static void warnFallback(
            UUID entityUuid,
            Direction raw,
            Direction assemblyDirection,
            Direction resolved
    ) {
        LOGGER.warn(
                "Legacy/invalid carriage InitialOrientation detected for {}: raw={}, assembly={}, resolved={}. "
                        + "This guard is read-only and non-persistent; conversion must normalize the saved enum.",
                entityUuid,
                raw,
                assemblyDirection,
                resolved
        );
    }
}
