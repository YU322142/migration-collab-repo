package com.bmt.waypointfire.mixin;

import com.bmt.waypointfire.CompatGameRules;
import com.bmt.waypointfire.ParitySemantics;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.GameRules;
import net.minecraft.world.level.block.FireBlock;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(FireBlock.class)
public abstract class FireBlockMixin {
    @Redirect(
        method = "tick",
        at = @At(
            value = "INVOKE",
            target = "Lnet/minecraft/world/level/GameRules;getBoolean(Lnet/minecraft/world/level/GameRules$Key;)Z"
        )
    )
    private boolean waypointFire$gateSpread(
        GameRules rules,
        GameRules.Key<GameRules.BooleanValue> key,
        net.minecraft.world.level.block.state.BlockState state,
        ServerLevel level,
        BlockPos pos,
        net.minecraft.util.RandomSource random
    ) {
        if (key != GameRules.RULE_DOFIRETICK) {
            return rules.getBoolean(key);
        }
        int radius = rules.getInt(CompatGameRules.FIRE_RADIUS);
        return ParitySemantics.fireSpreadAllowed(radius, level.players().stream()
            .filter(player -> !player.isSpectator())
            .mapToDouble(player -> player.position().distanceTo(net.minecraft.world.phys.Vec3.atLowerCornerOf(pos))));
    }
}
