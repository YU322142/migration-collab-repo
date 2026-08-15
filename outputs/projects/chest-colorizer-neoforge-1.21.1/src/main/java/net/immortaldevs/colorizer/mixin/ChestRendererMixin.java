package net.immortaldevs.colorizer.mixin;

import net.immortaldevs.colorizer.ColorManager;
import net.minecraft.client.renderer.blockentity.ChestRenderer;
import net.minecraft.client.resources.model.Material;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.EnderChestBlockEntity;
import net.minecraft.world.level.block.entity.TrappedChestBlockEntity;
import net.minecraft.world.level.block.state.properties.ChestType;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(ChestRenderer.class)
abstract class ChestRendererMixin {
    @Inject(method = "getMaterial", at = @At("HEAD"), cancellable = true)
    private void colorizer$getMaterial(
            BlockEntity blockEntity,
            ChestType chestType,
            CallbackInfoReturnable<Material> callback
    ) {
        if (blockEntity instanceof EnderChestBlockEntity || blockEntity instanceof TrappedChestBlockEntity) {
            return;
        }
        Material material = ColorManager.getColorizedChestMaterial(blockEntity, chestType);
        if (material != null) {
            callback.setReturnValue(material);
        }
    }
}
