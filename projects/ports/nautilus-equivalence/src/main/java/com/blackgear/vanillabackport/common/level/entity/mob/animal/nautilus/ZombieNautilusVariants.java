package com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus;

import net.minecraft.resources.ResourceLocation;

public final class ZombieNautilusVariants {
    public static final String TEMPERATE_ID = "minecraft:temperate";
    public static final String WARM_ID = "minecraft:warm";
    public static final ZombieNautilusVariant TEMPERATE =
        new ZombieNautilusVariant(ZombieNautilusVariant.ModelType.NORMAL,
            ResourceLocation.withDefaultNamespace("textures/entity/nautilus/zombie_nautilus.png"));
    public static final ZombieNautilusVariant WARM =
        new ZombieNautilusVariant(ZombieNautilusVariant.ModelType.WARM,
            ResourceLocation.withDefaultNamespace("textures/entity/nautilus/zombie_nautilus_coral.png"));

    public static ZombieNautilusVariant byId(String id) {
        return WARM_ID.equals(id) ? WARM : TEMPERATE;
    }

    private ZombieNautilusVariants() {
    }
}
