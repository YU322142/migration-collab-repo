package com.github.ysbbbbbb.kaleidoscopetavern.client.particle;

import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.particle.DripParticle;
import net.minecraft.client.particle.TextureSheetParticle;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.core.particles.SimpleParticleType;
import net.minecraft.world.level.material.Fluid;
import net.minecraft.world.level.material.Fluids;

public class TapDripParticle extends DripParticle {
    private final ParticleOptions fallingParticle;

    public TapDripParticle(ClientLevel pLevel, double pX, double pY, double pZ, Fluid pType, ParticleOptions fallingParticle) {
        super(pLevel, pX, pY, pZ, pType);
        this.fallingParticle = fallingParticle;
        this.gravity *= 0.02F;
        this.lifetime = 18;
    }

    public static TextureSheetParticle createWaterTapDripParticle(
            SimpleParticleType pType, ClientLevel level,
            double pX, double pY, double pZ,
            double pXSpeed, double pYSpeed, double pZSpeed
    ) {
        DripParticle dripparticle = new TapDripParticle(level, pX, pY, pZ, Fluids.WATER, ParticleTypes.FALLING_DRIPSTONE_WATER);
        dripparticle.setColor(0.2F, 0.3F, 1.0F);
        return dripparticle;
    }

    public static TextureSheetParticle createLavaTapDripParticle(
            SimpleParticleType type, ClientLevel level,
            double pX, double pY, double pZ,
            double pXSpeed, double pYSpeed, double pZSpeed
    ) {
        return new TapDripParticle(level, pX, pY, pZ, Fluids.LAVA, ParticleTypes.FALLING_DRIPSTONE_LAVA);
    }

    @Override
    protected void preMoveUpdate() {
        super.preMoveUpdate();
        this.level.addParticle(this.fallingParticle, this.x, this.y, this.z, this.xd, this.yd, this.zd);
    }

    @Override
    protected void postMoveUpdate() {
        this.xd *= 0.02;
        this.yd *= 0.02;
        this.zd *= 0.02;
    }
}
