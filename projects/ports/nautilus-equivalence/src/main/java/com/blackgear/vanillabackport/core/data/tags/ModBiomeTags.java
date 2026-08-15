package com.blackgear.vanillabackport.core.data.tags;

import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.tags.TagKey;
import net.minecraft.world.level.biome.Biome;

public final class ModBiomeTags {
    public static final TagKey<Biome> SPAWNS_CORAL_VARIANT_ZOMBIE_NAUTILUS = tag("spawns_coral_variant_zombie_nautilus");
    public static final TagKey<Biome> SPAWNS_NAUTILUS = tag("spawns_nautilus");
    public static final TagKey<Biome> SPAWNS_NAUTILUS_FREQUENTLY = tag("spawns_nautilus_frequently");

    private static TagKey<Biome> tag(String name) {
        return TagKey.create(Registries.BIOME, ResourceLocation.withDefaultNamespace(name));
    }

    private ModBiomeTags() {
    }
}
