package com.crabmod.hotbath.events.enter_fluid_events;

import com.crabmod.hotbath.HotBath;
import com.crabmod.hotbath.util.CustomFluidHandler;
import com.crabmod.hotbath.util.EffectRemovalHandler;
import com.crabmod.hotbath.util.HungerRegenHandler;
import net.minecraft.advancements.AdvancementHolder;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.tick.EntityTickEvent;

import java.util.Objects;

import static com.crabmod.hotbath.util.HealthRegenHandler.regenHealth;

@EventBusSubscriber(modid = HotBath.MOD_ID)
public class MilkBathEvents {
    private static final int TICK_NUMBER = 20;
    static final String MILK_BATH_ENTERED_NUMBER = "MilkBathEnteredNumber";
    static final String MILK_BATH_STAYED_TIME = "MilkBathStayedTime";
    static final String HAS_ENTERED_MILK_BATH = "HasEnteredMilkBath";
    static final String MILK_BATH_ADVANCEMENT_ID = "hotbath:milk_skin";
    private static final int MILK_BATH_ENTERED_COUNT_TRIGGER_NUMBER = 100;
    private static final int MILK_BATH_STAYED_EFFECT_TRIGGER_TIME_SECONDS = 15;

    // enter hot water block event
    @SubscribeEvent
    public static void enterMilkBathEvents(EntityTickEvent.Pre event) {
        enterFluidEvents(
                event,
                MILK_BATH_ENTERED_COUNT_TRIGGER_NUMBER,
                MILK_BATH_STAYED_EFFECT_TRIGGER_TIME_SECONDS,
                MILK_BATH_ENTERED_NUMBER,
                MILK_BATH_STAYED_TIME,
                HAS_ENTERED_MILK_BATH,
                MILK_BATH_ADVANCEMENT_ID);
    }

    public static void enterFluidEvents(
            EntityTickEvent.Pre event,
            int enteredCountTriggerNumber,
            int stayedEffectTriggerTime,
            String enteredNumberInMilkBath,
            String milkBathStayedTime,
            String hasEnteredMilkBath,
            String milkBathAdvancementId) {
        if (event.getEntity() instanceof ServerPlayer player) {
            CompoundTag playerData = player.getPersistentData();
            boolean isInMilkBath = CustomFluidHandler.isPlayerInMilkBathBlock(player);

            if (isInMilkBath && player.isAlive()) {
                handleAdvancement(
                        enteredCountTriggerNumber,
                        enteredNumberInMilkBath,
                        milkBathStayedTime,
                        hasEnteredMilkBath,
                        milkBathAdvancementId,
                        player,
                        playerData);
                HungerRegenHandler.regenHunger(1, 15, player);
                regenHealth(0.25F, 2, player);
                if (playerData.getInt(milkBathStayedTime) >= stayedEffectTriggerTime * TICK_NUMBER) {
                    EffectRemovalHandler.removeNegativeEffectsExceptUnluck(player);
                }
            } else {
                playerData.putInt(milkBathStayedTime, 0);
                playerData.putBoolean(hasEnteredMilkBath, false);
            }
        }
    }

    static void handleAdvancement(
            int enteredCountTriggerNumber,
            String enteredNumberInMilkBath,
            String milkBathStayedTime,
            String hasEnteredMilkBath,
            String milkBathAdvancementId,
            ServerPlayer player,
            CompoundTag playerData) {
        if (!playerData.getBoolean(hasEnteredMilkBath)) {
            int enteredCount = playerData.getInt(enteredNumberInMilkBath) + 1;
            playerData.putInt(enteredNumberInMilkBath, enteredCount);
            playerData.putBoolean(hasEnteredMilkBath, true);

            if (enteredCount >= enteredCountTriggerNumber) {
                AdvancementHolder advancement =
                        Objects.requireNonNull(player.getServer())
                                .getAdvancements()
                                .get(Objects.requireNonNull(ResourceLocation.tryParse(milkBathAdvancementId)));

                if (advancement != null) {
                    player.getAdvancements().award(advancement, "code_triggered");
                    playerData.putInt(enteredNumberInMilkBath, 0);
                }
            }
        }

        int hotBathTime = playerData.getInt(milkBathStayedTime) + 1;
        playerData.putInt(milkBathStayedTime, hotBathTime);
    }
}
