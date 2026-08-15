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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer;

import com.mojang.serialization.MapCodec;
import com.simibubi.create.foundation.block.IBE;
import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.ItemInteractionResult;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;
import net.neoforged.neoforge.fluids.FluidUtil;
import org.jetbrains.annotations.Nullable;
import plus.dragons.createdragonsplus.common.advancements.AdvancementBehaviour;
import plus.dragons.createdragonsplus.common.processing.blaze.BlazeBlock;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXBlockEntities;

public class BlazeComposerBlock extends BlazeBlock<BlazeComposerBlockEntity> {
    public BlazeComposerBlock(Properties properties) {
        super(properties);
    }

    @Override
    public void setPlacedBy(Level level, BlockPos pos, BlockState state, @Nullable LivingEntity placer, ItemStack stack) {
        super.setPlacedBy(level, pos, state, placer, stack);
        AdvancementBehaviour.setPlacedBy(level, pos, placer);
    }

    @Override
    protected InteractionResult useWithoutItem(BlockState state, Level level, BlockPos pos, Player player, BlockHitResult hitResult) {
        var blockEntity = getBlockEntity(level, pos);
        if (blockEntity == null)
            return InteractionResult.PASS;
        ItemStack extracted = blockEntity.extractItem(false);
        if (!extracted.isEmpty()) {
            player.getInventory().placeItemBackInInventory(extracted);
            return InteractionResult.sidedSuccess(level.isClientSide);
        }
        return InteractionResult.PASS;
    }

    @Override
    protected ItemInteractionResult useItemOn(ItemStack stack, BlockState state, Level level, BlockPos pos, Player player, InteractionHand hand, BlockHitResult hitResult) {
        if (stack.isEmpty())
            return ItemInteractionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
        var blockEntity = getBlockEntity(level, pos);
        if (blockEntity == null)
            return ItemInteractionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
        if (FluidUtil.getFluidHandler(stack).isPresent()) {
            if (FluidUtil.interactWithFluidHandler(player, hand, blockEntity.getFluidHandler(null)))
                return ItemInteractionResult.sidedSuccess(level.isClientSide);
            return ItemInteractionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
        }
        var remainder = blockEntity.insertItem(stack, false);
        if (ItemStack.isSameItemSameComponents(stack, remainder) && remainder.getCount() == stack.getCount())
            return ItemInteractionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
        player.setItemInHand(hand, remainder);
        return ItemInteractionResult.sidedSuccess(level.isClientSide);
    }

    @Override
    protected void onRemove(BlockState state, Level level, BlockPos pos, BlockState newState, boolean movedByPiston) {
        IBE.onRemove(state, level, pos, newState);
    }

    @Override
    protected MapCodec<BlazeComposerBlock> codec() {
        return simpleCodec(BlazeComposerBlock::new);
    }

    @Override
    public Class<BlazeComposerBlockEntity> getBlockEntityClass() {
        return BlazeComposerBlockEntity.class;
    }

    @Override
    public BlockEntityType<? extends BlazeComposerBlockEntity> getBlockEntityType() {
        return CEIAXBlockEntities.BLAZE_COMPOSER.get();
    }
}
