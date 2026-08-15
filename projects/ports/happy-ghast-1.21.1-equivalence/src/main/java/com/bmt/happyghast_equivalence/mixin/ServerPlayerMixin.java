package com.bmt.happyghast_equivalence.mixin;

import com.bmt.happyghast_equivalence.MigratedRideStats;
import com.bmt.happyghast_equivalence.RideStatSemantics;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.stats.Stat;
import net.minecraft.resources.ResourceLocation;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ServerPlayer.class)
public abstract class ServerPlayerMixin {
    @Inject(method = "checkRidingStatistics", at = @At("TAIL"))
    private void happyGhastEquivalence$recordMigratedRideDistance(
            double deltaX, double deltaY, double deltaZ, CallbackInfo ci) {
        ServerPlayer player = (ServerPlayer)(Object)this;
        if (!player.isPassenger() || !RideStatSemantics.hasMovement(deltaX, deltaY, deltaZ)) {
            return;
        }

        Stat<ResourceLocation> stat = MigratedRideStats.statisticForVehicle(player.getVehicle());
        if (stat != null) {
            player.awardStat(stat, RideStatSemantics.distanceInCentimeters(deltaX, deltaY, deltaZ));
        }
    }
}
