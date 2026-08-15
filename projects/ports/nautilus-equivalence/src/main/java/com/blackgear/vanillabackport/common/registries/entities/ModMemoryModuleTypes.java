package com.blackgear.vanillabackport.common.registries.entities;

import com.mojang.serialization.Codec;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.ai.memory.MemoryModuleType;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

import java.util.Optional;

public final class ModMemoryModuleTypes {
    public static final DeferredRegister<MemoryModuleType<?>> MEMORIES =
        DeferredRegister.create(BuiltInRegistries.MEMORY_MODULE_TYPE, "minecraft");

    public static final DeferredHolder<MemoryModuleType<?>, MemoryModuleType<Integer>> CHARGE_COOLDOWN_TICKS =
        MEMORIES.register("charge_cooldown_ticks", () -> new MemoryModuleType<>(Optional.of(Codec.INT)));
    public static final DeferredHolder<MemoryModuleType<?>, MemoryModuleType<Integer>> ATTACK_TARGET_COOLDOWN =
        MEMORIES.register("attack_target_cooldown", () -> new MemoryModuleType<>(Optional.of(Codec.INT)));

    private ModMemoryModuleTypes() {
    }
}
