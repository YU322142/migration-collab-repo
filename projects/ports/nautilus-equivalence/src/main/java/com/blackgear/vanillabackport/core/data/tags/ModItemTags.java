package com.blackgear.vanillabackport.core.data.tags;

import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.tags.TagKey;
import net.minecraft.world.item.Item;

public final class ModItemTags {
    public static final TagKey<Item> NAUTILUS_BUCKET_FOOD = tag("nautilus_bucket_food");
    public static final TagKey<Item> NAUTILUS_FOOD = tag("nautilus_food");
    public static final TagKey<Item> NAUTILUS_TAMING_ITEMS = tag("nautilus_taming_items");

    private static TagKey<Item> tag(String name) {
        return TagKey.create(Registries.ITEM, ResourceLocation.withDefaultNamespace(name));
    }

    private ModItemTags() {
    }
}
