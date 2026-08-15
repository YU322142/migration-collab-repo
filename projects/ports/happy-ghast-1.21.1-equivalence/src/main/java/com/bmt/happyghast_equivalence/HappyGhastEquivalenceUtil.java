package com.bmt.happyghast_equivalence;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.Entity;

public final class HappyGhastEquivalenceUtil {
    private static final ResourceLocation HAPPY_GHAST = ResourceLocation.withDefaultNamespace("happy_ghast");

    private HappyGhastEquivalenceUtil() {
    }

    public static boolean isHappyGhast(Entity entity) {
        return entity != null && HAPPY_GHAST.equals(BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()));
    }
}
