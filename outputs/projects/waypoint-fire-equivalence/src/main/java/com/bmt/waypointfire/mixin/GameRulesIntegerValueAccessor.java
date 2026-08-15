package com.bmt.waypointfire.mixin;

import java.util.function.BiConsumer;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.GameRules;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin(GameRules.IntegerValue.class)
public interface GameRulesIntegerValueAccessor {
    @Invoker("create")
    static GameRules.Type<GameRules.IntegerValue> waypointFire$create(
        int defaultValue,
        int minimum,
        int maximum,
        BiConsumer<MinecraftServer, GameRules.IntegerValue> callback
    ) {
        throw new AssertionError();
    }
}
