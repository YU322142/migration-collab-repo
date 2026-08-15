package com.crabmod.hotbath.events.enter_fluid_events;

import com.crabmod.hotbath.HotBath;
import com.crabmod.hotbath.util.CustomFluidHandler;
import com.crabmod.hotbath.util.EffectRemovalHandler;
import net.minecraft.advancements.AdvancementHolder;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.tick.EntityTickEvent;

import java.util.Objects;

import static com.crabmod.hotbath.util.HealthRegenHandler.regenHealth;

@EventBusSubscriber(modid = HotBath.MOD_ID)
public class RoseBathEvents {
    private static final int TICK_NUMBER = 20;
    static final String ROSE_BATH_ENTERED_NUMBER = "RoseBathEnteredNumber";
    static final String ROSE_BATH_STAYED_TIME = "RoseBathStayedTime";
    static final String HAS_ENTERED_ROSE_BATH = "HasEnteredRoseBath";
    static final String ROSE_BATH_ADVANCEMENT_ID = "hotbath:rose_body_fragrance";
    private static final int ROSE_BATH_ENTERED_COUNT_TRIGGER_NUMBER = 100;
    private static final int ROSE_BATH_STAYED_EFFECT_TRIGGER_TIME_SECONDS = 15;

    @SubscribeEvent
    public static void enterRoseBathEvents(EntityTickEvent.Pre event) {
        enterFluidEvents(
                event,
                ROSE_BATH_ENTERED_COUNT_TRIGGER_NUMBER,
                ROSE_BATH_STAYED_EFFECT_TRIGGER_TIME_SECONDS,
                ROSE_BATH_ENTERED_NUMBER,
                ROSE_BATH_STAYED_TIME,
                HAS_ENTERED_ROSE_BATH,
                ROSE_BATH_ADVANCEMENT_ID);
    }

    public static void enterFluidEvents(
            EntityTickEvent.Pre event,
            int enteredCountTriggerNumber,
            int stayedEffectTriggerTime,
            String enteredNumberInRoseBath,
            String roseBathStayedTime,
            String hasEnteredRoseBath,
            String roseBathAdvancementId) {
        if (event.getEntity() instanceof ServerPlayer player) {
            CompoundTag playerData = player.getPersistentData();
            boolean isInRoseBath = CustomFluidHandler.isPlayerInRoseBathBlock(player);

            if (isInRoseBath && player.isAlive()) {
                if (!playerData.getBoolean(hasEnteredRoseBath)) {
                    int enteredCount = playerData.getInt(enteredNumberInRoseBath) + 1;
                    playerData.putInt(enteredNumberInRoseBath, enteredCount);
                    playerData.putBoolean(hasEnteredRoseBath, true);

                    if (enteredCount >= enteredCountTriggerNumber) {
                        AdvancementHolder advancement =
                                Objects.requireNonNull(player.getServer())
                                        .getAdvancements()
                                        .get(Objects.requireNonNull(ResourceLocation.tryParse(roseBathAdvancementId)));

                        if (advancement != null) {
                            player.getAdvancements().award(advancement, "code_triggered");
                            playerData.putInt(enteredNumberInRoseBath, 0);
                        }
                    }
                }
                int roseBathStayTime = playerData.getInt(roseBathStayedTime) + 1;
                playerData.putInt(roseBathStayedTime, roseBathStayTime);
                regenHealth(0.25F, 1, player);
                if (playerData.getInt(roseBathStayedTime) >= stayedEffectTriggerTime * TICK_NUMBER) {
                    EffectRemovalHandler.removeNegativeEffects(player);
                    EffectRemovalHandler.removeBadOmen(player);
                    player.addEffect(
                            new MobEffectInstance(
                                    MobEffects.DAMAGE_BOOST, 20 * TICK_NUMBER, 0, false, false, true));
                }

            } else {
                playerData.putInt(roseBathStayedTime, 0);
                playerData.putBoolean(hasEnteredRoseBath, false);
            }
        }
    }
}
