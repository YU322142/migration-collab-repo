package com.blackgear.vanillabackport.common.registries.entities;

import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.Nautilus;
import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.ZombieNautilus;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModEntityTypes {
    public static final DeferredRegister<EntityType<?>> ENTITIES =
        DeferredRegister.create(BuiltInRegistries.ENTITY_TYPE, "minecraft");

    public static final DeferredHolder<EntityType<?>, EntityType<Nautilus>> NAUTILUS =
        ENTITIES.register("nautilus", () -> EntityType.Builder
            .of(Nautilus::new, MobCategory.WATER_CREATURE)
            .sized(0.875F, 0.95F)
            .passengerAttachments(1.1375F)
            .eyeHeight(0.2751F)
            .clientTrackingRange(10)
            .build("nautilus"));

    public static final DeferredHolder<EntityType<?>, EntityType<ZombieNautilus>> ZOMBIE_NAUTILUS =
        ENTITIES.register("zombie_nautilus", () -> EntityType.Builder
            .of(ZombieNautilus::new, MobCategory.MONSTER)
            .sized(0.875F, 0.95F)
            .passengerAttachments(1.1375F)
            .eyeHeight(0.2751F)
            .clientTrackingRange(10)
            .build("zombie_nautilus"));

    private ModEntityTypes() {
    }
}
