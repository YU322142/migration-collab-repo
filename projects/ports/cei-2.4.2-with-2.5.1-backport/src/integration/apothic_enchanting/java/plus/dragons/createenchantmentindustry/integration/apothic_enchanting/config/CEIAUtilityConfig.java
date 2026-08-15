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

public class CEIAUtilityConfig extends ConfigBase {
    public final ConfigInt enderWovenBagCapacity = i(6, 0,
            "enderWovenBagCapacity",
            Comments.enderWovenBagCapacity,
            ConfigAnnotations.RequiresRestart.SERVER.asComment());
    public final ConfigBool enderWovenBagPullToggle = b(true,
            "enderWovenBagPullToggle",
            Comments.enderWovenBagPullToggle);
    public final ConfigBool enderWovenBagPullBossToggle = b(false,
            "enderWovenBagPullBossToggle",
            Comments.enderWovenBagPullBossToggle);
    public final ConfigInt enderWovenBagPullRadius = i(5, 0,
            "enderWovenBagPullRadius",
            Comments.enderWovenBagPullRadius);
    public final ConfigFloat enderWovenBagPullForceMultiplier = f(.1f, 0.0f, .5f,
            "enderWovenBagPullForceMultiplier",
            Comments.enderWovenBagPullForceMultiplier);
    public final ConfigInt enderWovenBagStopDisableDurationAfterReleasingOnContraption = i(60, 0,
            "enderWovenBagStopDisableDurationAfterReleasingOnContraption",
            Comments.enderWovenBagStopDisableDurationAfterReleasingOnContraption);

    @Override
    public String getName() {
        return "utility";
    }

    static class Comments {
        static final String enderWovenBagCapacity = "The max entities an Ender Woven Bag can store.";
        static final String enderWovenBagPullToggle = "Whether the Ender Woven Bag will pull in entities from nearby.";
        static final String enderWovenBagPullBossToggle = "Whether the Ender Woven Bag will pull in bosses from nearby.";
        static final String enderWovenBagPullRadius = "The range at which entities will be pulled into the lantern.";
        static final String enderWovenBagPullForceMultiplier = "Modifier for the amount of force with which to pull entities.";
        static final String enderWovenBagStopDisableDurationAfterReleasingOnContraption = "The duration of being disabled after releasing mob when on contraption, in tick.";
    }
}
