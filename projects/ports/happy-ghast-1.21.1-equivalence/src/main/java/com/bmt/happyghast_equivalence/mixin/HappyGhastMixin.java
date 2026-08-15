package com.bmt.happyghast_equivalence.mixin;

import net.minecraft.core.BlockPos;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.Tag;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.level.Level;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Bridges the 1.21.6 mob home fields to Backport's older restriction API.
 * The mixin intentionally accepts both the GlobalPos-style compound and a
 * bare three-element int array, so old hand-authored NBT remains loadable.
 */
@Mixin(targets = "com.juanmuscaria.backport.world.entity.animal.happyghast.HappyGhast")
public abstract class HappyGhastMixin extends Mob {
    @Unique
    private boolean happyGhastEquivalence$hasHome;

    protected HappyGhastMixin(EntityType<? extends Mob> type, Level level) {
        super(type, level);
    }

    @Inject(method = "readAdditionalSaveData", at = @At("TAIL"))
    private void happyGhastEquivalence$readHome(CompoundTag tag, CallbackInfo ci) {
        if (!tag.contains("home_pos")) {
            return;
        }

        CompoundTag home = tag.contains("home_pos", Tag.TAG_COMPOUND)
                ? tag.getCompound("home_pos") : null;
        int[] coordinates = home == null ? tag.getIntArray("home_pos") : home.getIntArray("pos");
        if (coordinates.length != 3 && home != null
                && home.contains("x") && home.contains("y") && home.contains("z")) {
            coordinates = new int[]{home.getInt("x"), home.getInt("y"), home.getInt("z")};
        }
        if (coordinates.length != 3) {
            return;
        }

        String dimension = home == null ? "" : home.getString("dimension");
        if (!dimension.isEmpty() && !dimension.equals(level().dimension().location().toString())) {
            return;
        }

        int radius = tag.contains("home_radius") ? tag.getInt("home_radius") : 32;
        if (radius <= 0) {
            return;
        }
        restrictTo(new BlockPos(coordinates[0], coordinates[1], coordinates[2]), radius);
        happyGhastEquivalence$hasHome = true;
    }

    @Inject(method = "addAdditionalSaveData", at = @At("TAIL"))
    private void happyGhastEquivalence$writeHome(CompoundTag tag, CallbackInfo ci) {
        if (!happyGhastEquivalence$hasHome || !hasRestriction()) {
            return;
        }

        BlockPos center = getRestrictCenter();
        // 1.21.6 writes this field as a bare three-element int array.
        tag.putIntArray("home_pos", new int[]{center.getX(), center.getY(), center.getZ()});
        tag.putInt("home_radius", Math.max(1, Math.round(getRestrictRadius())));
    }

    @Inject(method = "tick", at = @At("TAIL"))
    private void happyGhastEquivalence$initializeNewHome(CallbackInfo ci) {
        // Backport creates its restriction lazily. Once that happens, retain
        // the first anchor so newly spawned entities gain the modern schema.
        if (!level().isClientSide && !happyGhastEquivalence$hasHome && hasRestriction()) {
            happyGhastEquivalence$hasHome = true;
        }
    }
}
