package com.bmt.happyghast_equivalence.mixin;

import com.bmt.happyghast_equivalence.HappyGhastEquivalenceUtil;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.ai.sensing.TemptingSensor;
import net.minecraft.world.entity.ai.targeting.TargetingConditions;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/** Extends only the custom Happy Ghast brain sensor's player checks to 16. */
@Mixin(TemptingSensor.class)
public abstract class TemptingSensorMixin {
    @Redirect(
            method = "lambda$doTick$0",
            at = @At(value = "INVOKE", target = "Lnet/minecraft/world/entity/ai/targeting/TargetingConditions;test(Lnet/minecraft/world/entity/LivingEntity;Lnet/minecraft/world/entity/LivingEntity;)Z")
    )
    private static boolean happyGhastEquivalence$targetingRange(TargetingConditions conditions,
                                                                  LivingEntity mob,
                                                                  LivingEntity player) {
        if (HappyGhastEquivalenceUtil.isHappyGhast(mob)) {
            return conditions.copy().range(16.0D).test(mob, player);
        }
        return conditions.test(mob, player);
    }

    @Redirect(
            method = "lambda$doTick$1",
            at = @At(value = "INVOKE", target = "Lnet/minecraft/world/entity/PathfinderMob;closerThan(Lnet/minecraft/world/entity/Entity;D)Z")
    )
    private static boolean happyGhastEquivalence$distanceRange(PathfinderMob mob,
                                                                 Entity player,
                                                                 double distance) {
        return mob.closerThan(player, HappyGhastEquivalenceUtil.isHappyGhast(mob) ? 16.0D : distance);
    }
}
