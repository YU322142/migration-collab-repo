/*
 * Copyright (C) 2025  DragonsPlus
 * SPDX-License-Identifier: LGPL-3.0-or-later
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

package plus.dragons.createenchantmentindustry.integration.sable_apotheosis.common.fluids.tank;

import dev.ryanhcode.sable.Sable;
import java.util.List;
import net.minecraft.util.Mth;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.item.ItemEntity;
import net.neoforged.neoforge.fluids.FluidStack;
import plus.dragons.createdragonsplus.integration.simulated.api.fluids.tank.FragileFluidTankBreakEffectHandler;
import plus.dragons.createdragonsplus.integration.simulated.api.fluids.tank.FragileFluidTankImpactContext;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.kinetics.fan.salvaging.SalvagingHelper;
import plus.dragons.createenchantmentindustry.integration.apotheosis.config.CEIAXConfig;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.registry.CEIAFluids;

public class CEISAXFragileFluidTankBreakEffectHandlers {
    private static final InfusedDragonBreathHandler INFUSED_DRAGON_BREATH = new InfusedDragonBreathHandler();

    private CEISAXFragileFluidTankBreakEffectHandlers() {}

    public static void register() {
        FragileFluidTankBreakEffectHandler.REGISTRY.register(CEIAFluids.INFUSED_DRAGON_BREATH.get(), INFUSED_DRAGON_BREATH);
        FragileFluidTankBreakEffectHandler.REGISTRY.register(CEIAFluids.INFUSED_DRAGON_BREATH_FLOWING.get(), INFUSED_DRAGON_BREATH);
    }

    private static class InfusedDragonBreathHandler implements FragileFluidTankBreakEffectHandler {
        @Override
        public void apply(FragileFluidTankImpactContext context) {
            var livingEntities = getEntitiesInRange(context, LivingEntity.class);
            applySalvaging(context, getEntitiesInRange(context, ItemEntity.class), livingEntities);
            applyDragonBreathDamage(context, livingEntities);
        }

        @Override
        public String getImpactEffectDescriptionKey(FluidStack fluid) {
            return "infused_dragon_breath";
        }

        private static void applySalvaging(FragileFluidTankImpactContext context, List<ItemEntity> items, List<LivingEntity> livingEntities) {
            var utility = CEIAXConfig.server().utility();
            var level = context.level();
            if (utility.fragileFluidTankInfusedDragonBreathSalvageDroppedItems.get()) {
                float chance = utility.fragileFluidTankInfusedDragonBreathDroppedItemSalvageChance.getF();
                for (var item : items)
                    SalvagingHelper.salvageItemEntity(item, level, level.random, chance);
            }
            if (utility.fragileFluidTankInfusedDragonBreathSalvageEquippedItems.get()) {
                float chance = utility.fragileFluidTankInfusedDragonBreathEquippedItemSalvageChance.getF()
                        * Mth.clamp(context.fullness(), 0.0f, 1.0f);
                int maxCount = utility.fragileFluidTankInfusedDragonBreathMaxEquippedItemsPerEntity.get();
                for (var living : livingEntities)
                    SalvagingHelper.salvageEquippedItems(living, level, living.getRandom(), chance, maxCount);
            }
        }

        private static void applyDragonBreathDamage(FragileFluidTankImpactContext context, List<LivingEntity> livingEntities) {
            int amplifier = context.effectAmplifier() + 1;
            for (var living : livingEntities) {
                if (living.isAffectedByPotions())
                    living.addEffect(new MobEffectInstance(MobEffects.HARM, 1, amplifier, false, false, false));
            }
        }
    }

    private static <T extends Entity> List<T> getEntitiesInRange(FragileFluidTankImpactContext context, Class<T> entityClass) {
        return context.level().getEntitiesOfClass(entityClass, context.area(), entity -> isInRangeConsideringSubLevel(context, entity));
    }

    private static boolean isInRangeConsideringSubLevel(FragileFluidTankImpactContext context, Entity entity) {
        var helper = Sable.HELPER;
        if (helper.isInPlotGrid(entity)) {
            return helper.distanceSquaredWithSubLevels(
                    context.level(),
                    entity.position().x,
                    entity.position().y,
                    entity.position().z,
                    context.hitPos().x,
                    context.hitPos().y,
                    context.hitPos().z) <= context.radius() * context.radius();
        }
        return entity.distanceToSqr(context.hitPos().x, context.hitPos().y, context.hitPos().z) <= context.radius() * context.radius();
    }
}
