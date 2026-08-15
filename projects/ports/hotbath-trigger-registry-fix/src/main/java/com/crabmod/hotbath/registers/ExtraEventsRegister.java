package com.crabmod.hotbath.registers;

import com.crabmod.hotbath.HotBath;
import com.crabmod.hotbath.advancements.AdvancementTrigger;
import com.crabmod.hotbath.particles.SteamParticle;
import net.minecraft.advancements.CriteriaTriggers;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.Registries;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.RegisterParticleProvidersEvent;
import net.neoforged.neoforge.registries.RegisterEvent;

@EventBusSubscriber(modid = HotBath.MOD_ID)
public class ExtraEventsRegister {
    @SubscribeEvent
    public static void registerParticlesFactories(final RegisterParticleProvidersEvent event) {
        Minecraft.getInstance()
                .particleEngine
                .register(ParticleRegister.STEAM_PARTICLE.get(), SteamParticle.CozySmokeFactory::new);
    }

    @SubscribeEvent
    public static void registerAdvancementTrigger(RegisterEvent event) {
        if (!event.getRegistryKey().equals(Registries.TRIGGER_TYPE)) {
            return;
        }

        CriteriaTriggers.register(
                "hotbath:foot_health", new AdvancementTrigger("hotbath", "foot_health"));
        CriteriaTriggers.register(
                "hotbath:milk_skin", new AdvancementTrigger("hotbath", "milk_skin"));
        CriteriaTriggers.register(
                "hotbath:chronic_invalid", new AdvancementTrigger("hotbath", "chronic_invalid"));
        CriteriaTriggers.register(
                "hotbath:rose_body_fragrance",
                new AdvancementTrigger("hotbath", "rose_body_fragrance"));
    }
}
