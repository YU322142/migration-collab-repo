package com.github.ysbbbbbb.kaleidoscopecookery.mixin;

import net.minecraft.world.entity.EntityType;
import net.minecraft.world.item.MobBucketItem;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

@SuppressWarnings("all")
@Mixin(value = MobBucketItem.class)
public interface MobBucketItemAccessor {
    @Invoker(value = "getFishType", remap = false)
    EntityType<?> kaleidoscope$GetFishType();
}
