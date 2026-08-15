package dev.migration.deferred_content_protection.mixin;

import com.mojang.logging.LogUtils;
import dev.migration.deferred_content_protection.DeferredContentProtection;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.phys.Vec3;
import org.slf4j.Logger;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(Entity.class)
public abstract class EntityMixin {
    private static final Logger DEFERRED_CONTENT_PROTECTION_LOGGER = LogUtils.getLogger();

    @Inject(method = "onBelowWorld", at = @At("HEAD"), cancellable = true)
    private void deferredContentProtection$rescueCarrierFromVoid(CallbackInfo callback) {
        Entity entity = (Entity) (Object) this;
        if (!(entity instanceof ItemEntity itemEntity)
                || !DeferredContentProtection.isProtected(itemEntity.getItem())) {
            return;
        }

        double rescueX = itemEntity.getX();
        double rescueY = itemEntity.level().getMinBuildHeight() + 1.0D;
        double rescueZ = itemEntity.getZ();
        if (itemEntity.level() instanceof ServerLevel serverLevel) {
            BlockPos spawn = serverLevel.getSharedSpawnPos();
            rescueX = spawn.getX() + 0.5D;
            rescueY = spawn.getY() + 1.0D;
            rescueZ = spawn.getZ() + 0.5D;
            DEFERRED_CONTENT_PROTECTION_LOGGER.warn(
                    "Rescued protected deferred carrier from the void to {} in {}",
                    spawn,
                    serverLevel.dimension().location()
            );
        }

        itemEntity.setPos(rescueX, rescueY, rescueZ);
        itemEntity.setDeltaMovement(Vec3.ZERO);
        itemEntity.setUnlimitedLifetime();
        itemEntity.setInvulnerable(true);
        callback.cancel();
    }
}
