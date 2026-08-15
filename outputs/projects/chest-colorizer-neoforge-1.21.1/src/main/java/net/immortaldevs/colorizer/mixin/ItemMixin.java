package net.immortaldevs.colorizer.mixin;

import net.immortaldevs.colorizer.ColorManager;
import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.item.DyeItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.context.UseOnContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.BarrelBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.ChestBlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(Item.class)
abstract class ItemMixin {
    @Inject(method = "useOn", at = @At("HEAD"))
    private void colorizer$useOn(UseOnContext context, CallbackInfoReturnable<InteractionResult> callback) {
        Level level = context.getLevel();
        if (!level.isClientSide) {
            return;
        }

        Item item = (Item) (Object) this;
        BlockPos position = context.getClickedPos();
        BlockEntity blockEntity = level.getBlockEntity(position);
        if (blockEntity instanceof ChestBlockEntity) {
            if (item instanceof DyeItem dyeItem) {
                ColorManager.updateColor(position, dyeItem);
            } else if (item == Items.PAPER) {
                ColorManager.clearChestColor(position, blockEntity.getBlockState());
            }
            return;
        }

        BlockState state = level.getBlockState(position);
        if (state.getBlock() instanceof BarrelBlock) {
            if (item instanceof DyeItem dyeItem) {
                ColorManager.updateColor(position, dyeItem);
            } else if (item == Items.PAPER) {
                ColorManager.clearColor(position);
            }
        }
    }
}
