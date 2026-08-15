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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.kinetics.belt.lowerProcessingAppliance;

import com.simibubi.create.AllBlocks;
import com.simibubi.create.content.kinetics.belt.BeltBlock;
import com.simibubi.create.content.kinetics.belt.BeltSlope;
import com.simibubi.create.content.processing.AssemblyOperatorBlockItem;
import com.simibubi.create.content.processing.AssemblyOperatorUseContext;
import com.simibubi.create.content.processing.basin.BasinBlock;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import plus.dragons.createdragonsplus.util.CodeReference;

@CodeReference(value = AssemblyOperatorBlockItem.class, source = "create", license = "mit")
public class LowerAssemblyOperatorBlockItem extends BlockItem {
    public LowerAssemblyOperatorBlockItem(Block block, Properties properties) {
        super(block, properties);
    }

    @Override
    public InteractionResult place(BlockPlaceContext context) {
        BlockPos placedOnPos = context.getClickedPos()
                .relative(context.getClickedFace()
                        .getOpposite());
        Level level = context.getLevel();
        BlockState placedOnState = level
                .getBlockState(placedOnPos);
        if (operatesOn(level, placedOnPos, placedOnState) && context.getClickedFace() == Direction.UP) {
            if (level.getBlockState(placedOnPos.above())
                    .canBeReplaced())
                context = adjustContext(context, placedOnPos);
            else
                return InteractionResult.FAIL;
        }

        return super.place(context);
    }

    protected BlockPlaceContext adjustContext(BlockPlaceContext context, BlockPos placedOnPos) {
        BlockPos up = placedOnPos.above();
        return new AssemblyOperatorUseContext(context.getLevel(), context.getPlayer(), context.getHand(), context.getItemInHand(), new BlockHitResult(new Vec3((double) up.getX() + 0.5D + (double) Direction.UP.getStepX() * 0.5D, (double) up.getY() + 0.5D + (double) Direction.UP.getStepY() * 0.5D, (double) up.getZ() + 0.5D + (double) Direction.UP.getStepZ() * 0.5D), Direction.UP, up, false));
    }

    protected boolean operatesOn(LevelReader world, BlockPos pos, BlockState placedOnState) {
        if (AllBlocks.BELT.has(placedOnState))
            return placedOnState.getValue(BeltBlock.SLOPE) == BeltSlope.HORIZONTAL;
        return BasinBlock.isBasin(world, pos) || AllBlocks.DEPOT.has(placedOnState); // Ejector won't be supported since no space for eject.
    }
}
