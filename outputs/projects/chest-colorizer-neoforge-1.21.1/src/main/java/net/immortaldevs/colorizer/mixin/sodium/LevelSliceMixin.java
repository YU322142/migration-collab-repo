package net.immortaldevs.colorizer.mixin.sodium;

import net.immortaldevs.colorizer.ColorManager;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.state.BlockState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Pseudo
@Mixin(targets = "net.caffeinemc.mods.sodium.client.world.LevelSlice", remap = false)
abstract class LevelSliceMixin {
    @Inject(method = "getBlockState(III)Lnet/minecraft/world/level/block/state/BlockState;", at = @At("RETURN"), cancellable = true, remap = false)
    private void colorizer$modifyBarrelState(int x, int y, int z, CallbackInfoReturnable<BlockState> callback) {
        BlockState state = callback.getReturnValue();
        if (state != null) {
            callback.setReturnValue(ColorManager.getColorizedBarrelState(state, new BlockPos(x, y, z)));
        }
    }
}
