package dev.migration.heightmap_384_to_544_compat.mixin;

import dev.migration.heightmap_384_to_544_compat.Heightmap384To544Compat;
import dev.migration.heightmap_384_to_544_compat.HeightmapArrayConverter;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.chunk.ChunkAccess;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

@Mixin(ChunkAccess.class)
public abstract class ChunkAccessMixin {
    @Shadow
    public abstract int getHeight();

    @Shadow
    public abstract ChunkPos getPos();

    @ModifyVariable(method = "setHeightmap", at = @At("HEAD"), argsOnly = true, index = 2)
    private long[] heightmap384To544Compat$repackLegacyArray(long[] input) {
        HeightmapArrayConverter.Conversion conversion = HeightmapArrayConverter.convert(this.getHeight(), input);
        if (conversion.status() == HeightmapArrayConverter.Status.CONVERTED) {
            Heightmap384To544Compat.noteConversion(this.getPos());
        } else if (conversion.status() == HeightmapArrayConverter.Status.REJECTED) {
            Heightmap384To544Compat.warnRejected(this.getPos(), conversion.diagnostic());
        }
        return conversion.data();
    }
}
