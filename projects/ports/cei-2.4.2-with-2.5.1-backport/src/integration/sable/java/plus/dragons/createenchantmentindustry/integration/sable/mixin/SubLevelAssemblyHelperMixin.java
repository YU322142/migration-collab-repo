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

package plus.dragons.createenchantmentindustry.integration.sable.mixin;

import com.llamalad7.mixinextras.injector.wrapmethod.WrapMethod;
import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import dev.ryanhcode.sable.api.SubLevelAssemblyHelper;
import me.fallenbreath.conditionalmixin.api.annotation.Condition;
import me.fallenbreath.conditionalmixin.api.annotation.Restriction;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import org.spongepowered.asm.mixin.Mixin;
import plus.dragons.createenchantmentindustry.common.fluids.experience.ExperienceFluidDropContext;
import plus.dragons.createenchantmentindustry.integration.ModIntegration;

@Restriction(require = @Condition(ModIntegration.Constants.SABLE))
@Mixin(SubLevelAssemblyHelper.class)
public class SubLevelAssemblyHelperMixin {
    @WrapMethod(method = "moveBlocks")
    private static void moveBlocks$suppressExperienceFluidDrops(ServerLevel level, SubLevelAssemblyHelper.AssemblyTransform transform, Iterable<BlockPos> blocks, Operation<Void> original) {
        ExperienceFluidDropContext.suppressDuring(() -> original.call(level, transform, blocks));
    }
}
