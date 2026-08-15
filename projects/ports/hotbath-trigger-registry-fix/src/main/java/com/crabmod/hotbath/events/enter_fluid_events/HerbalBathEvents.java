package com.crabmod.hotbath.events.enter_fluid_events;

import com.crabmod.hotbath.HotBath;
import com.crabmod.hotbath.util.CustomFluidHandler;
import com.crabmod.hotbath.util.EffectRemovalHandler;
import com.crabmod.hotbath.util.HealthRegenHandler;
import com.crabmod.hotbath.util.ResistanceBoostHandler;
import net.minecraft.advancements.AdvancementHolder;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.monster.Skeleton;
import net.minecraft.world.entity.monster.Zombie;
import net.minecraft.world.level.Level;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.tick.EntityTickEvent;

import java.util.Objects;

@EventBusSubscriber(modid = HotBath.MOD_ID)
public class HerbalBathEvents {
    private static final int TICK_NUMBER = 20;
    static final String HERBAL_BATH_ENTERED_NUMBER = "HerbalBathEnteredNumber";
    static final String HERBAL_BATH_STAYED_TIME = "HerbalBathStayedTime";
    static final String HAS_ENTERED_HERBAL_BATH = "HasEnteredHerbalBath";
    static final String HERBAL_BATH_ADVANCEMENT_ID = "hotbath:chronic_invalid";
    private static final int HERBAL_BATH_ENTERED_COUNT_TRIGGER_NUMBER = 100;
    private static final int HERBAL_BATH_STAYED_EFFECT_TRIGGER_TIME_SECONDS = 5;

    // enter hot water block event
    @SubscribeEvent
    public static void enterHerbalBathBlockEvent(EntityTickEvent.Pre event) {
        enterFluidEvents(
                event,
                HERBAL_BATH_ENTERED_COUNT_TRIGGER_NUMBER,
                HERBAL_BATH_STAYED_EFFECT_TRIGGER_TIME_SECONDS,
                HERBAL_BATH_ENTERED_NUMBER,
                HERBAL_BATH_STAYED_TIME,
                HAS_ENTERED_HERBAL_BATH,
                HERBAL_BATH_ADVANCEMENT_ID);
    }

    public static void enterFluidEvents(
            EntityTickEvent.Pre event,
            int enteredCountTriggerNumber,
            int stayedEffectTriggerTime,
            String enteredNumberInHerbalBath,
            String herbalBathStayedTime,
            String hasEnteredHerbalBath,
            String herbalBathAdvancementId) {

        if (!(event.getEntity() instanceof ServerPlayer)) {
            if (event.getEntity() instanceof Zombie || event.getEntity() instanceof Skeleton) {
                boolean isInHerbalBath = CustomFluidHandler.isEntityInHerbalBathBlock(event.getEntity());

                if (isInHerbalBath) {
                    int damageIntervalTicks = 20;
                    float damagePerSecond = 0.5F;

                    if (event.getEntity().tickCount % damageIntervalTicks == 0) {
                        Level level = event.getEntity().level();
                        event.getEntity().hurt(level.damageSources().magic(), damagePerSecond);
                    }
                }
            }
            return;
        }

        boolean isInHerbalBath =
                CustomFluidHandler.isPlayerInHerbalBathBlock((ServerPlayer) event.getEntity());

        if (event.getEntity() instanceof ServerPlayer player) {
            CompoundTag playerData = player.getPersistentData();

            if (isInHerbalBath && player.isAlive()) {
                if (!playerData.getBoolean(hasEnteredHerbalBath)) {
                    int enteredCount = playerData.getInt(enteredNumberInHerbalBath) + 1;
                    playerData.putInt(enteredNumberInHerbalBath, enteredCount);
                    playerData.putBoolean(hasEnteredHerbalBath, true);

                    if (enteredCount >= enteredCountTriggerNumber) {
                        AdvancementHolder advancement =
                                Objects.requireNonNull(player.getServer())
                                        .getAdvancements()
                                        .get(
                                                Objects.requireNonNull(ResourceLocation.tryParse(herbalBathAdvancementId)));

                        if (advancement != null) {
                            player.getAdvancements().award(advancement, "code_triggered");
                            playerData.putInt(enteredNumberInHerbalBath, 0);
                        }
                    }
                }

                int hotBathTime = playerData.getInt(herbalBathStayedTime) + 1;
                playerData.putInt(herbalBathStayedTime, hotBathTime);

                HealthRegenHandler.regenHealth(0.25F, 2, player);

                if (playerData.getInt(herbalBathStayedTime) >= stayedEffectTriggerTime * TICK_NUMBER) {
                    ResistanceBoostHandler.applyResistanceBoost(10, player);
                }

                if (playerData.getInt(herbalBathStayedTime) >= 15 * TICK_NUMBER) {
                    // remove negative effects
                    EffectRemovalHandler.removeNegativeEffects(player);
                }
            } else {
                playerData.putInt(herbalBathStayedTime, 0);
                playerData.putBoolean(hasEnteredHerbalBath, false);
            }
        }
    }
}
