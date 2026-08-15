package com.blackgear.vanillabackport.common.registries.entities;

import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.NautilusAi;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.ai.sensing.SensorType;
import net.minecraft.world.entity.ai.sensing.TemptingSensor;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModSensorTypes {
    public static final DeferredRegister<SensorType<?>> SENSORS =
        DeferredRegister.create(BuiltInRegistries.SENSOR_TYPE, "minecraft");

    public static final DeferredHolder<SensorType<?>, SensorType<TemptingSensor>> NAUTILUS_TEMPTATIONS =
        SENSORS.register("nautilus_temptations", () -> new SensorType<>(() -> new TemptingSensor(NautilusAi.getTemptations())));

    private ModSensorTypes() {
    }
}
