package pers.solid.mishang.uc.migration;

import com.mojang.serialization.MapCodec;
import net.minecraft.core.particles.ColorParticleOption;
import net.minecraft.core.particles.ParticleType;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class MishangPaleOakParticles {
    private static final DeferredRegister<ParticleType<?>> PARTICLE_TYPES =
            DeferredRegister.create(Registries.PARTICLE_TYPE, MishangPaleOakEquivalence.MOD_ID);

    public static final DeferredHolder<ParticleType<?>, ParticleType<ColorParticleOption>> TINTED_LEAVES =
            PARTICLE_TYPES.register("tinted_leaves", () -> new ParticleType<>(false) {
                @Override
                public MapCodec<ColorParticleOption> codec() {
                    return ColorParticleOption.codec(this);
                }

                @Override
                public StreamCodec<? super RegistryFriendlyByteBuf, ColorParticleOption> streamCodec() {
                    return ColorParticleOption.streamCodec(this);
                }
            });

    private MishangPaleOakParticles() {
    }

    public static void register(IEventBus modBus) {
        PARTICLE_TYPES.register(modBus);
    }
}
