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

package plus.dragons.createenchantmentindustry.integration.apotheosis.config;

import net.createmod.catnip.config.ConfigBase;

public class CEIAXUtilityConfig extends ConfigBase {
    public final ConfigFloat bulkSalvagingSalvageEquippedItemProbability = f(0.02f, 0, 1,
            "bulkSalvagingSalvageEquippedItemProbability",
            Comments.bulkSalvagingSalvageEquippedItemProbability);
    public final ConfigBool fragileFluidTankInfusedDragonBreathSalvageDroppedItems = b(true,
            "fragileFluidTankInfusedDragonBreathSalvageDroppedItems",
            Comments.fragileFluidTankInfusedDragonBreathSalvageDroppedItems);
    public final ConfigFloat fragileFluidTankInfusedDragonBreathDroppedItemSalvageChance = f(1.0f, 0, 1,
            "fragileFluidTankInfusedDragonBreathDroppedItemSalvageChance",
            Comments.fragileFluidTankInfusedDragonBreathDroppedItemSalvageChance);
    public final ConfigBool fragileFluidTankInfusedDragonBreathSalvageEquippedItems = b(true,
            "fragileFluidTankInfusedDragonBreathSalvageEquippedItems",
            Comments.fragileFluidTankInfusedDragonBreathSalvageEquippedItems);
    public final ConfigFloat fragileFluidTankInfusedDragonBreathEquippedItemSalvageChance = f(0.25f, 0, 1,
            "fragileFluidTankInfusedDragonBreathEquippedItemSalvageChance",
            Comments.fragileFluidTankInfusedDragonBreathEquippedItemSalvageChance);
    public final ConfigInt fragileFluidTankInfusedDragonBreathMaxEquippedItemsPerEntity = i(1, 0,
            "fragileFluidTankInfusedDragonBreathMaxEquippedItemsPerEntity",
            Comments.fragileFluidTankInfusedDragonBreathMaxEquippedItemsPerEntity);

    @Override
    public String getName() {
        return "ex-utility";
    }

    static class Comments {
        static final String bulkSalvagingSalvageEquippedItemProbability = "The probability of Bulk Salvaging air current destroying equipped items.";
        static final String fragileFluidTankInfusedDragonBreathSalvageDroppedItems = "Whether Fragile Fluid Tanks filled with Infused Dragon's Breath salvage dropped items on impact.";
        static final String fragileFluidTankInfusedDragonBreathDroppedItemSalvageChance = "The probability of each dropped item being salvaged by a Fragile Fluid Tank impact with Infused Dragon's Breath.";
        static final String fragileFluidTankInfusedDragonBreathSalvageEquippedItems = "Whether Fragile Fluid Tanks filled with Infused Dragon's Breath can salvage equipped items on impact.";
        static final String fragileFluidTankInfusedDragonBreathEquippedItemSalvageChance = "The max probability of each living entity having equipped items salvaged by a full Fragile Fluid Tank of Infused Dragon's Breath. Actual probability scales with tank fullness.";
        static final String fragileFluidTankInfusedDragonBreathMaxEquippedItemsPerEntity = "The maximum equipped items a Fragile Fluid Tank impact with Infused Dragon's Breath can salvage from each living entity.";
    }
}
