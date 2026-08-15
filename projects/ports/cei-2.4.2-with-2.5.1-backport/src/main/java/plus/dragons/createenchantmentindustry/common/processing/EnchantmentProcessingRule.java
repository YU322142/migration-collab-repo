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

package plus.dragons.createenchantmentindustry.common.processing;

import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import java.util.Optional;
import net.minecraft.util.ExtraCodecs;

public record EnchantmentProcessingRule(
        LevelExtensionRule levelExtension,
        CostMultiplierRule costMultiplier) {
    public static final EnchantmentProcessingRule DEFAULT = new EnchantmentProcessingRule(
            LevelExtensionRule.DEFAULT,
            CostMultiplierRule.DEFAULT);
    public static final Codec<EnchantmentProcessingRule> CODEC = RecordCodecBuilder.create(instance -> instance.group(
            LevelExtensionRule.CODEC.optionalFieldOf("level_extension", LevelExtensionRule.DEFAULT)
                    .forGetter(EnchantmentProcessingRule::levelExtension),
            CostMultiplierRule.CODEC.optionalFieldOf("cost_multiplier", CostMultiplierRule.DEFAULT)
                    .forGetter(EnchantmentProcessingRule::costMultiplier))
            .apply(instance, EnchantmentProcessingRule::new));

    public static EnchantmentProcessingRule enchanterAndForgerExtension(int blazeEnchanter, int blazeForger) {
        return new EnchantmentProcessingRule(
                new LevelExtensionRule(Optional.of(blazeEnchanter), Optional.of(blazeForger)),
                CostMultiplierRule.DEFAULT);
    }

    public record LevelExtensionRule(
            Optional<Integer> blazeEnchanter,
            Optional<Integer> blazeForger) {
        public static final LevelExtensionRule DEFAULT = new LevelExtensionRule(Optional.empty(), Optional.empty());
        public static final Codec<LevelExtensionRule> CODEC = RecordCodecBuilder.create(instance -> instance.group(
                ExtraCodecs.NON_NEGATIVE_INT.optionalFieldOf("blaze_enchanter").forGetter(LevelExtensionRule::blazeEnchanter),
                ExtraCodecs.NON_NEGATIVE_INT.optionalFieldOf("blaze_forger").forGetter(LevelExtensionRule::blazeForger))
                .apply(instance, LevelExtensionRule::new));
    }

    public record CostMultiplierRule(
            EnchanterCostMultipliers blazeEnchanter,
            ForgerCostMultipliers blazeForger) {
        public static final CostMultiplierRule DEFAULT = new CostMultiplierRule(
                EnchanterCostMultipliers.DEFAULT,
                ForgerCostMultipliers.DEFAULT);
        public static final Codec<CostMultiplierRule> CODEC = RecordCodecBuilder.create(instance -> instance.group(
                EnchanterCostMultipliers.CODEC.optionalFieldOf("blaze_enchanter", EnchanterCostMultipliers.DEFAULT)
                        .forGetter(CostMultiplierRule::blazeEnchanter),
                ForgerCostMultipliers.CODEC.optionalFieldOf("blaze_forger", ForgerCostMultipliers.DEFAULT)
                        .forGetter(CostMultiplierRule::blazeForger))
                .apply(instance, CostMultiplierRule::new));
    }

    public record EnchanterCostMultipliers(
            Optional<Float> normal,
            Optional<Float> super_,
            Optional<Float> direct,
            Optional<Float> template) {
        public static final EnchanterCostMultipliers DEFAULT = new EnchanterCostMultipliers(
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                Optional.empty());
        public static final Codec<EnchanterCostMultipliers> CODEC = RecordCodecBuilder.create(instance -> instance.group(
                Codec.floatRange(0, Float.MAX_VALUE).optionalFieldOf("normal").forGetter(EnchanterCostMultipliers::normal),
                Codec.floatRange(0, Float.MAX_VALUE).optionalFieldOf("super").forGetter(EnchanterCostMultipliers::super_),
                Codec.floatRange(0, Float.MAX_VALUE).optionalFieldOf("direct").forGetter(EnchanterCostMultipliers::direct),
                Codec.floatRange(0, Float.MAX_VALUE).optionalFieldOf("template").forGetter(EnchanterCostMultipliers::template))
                .apply(instance, EnchanterCostMultipliers::new));
    }

    public record ForgerCostMultipliers(
            Optional<Float> normal,
            Optional<Float> super_,
            Optional<Float> merge,
            Optional<Float> apply,
            Optional<Float> extract) {
        public static final ForgerCostMultipliers DEFAULT = new ForgerCostMultipliers(
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                Optional.empty());
        public static final Codec<ForgerCostMultipliers> CODEC = RecordCodecBuilder.create(instance -> instance.group(
                Codec.floatRange(0, Float.MAX_VALUE).optionalFieldOf("normal").forGetter(ForgerCostMultipliers::normal),
                Codec.floatRange(0, Float.MAX_VALUE).optionalFieldOf("super").forGetter(ForgerCostMultipliers::super_),
                Codec.floatRange(0, Float.MAX_VALUE).optionalFieldOf("merge").forGetter(ForgerCostMultipliers::merge),
                Codec.floatRange(0, Float.MAX_VALUE).optionalFieldOf("apply").forGetter(ForgerCostMultipliers::apply),
                Codec.floatRange(0, Float.MAX_VALUE).optionalFieldOf("extract").forGetter(ForgerCostMultipliers::extract))
                .apply(instance, ForgerCostMultipliers::new));
    }
}
