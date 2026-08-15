package dev.migration.cctweakedguard.mixin;

import dan200.computercraft.shared.computer.core.ServerContext;
import dev.migration.cctweakedguard.CCTweakedStartupGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.Constant;
import org.spongepowered.asm.mixin.injection.ModifyConstant;

@Mixin(value = ServerContext.class, remap = false)
abstract class ServerContextMixin {
    @ModifyConstant(
        method = "close()V",
        constant = @Constant(longValue = CCTweakedStartupGuard.ORIGINAL_SHUTDOWN_TIMEOUT_SECONDS),
        require = 1,
        allow = 1,
        remap = false
    )
    private static long cctweakedStartupGuard$extendShutdownTimeout(long original) {
        return CCTweakedStartupGuard.EXTENDED_SHUTDOWN_TIMEOUT_SECONDS;
    }
}
