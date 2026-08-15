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

package plus.dragons.createenchantmentindustry.api.registry;

import net.minecraft.core.Registry;
import net.minecraft.resources.ResourceKey;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.common.fluids.printer.behaviour.PrintingBehaviourProvider;

/** Keys for registries added by Create: Enchantment Industry. */
public final class CEIRegistries {
    public static final ResourceKey<Registry<PrintingBehaviourProvider>> PRINTING_BEHAVIOUR_PROVIDER = key("printing_behaviour");

    private CEIRegistries() {
        throw new AssertionError("This class should not be instantiated");
    }

    private static <T> ResourceKey<Registry<T>> key(String name) {
        return ResourceKey.createRegistryKey(CEICommon.asResource(name));
    }
}
