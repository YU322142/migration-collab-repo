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

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import com.simibubi.create.foundation.blockEntity.SmartBlockEntity;
import com.simibubi.create.foundation.blockEntity.behaviour.BlockEntityBehaviour;
import me.fallenbreath.conditionalmixin.api.annotation.Condition;
import me.fallenbreath.conditionalmixin.api.annotation.Restriction;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import plus.dragons.createenchantmentindustry.integration.ModIntegration;
import plus.dragons.createenchantmentindustry.integration.sable.SablePositions;

@Restriction(require = {
        @Condition(ModIntegration.Constants.SABLE),
        @Condition(ModIntegration.Constants.APOTHIC_ENCHANTING),
})
@Mixin(targets = "plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.contraptions.actors.enderWovenBag.CaptureEntityBehaviour")
public abstract class CaptureEntityBehaviourMixin extends BlockEntityBehaviour {
    public CaptureEntityBehaviourMixin(SmartBlockEntity be) {
        super(be);
    }

    @WrapOperation(method = "lazyTick", at = @At(value = "INVOKE", target = "Lnet/minecraft/core/BlockPos;getCenter()Lnet/minecraft/world/phys/Vec3;"))
    private Vec3 lazyTick$projectBagCenter(BlockPos pos, Operation<Vec3> original) {
        return SablePositions.project(blockEntity.getLevel(), original.call(pos));
    }
}
