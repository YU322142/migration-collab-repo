package com.github.ysbbbbbb.kaleidoscopecookery.client.init;

import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
import com.github.ysbbbbbb.kaleidoscopecookery.client.particle.CookingParticle;
import com.github.ysbbbbbb.kaleidoscopecookery.client.particle.StockpotParticle;
import com.github.ysbbbbbb.kaleidoscopecookery.init.ModParticles;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.client.event.RegisterParticleProvidersEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

@Mod.EventBusSubscriber(modid = KaleidoscopeCookery.MOD_ID, value = Dist.CLIENT, bus = Mod.EventBusSubscriber.Bus.MOD)
public class ParticleFactoryRegistry {
    @SubscribeEvent
    public static void onRegisterParticleFactory(RegisterParticleProvidersEvent event) {
        event.registerSpriteSet(ModParticles.COOKING.get(), CookingParticle.Provider::new);
        event.registerSpriteSet(ModParticles.STOCKPOT.get(), StockpotParticle.Provider::new);
    }
}
