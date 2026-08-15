package com.antigravity.create_dynamic_blocking.mixin;

import com.antigravity.create_dynamic_blocking.DynamicBlockingHandler;
import com.simibubi.create.content.trains.entity.Navigation;
import com.simibubi.create.content.trains.entity.Train;
import com.simibubi.create.content.trains.station.GlobalStation;
import net.minecraft.world.level.Level;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = Navigation.class, remap = false)
public abstract class NavigationMixin {
    @Shadow
    public Train train;

    @Shadow
    public GlobalStation destination;

    @Inject(method = "tick", at = @At("RETURN"))
    private void createDynamicBlocking$afterTick(Level level, CallbackInfo callbackInfo) {
        if (destination == null || train.graph == null) {
            return;
        }
        DynamicBlockingHandler.enforceSpacing(train, train.currentlyBackwards);
    }
}
