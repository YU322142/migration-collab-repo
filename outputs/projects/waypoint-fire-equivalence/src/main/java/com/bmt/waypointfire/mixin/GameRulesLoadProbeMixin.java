package com.bmt.waypointfire.mixin;

import com.bmt.waypointfire.CompatGameRules;
import com.mojang.serialization.DynamicLike;
import net.minecraft.world.level.GameRules;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(GameRules.class)
public abstract class GameRulesLoadProbeMixin {
    @Inject(method = "<init>(Lcom/mojang/serialization/DynamicLike;)V", at = @At("TAIL"))
    private void waypointFire$captureLoad(DynamicLike<?> source, CallbackInfo callback) {
        CompatGameRules.captureLoad((GameRules) (Object) this, source);
    }
}
