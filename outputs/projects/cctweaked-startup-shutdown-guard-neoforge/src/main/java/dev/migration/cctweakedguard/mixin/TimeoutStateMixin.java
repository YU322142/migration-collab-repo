package dev.migration.cctweakedguard.mixin;

import dan200.computercraft.core.computer.TimeoutState;
import dev.migration.cctweakedguard.CCTweakedStartupGuard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.Constant;
import org.spongepowered.asm.mixin.injection.ModifyConstant;

@Mixin(value = TimeoutState.class, remap = false)
abstract class TimeoutStateMixin {
    @ModifyConstant(
        method = "<clinit>()V",
        constant = @Constant(longValue = CCTweakedStartupGuard.ORIGINAL_STARTUP_TIMEOUT_SECONDS),
        require = 1,
        allow = 1,
        remap = false
    )
    private static long cctweakedStartupGuard$extendStartupTimeout(long originalSeconds) {
        return CCTweakedStartupGuard.EXTENDED_STARTUP_TIMEOUT_SECONDS;
    }
}
