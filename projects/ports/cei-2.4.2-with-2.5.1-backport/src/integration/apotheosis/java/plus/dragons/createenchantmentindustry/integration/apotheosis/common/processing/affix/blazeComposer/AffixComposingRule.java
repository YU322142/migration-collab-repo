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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer;

import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import java.util.Optional;

public record AffixComposingRule(
        float costMultiplier,
        float augmentingCostMultiplier,
        Optional<Float> maxLevel,
        boolean denyExtraction,
        boolean denyApplying,
        boolean denyMerge,
        boolean denyAugmenting,
        boolean denySuper) {

    private static final Codec<Float> NON_NEGATIVE_FLOAT = Codec.floatRange(0, Float.MAX_VALUE);

    public static final AffixComposingRule DEFAULT = new AffixComposingRule(1, 1, Optional.empty(), false, false, false, false, false);
    public static final Codec<AffixComposingRule> CODEC = RecordCodecBuilder.create(instance -> instance.group(
            NON_NEGATIVE_FLOAT.optionalFieldOf("cost_multiplier", 1F).forGetter(AffixComposingRule::costMultiplier),
            NON_NEGATIVE_FLOAT.optionalFieldOf("augmenting_cost_multiplier", 1F).forGetter(AffixComposingRule::augmentingCostMultiplier),
            NON_NEGATIVE_FLOAT.optionalFieldOf("max_level").forGetter(AffixComposingRule::maxLevel),
            Codec.BOOL.optionalFieldOf("deny_extraction", false).forGetter(AffixComposingRule::denyExtraction),
            Codec.BOOL.optionalFieldOf("deny_applying", false).forGetter(AffixComposingRule::denyApplying),
            Codec.BOOL.optionalFieldOf("deny_merge", false).forGetter(AffixComposingRule::denyMerge),
            Codec.BOOL.optionalFieldOf("deny_augmenting", false).forGetter(AffixComposingRule::denyAugmenting),
            Codec.BOOL.optionalFieldOf("deny_super", false).forGetter(AffixComposingRule::denySuper))
            .apply(instance, AffixComposingRule::new));
    public boolean denies(BlazeComposerMode mode, boolean superMode) {
        if (superMode && denySuper)
            return true;
        return switch (mode) {
            case EXTRACT -> denyExtraction;
            case APPLY -> denyApplying;
            case MERGE -> denyMerge;
        };
    }
}
