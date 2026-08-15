package dev.migration.create_carriage_orientation_guard.mixin;

import com.simibubi.create.content.contraptions.Contraption;
import com.simibubi.create.content.contraptions.OrientedContraptionEntity;
import com.simibubi.create.content.trains.entity.CarriageContraption;
import com.simibubi.create.content.trains.entity.CarriageContraptionEntity;
import dev.migration.create_carriage_orientation_guard.CarriageOrientationDecision;
import dev.migration.create_carriage_orientation_guard.CreateCarriageOrientationGuard;
import net.minecraft.core.Direction;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(value = OrientedContraptionEntity.class, remap = false)
public abstract class OrientedContraptionEntityMixin {
    @Unique
    private boolean createCarriageOrientationGuard$warned;

    @Inject(method = "getInitialOrientation", at = @At("RETURN"), cancellable = true, remap = false)
    private void createCarriageOrientationGuard$resolveInvalidCarriageOrientation(
            CallbackInfoReturnable<Direction> callbackInfo
    ) {
        if (!((Object) this instanceof CarriageContraptionEntity carriage)) {
            return;
        }

        Direction raw = callbackInfo.getReturnValue();
        Contraption contraption = carriage.getContraption();
        Direction assemblyDirection = contraption instanceof CarriageContraption carriageContraption
                ? carriageContraption.getAssemblyDirection()
                : null;
        Direction resolved = CarriageOrientationDecision.resolve(raw, assemblyDirection);
        if (resolved == raw) {
            return;
        }
        if (!createCarriageOrientationGuard$warned) {
            createCarriageOrientationGuard$warned = true;
            CreateCarriageOrientationGuard.warnFallback(
                    carriage.getUUID(),
                    raw,
                    assemblyDirection,
                    resolved
            );
        }
        callbackInfo.setReturnValue(resolved);
    }
}
