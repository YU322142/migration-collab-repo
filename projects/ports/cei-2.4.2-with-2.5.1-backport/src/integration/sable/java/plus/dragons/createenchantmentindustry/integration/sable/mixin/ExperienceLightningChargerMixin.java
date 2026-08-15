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

import com.simibubi.create.AllBlocks;
import dev.ryanhcode.sable.ActiveSableCompanion;
import dev.ryanhcode.sable.Sable;
import java.util.Optional;
import me.fallenbreath.conditionalmixin.api.annotation.Condition;
import me.fallenbreath.conditionalmixin.api.annotation.Restriction;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.LightningRodBlock;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import plus.dragons.createenchantmentindustry.common.fluids.experience.BlazeExperienceBlockEntity;
import plus.dragons.createenchantmentindustry.common.fluids.experience.ExperienceLightningCharger;
import plus.dragons.createenchantmentindustry.integration.ModIntegration;

@Restriction(require = @Condition(ModIntegration.Constants.SABLE))
@Mixin(ExperienceLightningCharger.class)
public class ExperienceLightningChargerMixin {
    @Inject(method = "findChargeableBlock", at = @At("HEAD"), cancellable = true)
    private static void findChargeableBlock$includeSubLevels(Level level, BlockPos pos, CallbackInfoReturnable<Optional<BlockPos>> cir) {
        ActiveSableCompanion helper = Sable.HELPER;
        BlockPos target = helper.runIncludingSubLevels(level, pos.getCenter(), true, helper.getContaining(level, pos),
                (subLevel, candidate) -> level.getBlockState(candidate).is(AllBlocks.EXPERIENCE_BLOCK) ? candidate : null);
        if (target != null)
            cir.setReturnValue(Optional.of(target));
    }

    @Inject(method = "findLightningRodTarget", at = @At("HEAD"), cancellable = true)
    private static void findLightningRodTarget$includeSubLevels(Level level, BlockPos pos, CallbackInfoReturnable<Optional<BlockPos>> cir) {
        ActiveSableCompanion helper = Sable.HELPER;
        BlockPos target = helper.runIncludingSubLevels(level, pos.getCenter(), true, helper.getContaining(level, pos), (subLevel, candidate) -> {
            var state = level.getBlockState(candidate);
            if (state.is(BlazeExperienceBlockEntity.LIGHTNING_ROD_BLOCKS))
                return candidate.relative(state.getValue(LightningRodBlock.FACING).getOpposite());
            return null;
        });
        if (target != null)
            cir.setReturnValue(Optional.of(target));
    }
}
