package com.github.ysbbbbbb.kaleidoscopecookery.client.render.block;

import com.github.ysbbbbbb.kaleidoscopecookery.block.kitchen.ChoppingBoardBlock;
import com.github.ysbbbbbb.kaleidoscopecookery.blockentity.kitchen.ChoppingBoardBlockEntity;
import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import com.mojang.math.Axis;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.Sheets;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.client.renderer.entity.ItemRenderer;
import net.minecraft.client.resources.model.BakedModel;
import net.minecraft.client.resources.model.ModelManager;
import net.minecraft.client.resources.model.ModelResourceLocation;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;

public class ChoppingBoardBlockEntityRender implements BlockEntityRenderer<ChoppingBoardBlockEntity> {
    private static final ResourceLocation EMPTY_MODEL_ID = ResourceLocation.fromNamespaceAndPath("minecraft", "air");
    private final ItemRenderer itemRenderer;

    public ChoppingBoardBlockEntityRender(BlockEntityRendererProvider.Context context) {
        this.itemRenderer = context.getItemRenderer();
    }

    @Override
    public void render(ChoppingBoardBlockEntity choppingBoard, float partialTick, PoseStack poseStack, MultiBufferSource buffer, int packedLight, int packedOverlay) {
        ResourceLocation modelId = choppingBoard.getModelId();
        // Empty boards migrated from older saves can contain the explicit
        // minecraft:air sentinel instead of a missing ModelId. No standalone
        // chopping-board model is registered for that sentinel, so rendering
        // it would pass null to ItemRenderer and crash the client.
        if (modelId == null || (EMPTY_MODEL_ID.equals(modelId) && choppingBoard.isProvablyEmptyBoard())) {
            return;
        }
        if (choppingBoard.previousModel == null || !modelId.equals(choppingBoard.previousModel.id())) {
            choppingBoard.previousModel = ModelResourceLocation.standalone(modelId);
            int maxCutCount = Math.max(0, choppingBoard.getMaxCutCount());
            choppingBoard.cacheModels = new ModelResourceLocation[maxCutCount + 1];
            for (int i = 0; i <= maxCutCount; i++) {
                ResourceLocation location = ResourceLocation.fromNamespaceAndPath(modelId.getNamespace(), "chopping_board/" + modelId.getPath() + "/" + i);
                choppingBoard.cacheModels[i] = ModelResourceLocation.standalone(location);
            }
        }
        if (choppingBoard.cacheModels == null) {
            return;
        }
        int index = Math.max(0, Math.min(choppingBoard.getCurrentCutCount(), choppingBoard.cacheModels.length - 1));
        ModelResourceLocation cacheModel = choppingBoard.cacheModels[index];

        ModelManager modelManager = itemRenderer.getItemModelShaper().getModelManager();
        BakedModel model = modelManager.getModel(cacheModel);
        if (model == null) {
            model = modelManager.getMissingModel();
        }
        if (model == null) {
            return;
        }

        poseStack.pushPose();
        int rotation = choppingBoard.getBlockState().getValue(ChoppingBoardBlock.FACING).get2DDataValue();
        poseStack.translate(0.5D, 0, 0.5D);
        poseStack.mulPose(Axis.YP.rotationDegrees(rotation * 90));
        poseStack.translate(-0.5D, 0.125, -0.5D);
        RenderType renderType = Sheets.cutoutBlockSheet();
        VertexConsumer vertexConsumer = ItemRenderer.getFoilBufferDirect(buffer, renderType, true, false);
        itemRenderer.renderModelLists(model, ItemStack.EMPTY, packedLight, packedOverlay, poseStack, vertexConsumer);
        poseStack.popPose();
    }
}
