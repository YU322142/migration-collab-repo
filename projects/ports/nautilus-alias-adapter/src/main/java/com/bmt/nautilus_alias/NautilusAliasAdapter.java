package com.bmt.nautilus_alias;

import net.asm.mountsofmayhem.entity.NautilusEntity;
import net.asm.mountsofmayhem.entity.ZombieNautilusEntity;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Isolated probe: registers the source entity classes under vanilla paths. */
@Mod(NautilusAliasAdapter.MOD_ID)
public final class NautilusAliasAdapter {
    public static final String MOD_ID = "nautilus_alias_adapter";

    public static final DeferredRegister<EntityType<?>> ENTITY_TYPES =
            DeferredRegister.create(BuiltInRegistries.ENTITY_TYPE, "minecraft");

    public static final DeferredHolder<EntityType<?>, EntityType<NautilusEntity>> NAUTILUS =
            ENTITY_TYPES.register("nautilus", () -> EntityType.Builder
                    .of(NautilusEntity::new, MobCategory.WATER_CREATURE)
                    .setShouldReceiveVelocityUpdates(true)
                    .setTrackingRange(16)
                    .setUpdateInterval(3)
                    .sized(1.2f, 1.2f)
                    .build("nautilus"));

    public static final DeferredHolder<EntityType<?>, EntityType<ZombieNautilusEntity>> ZOMBIE_NAUTILUS =
            ENTITY_TYPES.register("zombie_nautilus", () -> EntityType.Builder
                    .of(ZombieNautilusEntity::new, MobCategory.MONSTER)
                    .setShouldReceiveVelocityUpdates(true)
                    .setTrackingRange(16)
                    .setUpdateInterval(3)
                    .sized(0.6f, 1.8f)
                    .build("zombie_nautilus"));

    public NautilusAliasAdapter(IEventBus modBus) {
        ENTITY_TYPES.register(modBus);
        modBus.addListener(NautilusAliasAdapter::registerAttributes);
    }

    private static void registerAttributes(net.neoforged.neoforge.event.entity.EntityAttributeCreationEvent event) {
        event.put(NAUTILUS.get(), NautilusEntity.createAttributes().build());
        event.put(ZOMBIE_NAUTILUS.get(), ZombieNautilusEntity.createAttributes().build());
    }
}
