package com.bmt.nautilus_equivalence.client;

import com.blackgear.vanillabackport.client.level.model.entity.nautilus.NautilusModel;
import com.blackgear.vanillabackport.client.level.model.entity.nautilus.ZombieNautilusCoralModel;
import com.blackgear.vanillabackport.client.level.renderer.entity.mob.NautilusRenderer;
import com.blackgear.vanillabackport.client.level.renderer.entity.mob.ZombieNautilusRenderer;
import com.blackgear.vanillabackport.client.registries.ModModelLayers;
import com.blackgear.vanillabackport.common.registries.entities.ModEntityTypes;
import com.bmt.nautilus_equivalence.NautilusEquivalence;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.EntityRenderersEvent;

@EventBusSubscriber(modid = NautilusEquivalence.MOD_ID, bus = EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
public final class NautilusClientEvents {
    private NautilusClientEvents() {
    }

    @SubscribeEvent
    public static void registerRenderers(EntityRenderersEvent.RegisterRenderers event) {
        event.registerEntityRenderer(ModEntityTypes.NAUTILUS.get(), NautilusRenderer::new);
        event.registerEntityRenderer(ModEntityTypes.ZOMBIE_NAUTILUS.get(), ZombieNautilusRenderer::new);
    }

    @SubscribeEvent
    public static void registerLayers(EntityRenderersEvent.RegisterLayerDefinitions event) {
        event.registerLayerDefinition(ModModelLayers.NAUTILUS, NautilusModel::createBodyLayer);
        event.registerLayerDefinition(ModModelLayers.NAUTILUS_BABY, NautilusModel::createBabyBodyLayer);
        event.registerLayerDefinition(ModModelLayers.NAUTILUS_ARMOR, NautilusModel::createBodyArmorLayer);
        event.registerLayerDefinition(ModModelLayers.NAUTILUS_SADDLE, NautilusModel::createSaddleLayer);
        event.registerLayerDefinition(ModModelLayers.ZOMBIE_NAUTILUS, NautilusModel::createBodyLayer);
        event.registerLayerDefinition(ModModelLayers.ZOMBIE_NAUTILUS_CORAL, ZombieNautilusCoralModel::createBodyLayer);
    }
}
