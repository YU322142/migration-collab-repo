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

public class CEIAStatsConfig extends ConfigBase {
    public final ConfigInt brassBookshelfMaxEterna = i(25, 1, 100,
            "brassBookshelfMaxEterna",
            CEIAStatsConfig.Comments.brassBookshelfMaxEterna,
            ConfigAnnotations.RequiresRestart.SERVER.asComment());

    public final ConfigFloat brassBookshelfMaxQuanta = f(0.25f, 0.01f, 1f,
            "brassBookshelfMaxQuanta",
            CEIAStatsConfig.Comments.brassBookshelfMaxQuanta,
            ConfigAnnotations.RequiresRestart.SERVER.asComment());

    public final ConfigFloat brassBookshelfMaxArcana = f(0.25f, 0.01f, 1f,
            "brassBookshelfMaxArcana",
            CEIAStatsConfig.Comments.brassBookshelfMaxArcana,
            ConfigAnnotations.RequiresRestart.SERVER.asComment());

    public final ConfigBool brassBookshelfAllowTreasures = b(true,
            "brassBookshelfAllowTreasures",
            CEIAStatsConfig.Comments.brassBookshelfAllowTreasures,
            ConfigAnnotations.RequiresRestart.SERVER.asComment());

    public final ConfigInt multipleBrassBookshelfMaxEterna = i(100, 1, 100,
            "multipleBrassBookshelfMaxEterna",
            CEIAStatsConfig.Comments.multipleBrassBookshelfMaxEterna,
            ConfigAnnotations.RequiresRestart.SERVER.asComment());

    public final ConfigBool creativeBookshelfAllowTreasures = b(true,
            "creativeBookshelfAllowTreasures",
            CEIAStatsConfig.Comments.creativeBookshelfAllowTreasures,
            ConfigAnnotations.RequiresRestart.SERVER.asComment());

    @Override
    public String getName() {
        return "stats";
    }

    static class Comments {
        static final String brassBookshelfMaxEterna = "The max Eterna a Brass Bookshelf can provide.";
        static final String brassBookshelfMaxQuanta = "The max Quanta a Brass Bookshelf can provide.";
        static final String brassBookshelfMaxArcana = "The max Arcana a Brass Bookshelf can provide.";
        static final String brassBookshelfAllowTreasures = "Brass Bookshelf can provide treasures.";
        static final String multipleBrassBookshelfMaxEterna = "The max Eterna Brass Bookshelves can provide.";
        static final String creativeBookshelfAllowTreasures = "Creative Bookshelf can provide treasures.";
    }
}
