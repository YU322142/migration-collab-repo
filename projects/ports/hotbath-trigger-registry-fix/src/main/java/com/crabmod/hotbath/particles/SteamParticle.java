package com.crabmod.hotbath.particles;

import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.particle.Particle;
import net.minecraft.client.particle.ParticleProvider;
import net.minecraft.client.particle.ParticleRenderType;
import net.minecraft.client.particle.SpriteSet;
import net.minecraft.client.particle.TextureSheetParticle;
import net.minecraft.core.particles.SimpleParticleType;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.api.distmarker.OnlyIn;
import org.jetbrains.annotations.NotNull;

@OnlyIn(Dist.CLIENT)
public class SteamParticle extends TextureSheetParticle {

    private SteamParticle(
            ClientLevel world,
            double x,
            double y,
            double z,
            double motionX,
            double motionY,
            double motionZ,
            boolean longLivingEmber) {
        super(world, x, y, z);
        this.quadSize = (this.random.nextFloat() * 0.5F + 0.5F) * 2.0F;
        this.scale(2.5F + random.nextFloat());
        this.setSize(0.25F, 0.25F);
        this.quadSize *= 0.2F;
        if (longLivingEmber) {
            this.lifetime = 90 + this.random.nextInt(10) + 20;
        } else {
            this.lifetime = 80 + this.random.nextInt(10) + 10;
        }

        this.gravity = 0.0002F;
        this.xd =
                motionX
                        + (double)
                        (this.random.nextFloat() / 250.0F * (float) (this.random.nextBoolean() ? 1 : -1));
        this.zd =
                motionZ
                        + (double)
                        (this.random.nextFloat() / 250.0F * (float) (this.random.nextBoolean() ? 1 : -1));
        this.yd = motionY + 0.025 + (double) (this.random.nextFloat() / 250.0F);
    }

    public void tick() {

        this.xo = this.x;
        this.yo = this.y;
        this.zo = this.z;

        if (this.age++ < this.lifetime && this.alpha > 0.02F) {
            this.xd += this.random.nextFloat() / 1000.0F * (float) (this.random.nextBoolean() ? 1 : -1);
            this.zd += this.random.nextFloat() / 1000.0F * (float) (this.random.nextBoolean() ? 1 : -1);
            this.yd -= this.gravity;
            this.move(this.xd, this.yd, this.zd);

            this.alpha -= 0.01F + random.nextFloat() * 0.01F;
        } else {
            this.remove();
        }
    }

    public @NotNull ParticleRenderType getRenderType() {
        return ParticleRenderType.PARTICLE_SHEET_TRANSLUCENT;
    }

    public static class CozySmokeFactory implements ParticleProvider<SimpleParticleType> {
        private final SpriteSet spriteSet;

        public CozySmokeFactory(SpriteSet spriteSet) {
            this.spriteSet = spriteSet;
        }

        public Particle createParticle(
                @NotNull SimpleParticleType typeIn,
                @NotNull ClientLevel worldIn,
                double x,
                double y,
                double z,
                double xSpeed,
                double ySpeed,
                double zSpeed) {
            SteamParticle steamParticle =
                    new SteamParticle(worldIn, x, y, z, xSpeed, ySpeed, zSpeed, false);
            steamParticle.setAlpha(0.9F); // transparency
            steamParticle.pickSprite(this.spriteSet);
            return steamParticle;
        }
    }
}
