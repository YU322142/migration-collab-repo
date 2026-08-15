package com.bmt.respawnpitchcompat.mixin;

import com.bmt.respawnpitchcompat.CompatSpawnCommand;
import com.mojang.brigadier.CommandDispatcher;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.server.commands.SetSpawnCommand;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(SetSpawnCommand.class)
public abstract class SetSpawnCommandMixin {
    @Inject(method = "register", at = @At("HEAD"), cancellable = true)
    private static void respawnPitchCompat$register(
            CommandDispatcher<CommandSourceStack> dispatcher,
            CallbackInfo callback) {
        CompatSpawnCommand.register(dispatcher);
        callback.cancel();
    }
}
