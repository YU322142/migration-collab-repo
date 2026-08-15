package com.crabmod.hotbath.events;

import com.crabmod.hotbath.fluid_blocks.AbstractHotbathBlock;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.animal.AbstractFish;
import net.minecraft.world.entity.animal.Squid;
import net.minecraft.world.entity.animal.TropicalFish;
import net.minecraft.world.level.Level;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.tick.EntityTickEvent;

import static com.crabmod.hotbath.HotBath.MOD_ID;

@EventBusSubscriber(modid = MOD_ID)
public class AquaticMobHurtsHandler {

    @SubscribeEvent
    public static void onEntityUpdate(EntityTickEvent.Pre event) {
        Entity e = event.getEntity();
        if (e instanceof LivingEntity entity) {
            Level world = entity.level();
            BlockPos pos = entity.blockPosition();

            // Check if the entity is in a hot bath block
            boolean inHotBath = world.getBlockState(pos).getBlock() instanceof AbstractHotbathBlock;

            if (inHotBath && isNonTropicalAquatic(entity)) {
                entity.hurt(world.damageSources().magic(), 1.0F);
            }
        }
    }

    private static boolean isNonTropicalAquatic(LivingEntity livingEntity) {
        return (livingEntity instanceof AbstractFish && !(livingEntity instanceof TropicalFish))
                || livingEntity instanceof Squid;
    }
}
