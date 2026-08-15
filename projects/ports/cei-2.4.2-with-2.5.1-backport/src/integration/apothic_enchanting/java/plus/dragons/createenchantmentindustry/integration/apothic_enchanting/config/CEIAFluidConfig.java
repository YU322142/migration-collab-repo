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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.config;

import net.createmod.catnip.config.ConfigBase;
import net.createmod.catnip.config.ui.ConfigAnnotations;

public class CEIAFluidConfig extends ConfigBase {
    public final ConfigInt infuserFluidCapacity = i(4000, 1000,
            "infuserFluidCapacity",
            Comments.infuserFluidCapacity,
            ConfigAnnotations.RequiresRestart.SERVER.asComment());

    @Override
    public String getName() {
        return "fluids";
    }

    static class Comments {
        static final String infuserFluidCapacity = "The amount of liquid an Infuser can hold (mB).";
    }
}
