package dev.migration.hardcore_revival_death_fix.mixin;

import net.minecraft.world.level.GameRules;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(targets = "net.blay09.mods.hardcorerevival.HardcoreRevivalManager")
public abstract class HardcoreRevivalManagerMixin {
    @Redirect(
            method = "knockout(Lnet/minecraft/world/entity/player/Player;Lnet/minecraft/world/damagesource/DamageSource;)V",
            at = @At(value = "INVOKE", target = "Lnet/minecraft/world/level/GameRules;getBoolean(Lnet/minecraft/world/level/GameRules$Key;)Z")
    )
    private static boolean migration$doNotAnnounceKnockoutAsDeath(
            GameRules rules,
            GameRules.Key<GameRules.BooleanValue> key
    ) {
        if (key == GameRules.RULE_SHOWDEATHMESSAGES) {
            return false;
        }
        return rules.getBoolean(key);
    }
}
