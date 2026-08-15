package com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus;

import net.minecraft.resources.ResourceLocation;

public record ZombieNautilusVariant(ModelType model, ResourceLocation texture) {
    public enum ModelType {
        NORMAL,
        WARM
    }
}
