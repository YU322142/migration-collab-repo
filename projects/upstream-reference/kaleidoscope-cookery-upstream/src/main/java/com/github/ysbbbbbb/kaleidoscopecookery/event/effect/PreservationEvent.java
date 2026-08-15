package com.github.ysbbbbbb.kaleidoscopecookery.event.effect;

import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
import com.github.ysbbbbbb.kaleidoscopecookery.init.ModEffects;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.food.FoodProperties;
import net.minecraft.world.item.ItemStack;
import net.minecraftforge.event.entity.living.LivingEntityUseItemEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import static net.minecraft.world.effect.MobEffectCategory.HARMFUL;

@Mod.EventBusSubscriber(modid = KaleidoscopeCookery.MOD_ID)
public class PreservationEvent {
    @SubscribeEvent
    public static void onEatFood(LivingEntityUseItemEvent.Finish event) {
        ItemStack stack = event.getItem();
        LivingEntity entity = event.getEntity();
        if (stack.isEdible() && entity.hasEffect(ModEffects.PRESERVATION.get())) {
            FoodProperties foodProperties = stack.getFoodProperties(entity);
            if (foodProperties == null) {
                return;
            }
            for (var effectPair : foodProperties.getEffects()) {
                MobEffect effect = effectPair.getFirst().getEffect();
                if (effect.getCategory() == HARMFUL) {
                    entity.removeEffect(effect);
                }
            }
        }
    }
}
