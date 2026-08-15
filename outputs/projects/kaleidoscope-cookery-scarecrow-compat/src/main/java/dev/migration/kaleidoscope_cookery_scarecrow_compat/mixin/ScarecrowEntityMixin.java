package dev.migration.kaleidoscope_cookery_scarecrow_compat.mixin;

import com.github.ysbbbbbb.kaleidoscopecookery.entity.ScarecrowEntity;
import dev.migration.kaleidoscope_cookery_scarecrow_compat.LegacyScarecrowNbt;
import net.minecraft.nbt.CompoundTag;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = ScarecrowEntity.class, remap = false)
public abstract class ScarecrowEntityMixin {
    @Inject(method = "readAdditionalSaveData", at = @At("HEAD"), remap = false)
    private void candidate13$normalizeLegacyInventory(CompoundTag tag, CallbackInfo callbackInfo) {
        LegacyScarecrowNbt.normalize(tag);
    }
}

