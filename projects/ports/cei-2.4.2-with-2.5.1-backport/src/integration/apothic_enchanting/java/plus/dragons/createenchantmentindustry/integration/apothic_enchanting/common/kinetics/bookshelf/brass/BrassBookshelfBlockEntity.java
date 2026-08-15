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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.kinetics.bookshelf.brass;

import com.simibubi.create.api.equipment.goggles.IHaveGoggleInformation;
import com.simibubi.create.content.kinetics.base.KineticBlockEntity;
import com.simibubi.create.foundation.blockEntity.behaviour.BlockEntityBehaviour;
import com.simibubi.create.foundation.blockEntity.behaviour.ValueBoxTransform;
import java.util.List;
import net.createmod.catnip.lang.Lang;
import net.createmod.catnip.lang.LangBuilder;
import net.createmod.catnip.math.VecHelper;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.network.chat.Component;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.kinetics.bookshelf.EnchantmentStatType;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.kinetics.bookshelf.IHaveStatType;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.kinetics.bookshelf.StatTypeBehaviour;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.kinetics.bookshelf.StatValueBehaviour;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.config.CEIAConfig;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.util.CEIALang;

public class BrassBookshelfBlockEntity extends KineticBlockEntity implements IHaveGoggleInformation, IHaveStatType {
    protected StatTypeBehaviour statType;
    protected StatValueBehaviour statValue;

    public BrassBookshelfBlockEntity(BlockEntityType<?> type, BlockPos pos, BlockState state) {
        super(type, pos, state);
    }

    @Override
    public void addBehaviours(List<BlockEntityBehaviour> behaviours) {
        this.statType = new StatTypeBehaviour(CEIALang.translate("gui.bookshelf.stat_type").component(), this, new StatTypeTransform());
        this.statValue = new StatValueBehaviour(CEIALang.translate("gui.bookshelf.stat_value").component(), this, this,
                new StatValueTransform(), statType -> statType == EnchantmentStatType.ETERNA ? CEIAConfig.server().stats().brassBookshelfMaxEterna.get() : (int) (statType == EnchantmentStatType.QUANTA ? CEIAConfig.server().stats().brassBookshelfMaxQuanta.get() * 100 : CEIAConfig.server().stats().brassBookshelfMaxArcana.get() * 100),
                false);
        behaviours.add(this.statType);
        behaviours.add(this.statValue);
    }

    @Override
    public EnchantmentStatType getStatType() {
        return statType.get();
    }

    public int eterna() {
        return statType.get() == EnchantmentStatType.ETERNA && isSpeedRequirementFulfilled() ? statValue.getValue() : 0;
    }

    public float quanta() {
        return statType.get() == EnchantmentStatType.QUANTA && isSpeedRequirementFulfilled() ? statValue.getValue() : 0;
    }

    public float arcana() {
        return statType.get() == EnchantmentStatType.ARCANA && isSpeedRequirementFulfilled() ? statValue.getValue() : 0;
    }

    public boolean allowTreasure() {
        return CEIAConfig.server().stats().brassBookshelfAllowTreasures.get() && isSpeedRequirementFulfilled();
    }

    private static class StatTypeTransform extends ValueBoxTransform.Sided {
        @Override
        protected Vec3 getSouthLocation() {
            return VecHelper.voxelSpace(8, 8, 16);
        }

        @Override
        protected boolean isSideActive(BlockState state, Direction direction) {
            return direction == Direction.UP;
        }
    }

    private static class StatValueTransform extends StatTypeTransform {
        @Override
        protected boolean isSideActive(BlockState state, Direction direction) {
            return direction.getAxis().isHorizontal();
        }
    }

    @Override
    public boolean addToGoggleTooltip(List<Component> tooltip, boolean isPlayerSneaking) {
        super.addToGoggleTooltip(tooltip, isPlayerSneaking);
        CEIALang.translate("gui.goggles.apotheotic_stats")
                .forGoggles(tooltip);
        var type = statType.get();
        LangBuilder stat = CEIALang.translate("gui.goggles.bookshelf." + Lang.asId(type.name()))
                .add(Component.literal(statValue.getValue() + (type == EnchantmentStatType.ETERNA ? ".00" : ".00%")))
                .style(type == EnchantmentStatType.ETERNA ? ChatFormatting.GREEN : type == EnchantmentStatType.ARCANA ? ChatFormatting.LIGHT_PURPLE : ChatFormatting.RED);
        if (!isSpeedRequirementFulfilled())
            stat.add(CEIALang.translate("gui.goggles.bookshelf.inactive"));
        stat.forGoggles(tooltip);
        if (allowTreasure())
            CEIALang.translate("gui.goggles.bookshelf.allow_treasure").style(ChatFormatting.GOLD).forGoggles(tooltip);
        return true;
    }
}
