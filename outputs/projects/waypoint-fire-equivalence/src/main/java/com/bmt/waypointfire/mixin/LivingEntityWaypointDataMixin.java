package com.bmt.waypointfire.mixin;

import com.bmt.waypointfire.WaypointIcon;
import com.bmt.waypointfire.WaypointIconCarrier;
import com.bmt.waypointfire.WaypointFireEquivalence;
import com.bmt.waypointfire.server.WaypointManager;
import net.minecraft.core.Holder;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.ai.attributes.Attribute;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(LivingEntity.class)
public abstract class LivingEntityWaypointDataMixin implements WaypointIconCarrier {
    @Unique
    private WaypointIcon waypointFire$icon = WaypointIcon.DEFAULT;

    @Override
    public WaypointIcon waypointFire$getIcon() {
        return waypointFire$icon;
    }

    @Override
    public void waypointFire$setIcon(WaypointIcon icon) {
        waypointFire$icon = icon == null ? WaypointIcon.DEFAULT : icon;
    }

    @Inject(method = "addAdditionalSaveData", at = @At("TAIL"))
    private void waypointFire$saveIcon(CompoundTag tag, CallbackInfo callback) {
        if (!waypointFire$icon.isDefault()) {
            tag.put("locator_bar_icon", waypointFire$icon.save());
        }
    }

    @Inject(method = "readAdditionalSaveData", at = @At("TAIL"))
    private void waypointFire$loadIcon(CompoundTag tag, CallbackInfo callback) {
        waypointFire$icon = tag.contains("locator_bar_icon", CompoundTag.TAG_COMPOUND)
            ? WaypointIcon.load(tag.getCompound("locator_bar_icon"))
            : WaypointIcon.DEFAULT;
    }

    @Inject(method = "onAttributeUpdated", at = @At("TAIL"))
    private void waypointFire$attributeUpdated(Holder<Attribute> attribute, CallbackInfo callback) {
        if (attribute.is(WaypointFireEquivalence.WAYPOINT_TRANSMIT_RANGE.getKey())) {
            WaypointManager.transmitRangeChanged((LivingEntity) (Object) this);
        }
    }
}
