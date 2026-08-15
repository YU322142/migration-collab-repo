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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.template;

import java.util.function.IntFunction;
import net.minecraft.util.ByIdMap;
import net.minecraft.util.StringRepresentable;
import plus.dragons.createenchantmentindustry.integration.apotheosis.config.CEIAXConfig;

public enum AffixTemplateTier implements StringRepresentable {
    BRASS("brass"),
    CRYSTAL("crystal"),
    APOTHEOTIC("apotheotic");

    public static final IntFunction<AffixTemplateTier> BY_ID = ByIdMap.continuous(Enum::ordinal, values(), ByIdMap.OutOfBoundsStrategy.CLAMP);

    private final String name;

    AffixTemplateTier(String name) {
        this.name = name;
    }

    @Override
    public String getSerializedName() {
        return name;
    }

    public boolean canHold(float level) {
        return level <= getMaxLevel() + 0.0001F;
    }

    public boolean canHold(AffixTemplateData data) {
        return data.entries().stream().allMatch(entry -> canHold(entry.level()));
    }

    public float getMaxLevel() {
        var config = CEIAXConfig.server().affixes();
        return switch (this) {
            case BRASS -> config.brassAffixTemplateMaxLevel.getF();
            case CRYSTAL -> config.crystalAffixTemplateMaxLevel.getF();
            case APOTHEOTIC -> config.apotheoticAffixTemplateMaxLevel.getF();
        };
    }

    public boolean isAtLeast(AffixTemplateTier tier) {
        return ordinal() >= tier.ordinal();
    }

    public boolean isSuper() {
        return this == APOTHEOTIC;
    }

    public boolean matchesSuperMode(boolean superMode) {
        return isSuper() == superMode;
    }
}
