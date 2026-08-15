package com.blackgear.vanillabackport.core;

import net.minecraft.resources.ResourceLocation;

/** Small compatibility facade retained by the copied entity sources. */
public final class VanillaBackport {
    public static final String MOD_ID = "nautilus_equivalence";
    public static final String NAMESPACE = "minecraft";

    private VanillaBackport() {}

    public static ResourceLocation resource(String path) {
        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);
    }
}
