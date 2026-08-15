package com.github.ysbbbbbb.kaleidoscopecookery.init;

import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
import com.github.ysbbbbbb.kaleidoscopecookery.client.particle.StockpotParticleOptions;
import com.mojang.serialization.Codec;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.core.particles.ParticleType;
import net.minecraft.core.particles.SimpleParticleType;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;
import org.jetbrains.annotations.NotNull;

public class ModParticles {
    public static final DeferredRegister<ParticleType<?>> PARTICLES = DeferredRegister.create(ForgeRegistries.PARTICLE_TYPES, KaleidoscopeCookery.MOD_ID);

    public static final RegistryObject<SimpleParticleType> COOKING = PARTICLES.register("cooking_particle", () -> new SimpleParticleType(true));
    public static final RegistryObject<ModParticleType<StockpotParticleOptions>> STOCKPOT = PARTICLES.register("stockpot_particle",
            () -> new ModParticleType<>(false, StockpotParticleOptions.DESERIALIZER, StockpotParticleOptions.CODEC));

    @SuppressWarnings("deprecation")
    public static class ModParticleType<T extends ParticleOptions> extends ParticleType<T> {
        private final Codec<T> codec;

        public ModParticleType(boolean overrideLimiter, ParticleOptions.Deserializer<T> deserializer, Codec<T> codec) {
            super(overrideLimiter, deserializer);
            this.codec = codec;
        }

        @Override
        public @NotNull Codec<T> codec() {
            return this.codec;
        }
    }
}
