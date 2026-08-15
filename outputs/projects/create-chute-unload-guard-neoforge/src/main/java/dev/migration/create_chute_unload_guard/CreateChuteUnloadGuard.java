package dev.migration.create_chute_unload_guard;

import com.mojang.logging.LogUtils;
import net.neoforged.fml.common.Mod;
import org.slf4j.Logger;

@Mod(CreateChuteUnloadGuard.MOD_ID)
public final class CreateChuteUnloadGuard {
    public static final String MOD_ID = "create_chute_unload_guard";
    private static final Logger LOGGER = LogUtils.getLogger();

    public CreateChuteUnloadGuard() {
        LOGGER.info("Create 6.0.10 chute unload guard enabled");
    }
}
