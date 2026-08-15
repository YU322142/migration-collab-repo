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

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import com.simibubi.create.AllPartialModels;
import com.simibubi.create.content.kinetics.base.KineticBlockEntityRenderer;
import dev.engine_room.flywheel.api.visualization.VisualizationManager;
import net.createmod.catnip.render.CachedBuffers;
import net.createmod.catnip.render.SuperByteBuffer;
import net.minecraft.client.renderer.LevelRenderer;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.core.Direction;

public class BrassBookshelfRenderer extends KineticBlockEntityRenderer<BrassBookshelfBlockEntity> {
    public BrassBookshelfRenderer(BlockEntityRendererProvider.Context context) {
        super(context);
    }

    @Override
    protected void renderSafe(BrassBookshelfBlockEntity be, float partialTicks, PoseStack ms, MultiBufferSource buffer,
            int light, int overlay) {
        if (VisualizationManager.supportsVisualization(be.getLevel())) return;

        VertexConsumer vb = buffer.getBuffer(RenderType.cutoutMipped());
        int lightBehind = LevelRenderer.getLightColor(be.getLevel(), be.getBlockPos().relative(Direction.DOWN));
        SuperByteBuffer shaftHalf = CachedBuffers.partialFacing(AllPartialModels.SHAFT_HALF, be.getBlockState(), Direction.DOWN);
        standardKineticRotationTransform(shaftHalf, be, lightBehind).renderInto(ms, vb);
    }
}
