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

package plus.dragons.createenchantmentindustry.integration.touhou_little_maid.config;

import net.createmod.catnip.config.ConfigBase;

public class CEITouhouLittleMaidServerConfig extends ConfigBase {
    public final ConfigBool experienceLanternDrainMaidExperience = b(true,
            "experienceLanternDrainMaidExperience",
            Comments.experienceLanternDrainMaidExperience);
    public final ConfigInt experienceLanternMaxDrainPerMaid = i(50, 1,
            "experienceLanternMaxDrainPerMaid",
            Comments.experienceLanternMaxDrainPerMaid);

    @Override
    public String getName() {
        return "server";
    }

    static class Comments {
        static final String experienceLanternDrainMaidExperience = "Whether Experience Lanterns drain experience from nearby Touhou Little Maid maids.";
        static final String experienceLanternMaxDrainPerMaid = "The maximum amount of experience an Experience Lantern drains from each maid per operation.";
    }
}
