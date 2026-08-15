package dev.migration.create_chute_unload_guard.mixin;

import com.simibubi.create.content.logistics.chute.AbstractChuteBlock;
import com.simibubi.create.content.logistics.chute.ChuteBlockEntity;
import dev.migration.create_chute_unload_guard.ChuteGuardDecision;
import net.minecraft.world.level.Level;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = ChuteBlockEntity.class, remap = false)
public abstract class ChuteBlockEntityMixin {
    @Inject(method = "onAdded", at = @At("HEAD"), cancellable = true, remap = false)
    private void createChuteUnloadGuard$guardOnAdded(CallbackInfo callbackInfo) {
        ChuteBlockEntity chute = (ChuteBlockEntity) (Object) this;
        Level level = chute.getLevel();
        boolean chuteAtPosition = level != null
                && AbstractChuteBlock.isChute(level.getBlockState(chute.getBlockPos()));
        if (!ChuteGuardDecision.shouldRemove(level != null, chuteAtPosition)) {
            return;
        }
        chute.setRemoved();
        callbackInfo.cancel();
    }
}
