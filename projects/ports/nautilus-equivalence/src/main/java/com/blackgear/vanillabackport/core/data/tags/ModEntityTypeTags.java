package com.blackgear.vanillabackport.core.data.tags;

import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.tags.TagKey;
import net.minecraft.world.entity.EntityType;

public final class ModEntityTypeTags {
    public static final TagKey<EntityType<?>> CAN_WEAR_NAUTILUS_ARMOR =
        TagKey.create(Registries.ENTITY_TYPE, ResourceLocation.withDefaultNamespace("can_wear_nautilus_armor"));
    public static final TagKey<EntityType<?>> NAUTILUS_HOSTILES =
        TagKey.create(Registries.ENTITY_TYPE, ResourceLocation.withDefaultNamespace("nautilus_hostiles"));

    private ModEntityTypeTags() {
    }
}
