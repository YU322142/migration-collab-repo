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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.contraptions.actors.enderWovenBag;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import com.simibubi.create.content.contraptions.behaviour.MovementContext;
import com.simibubi.create.content.contraptions.render.ContraptionMatrices;
import com.simibubi.create.content.equipment.toolbox.ToolboxBlock;
import com.simibubi.create.foundation.blockEntity.renderer.SmartBlockEntityRenderer;
import com.simibubi.create.foundation.virtualWorld.VirtualRenderWorld;
import net.createmod.catnip.render.CachedBuffers;
import net.createmod.catnip.render.SuperByteBuffer;
import net.minecraft.client.renderer.LevelRenderer;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.state.BlockState;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.client.registry.CEIAPartialModels;

public class EnderWovenBagRenderer extends SmartBlockEntityRenderer<EnderWovenBagBlockEntity> {
    public EnderWovenBagRenderer(BlockEntityRendererProvider.Context context) {
        super(context);
    }

    @Override
    protected void renderSafe(EnderWovenBagBlockEntity bag, float partialTicks, PoseStack poseStack, MultiBufferSource buffer, int light, int overlay) {
        super.renderSafe(bag, partialTicks, poseStack, buffer, light, overlay);
        BlockState state = bag.getBlockState();

        Direction facing = state.getValue(ToolboxBlock.FACING)
                .getOpposite();
        VertexConsumer builder = buffer.getBuffer(RenderType.cutout());

        SuperByteBuffer lit = CachedBuffers.partial(bag.getEntities().full() ? CEIAPartialModels.ENDER_WOVEN_BAG_LIGHT_ON : CEIAPartialModels.ENDER_WOVEN_BAG_LIGHT_OFF, state);
        lit.center()
                .rotateYDegrees(-facing.toYRot())
                .uncenter()
                .light(light)
                .renderInto(poseStack, builder);

        if (bag.pocketOpen != 0) {
            SuperByteBuffer pocket = CachedBuffers.partial(CEIAPartialModels.ENDER_WOVEN_BAG_CLOSED_POCKET, state);
            pocket.translate(facing.getStepX() * -6 / 16f, 0, facing.getStepZ() * -6 / 16f)
                    .center()
                    .scale(bag.pocketOpen)
                    .rotateYDegrees(-facing.toYRot())
                    .uncenter()
                    .light(light)
                    .renderInto(poseStack, builder);
        }

        if (bag.pocketOpen != 1) {
            SuperByteBuffer pocket = CachedBuffers.partial(CEIAPartialModels.ENDER_WOVEN_BAG_OPEN_POCKET, state);
            pocket.translate(facing.getStepX() * -6 / 16f, 0, facing.getStepZ() * -6 / 16f)
                    .center()
                    .scale(1 - bag.pocketOpen)
                    .rotateYDegrees(-facing.toYRot())
                    .uncenter()
                    .light(light)
                    .renderInto(poseStack, builder);
        }
    }

    public static void renderInContraption(MovementContext context, VirtualRenderWorld renderWorld,
            ContraptionMatrices matrices, MultiBufferSource buffer) {
        BlockState state = context.state;
        VertexConsumer vb = buffer.getBuffer(RenderType.cutout());
        Direction facing = state.getValue(ToolboxBlock.FACING).getOpposite();

        SuperByteBuffer lit = CachedBuffers.partial(EnderWovenBagMovementBehaviour.renderFull(context) ? CEIAPartialModels.ENDER_WOVEN_BAG_LIGHT_ON : CEIAPartialModels.ENDER_WOVEN_BAG_LIGHT_OFF, state);
        SuperByteBuffer pocket = CachedBuffers.partial(EnderWovenBagMovementBehaviour.renderFull(context) ? CEIAPartialModels.ENDER_WOVEN_BAG_CLOSED_POCKET : CEIAPartialModels.ENDER_WOVEN_BAG_OPEN_POCKET, state);

        lit.transform(matrices.getModel())
                .center()
                .light(LevelRenderer.getLightColor(renderWorld, context.localPos))
                .useLevelLight(context.world, matrices.getWorld())
                .rotateYDegrees(-facing.toYRot())
                .uncenter()
                .renderInto(matrices.getViewProjection(), vb);

        pocket.transform(matrices.getModel())
                .translate(facing.getStepX() * -6 / 16f, 0, facing.getStepZ() * -6 / 16f)
                .center()
                .light(LevelRenderer.getLightColor(renderWorld, context.localPos))
                .useLevelLight(context.world, matrices.getWorld())
                .rotateYDegrees(-facing.toYRot())
                .uncenter()
                .renderInto(matrices.getViewProjection(), vb);
    }
}
