package com.github.ysbbbbbb.kaleidoscopetavern.client.event;

import com.github.ysbbbbbb.kaleidoscopetavern.KaleidoscopeTavern;
import com.github.ysbbbbbb.kaleidoscopetavern.init.ModEffects;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.client.event.RenderPlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import static com.github.ysbbbbbb.kaleidoscopetavern.effect.GrassStealthEffect.notInGrassStealthPlant;

@Mod.EventBusSubscriber(modid = KaleidoscopeTavern.MOD_ID, value = Dist.CLIENT)
public class PlayerRenderEvent {
    @SubscribeEvent
    public static void onPlayerRender(RenderPlayerEvent.Pre event) {
        Player player = event.getEntity();
        if (player == null || !player.isAlive()) {
            return;
        }
        if (player.hasEffect(ModEffects.GRASS_STEALTH.get()) && player.isShiftKeyDown()) {
            Level level = player.level();
            BlockPos pos = player.blockPosition();
            BlockPos abovePos = pos.above();
            if (notInGrassStealthPlant(level, pos) && notInGrassStealthPlant(level, abovePos)) {
                return;
            }
            event.setCanceled(true);
        }
    }
}