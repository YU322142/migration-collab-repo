package com.bmt.happyghast_equivalence.mixin;

import com.bmt.happyghast_equivalence.HappyGhastEquivalenceUtil;
import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.ai.goal.TemptGoal;
import net.minecraft.world.entity.ai.targeting.TargetingConditions;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.util.function.Predicate;

/** Extends only Backport Happy Ghast's adult TemptGoal from 10 to 16 blocks. */
@Mixin(TemptGoal.class)
public abstract class TemptGoalMixin {
    @Shadow @Final private TargetingConditions targetingConditions;

    @Inject(method = "<init>", at = @At("TAIL"))
    private void happyGhastEquivalence$setRange(PathfinderMob mob, double speed,
                                                  Predicate<ItemStack> items, boolean canScare,
                                                  CallbackInfo ci) {
        if (HappyGhastEquivalenceUtil.isHappyGhast(mob)) {
            targetingConditions.range(16.0D);
        }
    }
}
