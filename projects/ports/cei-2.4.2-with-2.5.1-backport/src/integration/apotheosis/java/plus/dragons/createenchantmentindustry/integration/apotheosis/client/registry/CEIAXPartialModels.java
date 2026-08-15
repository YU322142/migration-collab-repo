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

package plus.dragons.createenchantmentindustry.integration.apotheosis.client.registry;

import dev.engine_room.flywheel.lib.model.baked.PartialModel;
import plus.dragons.createenchantmentindustry.common.CEICommon;

public class CEIAXPartialModels {
    public static final PartialModel SPECIAL_CASING = block("belt_casing/special");
    public static final PartialModel SPECIAL_CASING_WITH_SHAFT = block("belt_casing/special_with_shaft");
    public static final PartialModel SPECIAL_CASING_TOP_ONLY = block("belt_casing/special_top_only");

    public static final PartialModel GEM_CUTTER_CRYSTAL_NEEDLE = block("gem_cutter/crystal_needle");
    public static final PartialModel GEM_CUTTER_CRYSTAL_NEEDLE_POWERED = block("gem_cutter/crystal_needle_powered");
    public static final PartialModel GEM_CUTTER_CRYSTAL_SPHERE_VERTICAL_ALIGNED_FRAME = block("gem_cutter/vertical_aligned");
    public static final PartialModel GEM_CUTTER_CRYSTAL_SPHERE_VERTICAL_ALIGNED_FRAME_POWERED = block("gem_cutter/vertical_aligned_powered");
    public static final PartialModel GEM_CUTTER_CRYSTAL_SPHERE_VERTICAL_FRAME = block("gem_cutter/vertical");
    public static final PartialModel GEM_CUTTER_CRYSTAL_SPHERE_VERTICAL_FRAME_POWERED = block("gem_cutter/vertical_powered");
    public static final PartialModel GEM_CUTTER_CRYSTAL_SPHERE_HORIZONTAL_FRAME = block("gem_cutter/horizontal");
    public static final PartialModel GEM_CUTTER_CRYSTAL_SPHERE_HORIZONTAL_FRAME_POWERED = block("gem_cutter/horizontal_powered");

    public static final PartialModel AFFIX_AUGMENTOR_PLATE = block("affix_augmentor/plate");
    public static final PartialModel AFFIX_AUGMENTOR_PLATE_POWERED = block("affix_augmentor/plate_powered");
    public static final PartialModel AFFIX_AUGMENTOR_BIG_COLUMN = block("affix_augmentor/big_column");
    public static final PartialModel AFFIX_AUGMENTOR_SMALL_COLUMN = block("affix_augmentor/small_column");
    public static final PartialModel AFFIX_AUGMENTOR_NEEDLE = block("affix_augmentor/needle");

    public static final PartialModel BLAZE_COMPOSER_HAT = block("blaze/composer_hat");
    public static final PartialModel BLAZE_COMPOSER_HAT_SMALL = block("blaze/composer_hat_small");

    public static void register() {}

    private static PartialModel block(String path) {
        return PartialModel.of(CEICommon.asResource("block/" + path));
    }
}
