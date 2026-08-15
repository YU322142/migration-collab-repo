package com.crabmod.hotbath.client.particle;

import com.crabmod.hotbath.fluid_blocks.AbstractHotbathBlock;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.particle.Particle;
import net.minecraft.client.particle.ParticleProvider;
import net.minecraft.client.particle.ParticleRenderType;
import net.minecraft.client.particle.SpriteSet;
import net.minecraft.client.particle.TextureSheetParticle;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.SimpleParticleType;
import net.minecraft.tags.FluidTags;

public class HotBathBubbleParticle extends TextureSheetParticle {
    HotBathBubbleParticle(ClientLevel level, double x, double y, double z, double xSpeed, double ySpeed, double zSpeed) {
        super(level, x, y, z);
        this.setSize(0.02F, 0.02F);
        this.quadSize *= this.random.nextFloat() * 0.6F + 0.2F;
        this.xd = xSpeed * (double)0.2F + (Math.random() * 2.0D - 1.0D) * (double)0.02F;
        this.yd = ySpeed * (double)0.2F + (Math.random() * 2.0D - 1.0D) * (double)0.02F;
        this.zd = zSpeed * (double)0.2F + (Math.random() * 2.0D - 1.0D) * (double)0.02F;
        this.lifetime = (int)(8.0D / (Math.random() * 0.8D + 0.2D));
    }

    public void tick() {
        this.xo = this.x;
        this.yo = this.y;
        this.zo = this.z;
        if (this.lifetime-- <= 0) {
            this.remove();
        } else {
            this.yd += 0.002D;
            this.move(this.xd, this.yd, this.zd);
            this.xd *= 0.85F;
            this.yd *= 0.85F;
            this.zd *= 0.85F;
            if (!this.level.getFluidState(BlockPos.containing(this.x, this.y, this.z)).is(FluidTags.WATER) && 
                !(this.level.getBlockState(BlockPos.containing(this.x, this.y, this.z)).getBlock() instanceof AbstractHotbathBlock)) {
                this.remove();
            }
        }
    }

    public ParticleRenderType getRenderType() {
        return ParticleRenderType.PARTICLE_SHEET_OPAQUE;
    }

    public static class Provider implements ParticleProvider<SimpleParticleType> {
        private final SpriteSet sprite;

        public Provider(SpriteSet sprite) {
            this.sprite = sprite;
        }

        public Particle createParticle(SimpleParticleType type, ClientLevel level, double x, double y, double z, double xSpeed, double ySpeed, double zSpeed) {
            HotBathBubbleParticle particle = new HotBathBubbleParticle(level, x, y, z, xSpeed, ySpeed, zSpeed);
            particle.pickSprite(this.sprite);
            return particle;
        }
    }
}
