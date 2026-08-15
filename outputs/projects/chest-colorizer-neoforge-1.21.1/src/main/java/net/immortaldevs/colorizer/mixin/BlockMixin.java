package net.immortaldevs.colorizer.mixin;

import net.immortaldevs.colorizer.ColorManager;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.BarrelBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.ChestBlock;
import net.minecraft.world.level.block.state.BlockState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(Block.class)
abstract class BlockMixin {
    @Inject(method = "playerWillDestroy", at = @At("HEAD"))
    private void colorizer$playerWillDestroy(
            Level level,
            BlockPos position,
            BlockState state,
            Player player,
            CallbackInfoReturnable<BlockState> callback
    ) {
        if (!level.isClientSide) {
            return;
        }
        Block block = (Block) (Object) this;
        if (block instanceof ChestBlock) {
            ColorManager.clearChestColor(position, state);
        } else if (block instanceof BarrelBlock) {
            ColorManager.clearColor(position);
        }
    }
}
