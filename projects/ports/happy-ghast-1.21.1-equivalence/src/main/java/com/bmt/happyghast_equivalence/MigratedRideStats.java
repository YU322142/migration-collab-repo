package com.bmt.happyghast_equivalence;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.stats.Stat;
import net.minecraft.stats.StatFormatter;
import net.minecraft.stats.Stats;
import net.minecraft.world.entity.Entity;
import net.neoforged.neoforge.registries.RegisterEvent;

public final class MigratedRideStats {
    public static final ResourceLocation HAPPY_GHAST_ONE_CM =
            ResourceLocation.parse(RideStatSemantics.HAPPY_GHAST_STAT);
    public static final ResourceLocation NAUTILUS_ONE_CM =
            ResourceLocation.parse(RideStatSemantics.NAUTILUS_STAT);

    private MigratedRideStats() {
    }

    public static void register(RegisterEvent event) {
        if (!event.getRegistryKey().equals(Registries.CUSTOM_STAT)) {
            return;
        }

        registerDistanceStat(event, HAPPY_GHAST_ONE_CM);
        registerDistanceStat(event, NAUTILUS_ONE_CM);
    }

    private static void registerDistanceStat(RegisterEvent event, ResourceLocation id) {
        if (!BuiltInRegistries.CUSTOM_STAT.containsKey(id)) {
            event.register(Registries.CUSTOM_STAT, id, () -> id);
        }
        Stats.CUSTOM.get(id, StatFormatter.DISTANCE);
    }

    public static Stat<ResourceLocation> statisticForVehicle(Entity vehicle) {
        if (vehicle == null) {
            return null;
        }

        ResourceLocation entityId = BuiltInRegistries.ENTITY_TYPE.getKey(vehicle.getType());
        if (entityId == null) {
            return null;
        }
        String statId = RideStatSemantics.statisticForVehicle(entityId.toString());
        if (statId == null) {
            return null;
        }
        ResourceLocation statisticId = ResourceLocation.parse(statId);
        return BuiltInRegistries.CUSTOM_STAT.containsKey(statisticId)
                ? Stats.CUSTOM.get(statisticId) : null;
    }
}
