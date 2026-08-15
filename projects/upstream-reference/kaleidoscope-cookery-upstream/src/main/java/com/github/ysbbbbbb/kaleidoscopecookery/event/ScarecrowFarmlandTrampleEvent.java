package com.github.ysbbbbbb.kaleidoscopecookery.event;

import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
import com.github.ysbbbbbb.kaleidoscopecookery.entity.ScarecrowEntity;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.LevelAccessor;
import net.minecraft.world.phys.AABB;
import net.minecraftforge.event.level.BlockEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.List;

@Mod.EventBusSubscriber(modid = KaleidoscopeCookery.MOD_ID)
public class ScarecrowFarmlandTrampleEvent {
    @SubscribeEvent
    public static void onFarmlandTrampleEvent(BlockEvent.FarmlandTrampleEvent event) {
        LevelAccessor level = event.getLevel();
        BlockPos pos = event.getPos();
        if (level instanceof ServerLevel serverLevel) {
            List<ScarecrowEntity> entities = serverLevel.getEntitiesOfClass(ScarecrowEntity.class, new AABB(pos).inflate(16));
            if (!entities.isEmpty()) {
                event.setCanceled(true);
            }
        }
    }
}
