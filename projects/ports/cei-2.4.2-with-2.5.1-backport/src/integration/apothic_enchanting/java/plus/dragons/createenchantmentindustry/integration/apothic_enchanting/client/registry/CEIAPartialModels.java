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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.client.registry;

import dev.engine_room.flywheel.lib.model.baked.PartialModel;
import plus.dragons.createenchantmentindustry.common.CEICommon;

public class CEIAPartialModels {
    public static final PartialModel INFUSER_ETERNA_NEEDLE = block("infuser/eterna_needle");
    public static final PartialModel INFUSER_ARCANA_NEEDLE = block("infuser/arcana_needle");
    public static final PartialModel INFUSER_QUANTA_NEEDLE = block("infuser/quanta_needle");
    public static final PartialModel ENDER_WOVEN_BAG_LIGHT_ON = block("ender_woven_bag/light_on");
    public static final PartialModel ENDER_WOVEN_BAG_LIGHT_OFF = block("ender_woven_bag/light_off");
    public static final PartialModel ENDER_WOVEN_BAG_OPEN_POCKET = block("ender_woven_bag/open_pocket");
    public static final PartialModel ENDER_WOVEN_BAG_CLOSED_POCKET = block("ender_woven_bag/closed_pocket");

    public static void register() {}

    private static PartialModel block(String path) {
        return PartialModel.of(CEICommon.asResource("block/" + path));
    }
}
