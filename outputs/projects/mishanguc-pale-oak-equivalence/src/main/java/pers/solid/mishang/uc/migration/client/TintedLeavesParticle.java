package pers.solid.mishang.uc.migration.client;

import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.particle.CherryParticle;
import net.minecraft.client.particle.Particle;
import net.minecraft.client.particle.ParticleProvider;
import net.minecraft.client.particle.SpriteSet;
import net.minecraft.core.particles.ColorParticleOption;

public final class TintedLeavesParticle extends CherryParticle {
    private TintedLeavesParticle(
            ClientLevel level, double x, double y, double z,
            SpriteSet sprites, ColorParticleOption color) {
        super(level, x, y, z, sprites);
        setColor(color.getRed(), color.getGreen(), color.getBlue());
    }

    public static final class Provider implements ParticleProvider<ColorParticleOption> {
        private final SpriteSet sprites;

        public Provider(SpriteSet sprites) {
            this.sprites = sprites;
        }

        @Override
        public Particle createParticle(
                ColorParticleOption color, ClientLevel level,
                double x, double y, double z, double xSpeed, double ySpeed, double zSpeed) {
            return new TintedLeavesParticle(level, x, y, z, sprites, color);
        }
    }
}
