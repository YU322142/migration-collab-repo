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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.socket.gem.gemCutter;

import dev.shadowsoffire.apotheosis.socket.gem.Purity;
import plus.dragons.createenchantmentindustry.integration.apotheosis.config.CEIAXConfig;

public class GemCutting {
    private GemCutting() {}

    public static boolean canCut(Purity purity) {
        return purity != Purity.PERFECT;
    }

    public static Purity resultPurity(Purity purity) {
        return canCut(purity) ? purity.next() : purity;
    }

    public static int getCutCost(Purity purity) {
        if (!canCut(purity))
            return 0;
        int cost = switch (purity) {
            case CRACKED -> CEIAXConfig.server().fluids().gemCutterCostCrackedToChipped.get();
            case CHIPPED -> CEIAXConfig.server().fluids().gemCutterCostChippedToFlawed.get();
            case FLAWED -> CEIAXConfig.server().fluids().gemCutterCostFlawedToNormal.get();
            case NORMAL -> CEIAXConfig.server().fluids().gemCutterCostNormalToFlawless.get();
            case FLAWLESS -> CEIAXConfig.server().fluids().gemCutterCostFlawlessToPerfect.get();
            case PERFECT -> 0;
        };
        return Math.max(1, Math.round(cost * CEIAXConfig.server().fluids().gemCutterCostMultiplier.getF()));
    }
}
