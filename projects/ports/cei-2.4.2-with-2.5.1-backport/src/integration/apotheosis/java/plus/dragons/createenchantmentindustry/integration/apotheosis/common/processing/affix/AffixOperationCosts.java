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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix;

import dev.shadowsoffire.apotheosis.AdventureConfig;
import dev.shadowsoffire.apotheosis.affix.Affix;
import dev.shadowsoffire.apotheosis.affix.AffixInstance;
import dev.shadowsoffire.apotheosis.affix.AffixType;
import dev.shadowsoffire.placebo.util.EnchantmentUtils;
import net.minecraft.util.Mth;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.AffixComposingRules;
import plus.dragons.createenchantmentindustry.integration.apotheosis.config.CEIAXConfig;

public class AffixOperationCosts {
    public static final float EPSILON = 0.0001F;
    public static final float APOTHEOSIS_AUGMENTING_STEP = 0.25F;
    private static final int DEFAULT_APOTHEOSIS_UPGRADE_LEVEL_COST = 225;

    public static int apotheosisUpgradeReferenceCost() {
        var fluids = CEIAXConfig.server().fluids();
        int defaultExperience = Math.max(1, EnchantmentUtils.getTotalExperienceForLevel(DEFAULT_APOTHEOSIS_UPGRADE_LEVEL_COST));
        int configuredExperience = EnchantmentUtils.getTotalExperienceForLevel(Math.max(0, AdventureConfig.upgradeLevelCost));
        float experienceCost = (float) fluids.affixAugmentorCostExperienceToApotheoticEssenceTotal.get()
                * ((float) configuredExperience / defaultExperience);
        float sigilCost = AdventureConfig.upgradeSigilCost * fluids.affixAugmentorCostSigilToApotheoticEssenceRatio.get();
        return roundPositiveCost(experienceCost + sigilCost);
    }

    public static int augmentingCost(AffixInstance instance, float fromLevel, float toLevel) {
        if (toLevel <= fromLevel + EPSILON)
            return 0;
        var config = CEIAXConfig.server().affixes();
        float stepWeight = Math.max(EPSILON, weightedLevelSpan(0, APOTHEOSIS_AUGMENTING_STEP));
        float upgradeUnits = weightedLevelSpan(fromLevel, toLevel) / stepWeight;
        float cost = apotheosisUpgradeReferenceCost()
                * upgradeUnits
                * typeMultiplier(instance.affix().get().definition().type())
                * config.affixAugmentorCostMultiplier.getF()
                * AffixComposingRules.INSTANCE.getAugmentingCostMultiplier(instance);
        return roundPositiveCost(cost);
    }

    public static float weightedLevelSpan(float fromLevel, float toLevel) {
        fromLevel = Math.max(0, fromLevel);
        toLevel = Math.max(0, toLevel);
        if (toLevel <= fromLevel + EPSILON)
            return 0;
        return levelValue(toLevel) - levelValue(fromLevel);
    }

    public static float levelValue(float level) {
        var config = CEIAXConfig.server().affixes();
        level = Math.max(0, level);
        float standard = Mth.clamp(level, 0, Affix.STANDARD_MAX_LEVEL);
        float crystal = Math.max(0, Math.min(level, Affix.MAX_LEVEL) - Affix.STANDARD_MAX_LEVEL);
        float superSegment = Math.max(0, level - Affix.MAX_LEVEL);
        return standard
                + crystal * config.blazeComposerCrystalLevelMultiplier.getF()
                + (float) Math.pow(superSegment, config.blazeComposerSuperLevelExponent.getF()) * config.blazeComposerSuperLevelMultiplier.getF();
    }

    public static float typeMultiplier(AffixType type) {
        var config = CEIAXConfig.server().affixes();
        return switch (type) {
            case STAT -> config.statAffixTypeCostMultiplier.getF();
            case BASIC_EFFECT -> config.basicEffectAffixTypeCostMultiplier.getF();
            case ABILITY -> config.abilityAffixTypeCostMultiplier.getF();
        };
    }

    public static int roundCost(float cost) {
        return Math.max(1, Math.round(cost));
    }

    public static int roundPositiveCost(float cost) {
        if (cost <= EPSILON)
            return 0;
        return Math.max(1, Math.round(cost));
    }
}
