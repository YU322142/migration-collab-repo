package com.bmt.happyghast_equivalence.client;

import com.bmt.happyghast_equivalence.HappyGhastEquivalence;
import com.bmt.happyghast_equivalence.HappyGhastEquivalenceUtil;
import net.minecraft.client.Camera;
import net.minecraft.world.entity.Entity;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.CalculateDetachedCameraDistanceEvent;

/** Restores the 1.21.6 Happy Ghast mounted third-person camera distance. */
@EventBusSubscriber(modid = HappyGhastEquivalence.MOD_ID, value = Dist.CLIENT)
public final class HappyGhastClientEvents {
    private HappyGhastClientEvents() {
    }

    @SubscribeEvent
    public static void calculateDetachedCameraDistance(CalculateDetachedCameraDistanceEvent event) {
        Camera camera = event.getCamera();
        Entity cameraEntity = camera.getEntity();
        if (cameraEntity != null && HappyGhastEquivalenceUtil.isHappyGhast(cameraEntity.getRootVehicle())) {
            event.setDistance(8.0F);
        }
    }
}
