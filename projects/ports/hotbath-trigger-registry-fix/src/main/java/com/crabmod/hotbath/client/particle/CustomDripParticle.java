package com.crabmod.hotbath.client.particle;

import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.particle.DripParticle;
import net.minecraft.client.particle.Particle;
import net.minecraft.client.particle.ParticleProvider;
import net.minecraft.client.particle.SpriteSet;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.core.particles.SimpleParticleType;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.util.Mth;
import net.minecraft.world.level.material.Fluid;
import net.minecraft.world.level.material.Fluids;

public class CustomDripParticle extends DripParticle {
    private final ParticleOptions fallParticle;
    private final ParticleOptions landParticle;
    private final Fluid fluid;

    protected CustomDripParticle(ClientLevel level, double x, double y, double z, Fluid fluid, ParticleOptions fallParticle, ParticleOptions landParticle) {
        super(level, x, y, z, fluid);
        this.fluid = fluid;
        this.fallParticle = fallParticle;
        this.landParticle = landParticle;
        // Force white color (no tint)
        this.rCol = 1.0F;
        this.gCol = 1.0F;
        this.bCol = 1.0F;
    }

    @Override
    public void setColor(float r, float g, float b) {
        // Override to prevent biome tinting or external color changes
        // We want to keep the original texture color (1.0, 1.0, 1.0)
        super.setColor(1.0F, 1.0F, 1.0F);
    }

    @Override
    public void tick() {
        this.xo = this.x;
        this.yo = this.y;
        this.zo = this.z;
        if (this.age++ >= this.lifetime) {
            this.remove();
        } else {
            if (this.onGround) {
                this.remove();
                if (this.landParticle != null) {
                    this.level.addParticle(this.landParticle, this.x, this.y, this.z, 0.0D, 0.0D, 0.0D);
                }
                // Play sound
                if (this.fluid == Fluids.LAVA) {
                    this.level.playLocalSound(this.x, this.y, this.z, SoundEvents.POINTED_DRIPSTONE_DRIP_LAVA_INTO_CAULDRON, SoundSource.BLOCKS, 0.3F, 1.0F, false);
                } else {
                    this.level.playLocalSound(this.x, this.y, this.z, SoundEvents.POINTED_DRIPSTONE_DRIP_WATER_INTO_CAULDRON, SoundSource.BLOCKS, 0.3F, 1.0F, false);
                }
            }

            // Physics logic copied/adapted from DripParticle
            if (this.lifetime - this.age <= 20 && this.fallParticle != null) {
                // Transition from Hanging to Falling
                if (!this.removed) {
                    this.remove();
                    this.level.addParticle(this.fallParticle, this.x, this.y, this.z, this.xd, this.yd, this.zd);
                }
            }
            
            // Basic movement
            if (this.fallParticle != null) {
                this.xd *= 0.0D;
                this.yd *= 0.0D;
                this.zd *= 0.0D;
            } else {
                this.yd -= (double)this.gravity;
                this.move(this.xd, this.yd, this.zd);
                this.xd *= (double)0.98F;
                this.yd *= (double)0.98F;
                this.zd *= (double)0.98F;
            }
        }
    }

    public static class Factory implements ParticleProvider<SimpleParticleType> {
        private final SpriteSet sprite;
        private final Fluid fluid;
        private final ParticleOptions fallOption;
        private final ParticleOptions landOption;

        public Factory(SpriteSet sprite, Fluid fluid, ParticleOptions fallOption, ParticleOptions landOption) {
            this.sprite = sprite;
            this.fluid = fluid;
            this.fallOption = fallOption;
            this.landOption = landOption;
        }

        public Particle createParticle(SimpleParticleType type, ClientLevel level, double x, double y, double z, double xSpeed, double ySpeed, double zSpeed) {
            CustomDripParticle particle = new CustomDripParticle(level, x, y, z, this.fluid, this.fallOption, this.landOption);
            particle.pickSprite(this.sprite);
            
            // Adjust gravity/size based on type (simplified)
            if (this.fallOption != null) { // Hanging
                particle.gravity = 0.0F; // Hangs
                particle.setLifetime(40 + level.random.nextInt(40)); // Hang time
            } else if (this.landOption != null) { // Falling
                particle.gravity = 0.06F;
                particle.setLifetime((int)(64.0D / (Math.random() * 0.8D + 0.2D)));
            } else { // Landing
                particle.gravity = 0.0F;
                particle.setLifetime((int)(16.0D / (Math.random() * 0.8D + 0.2D)));
            }
            
            return particle;
        }
    }
}
