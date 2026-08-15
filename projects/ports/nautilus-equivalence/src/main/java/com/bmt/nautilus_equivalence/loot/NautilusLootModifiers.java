package com.bmt.nautilus_equivalence.loot;

import com.bmt.nautilus_equivalence.NautilusEquivalence;
import com.mojang.serialization.MapCodec;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.common.loot.IGlobalLootModifier;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;
import net.neoforged.neoforge.registries.NeoForgeRegistries;

public final class NautilusLootModifiers {
    public static final DeferredRegister<MapCodec<? extends IGlobalLootModifier>> SERIALIZERS =
        DeferredRegister.create(
            NeoForgeRegistries.Keys.GLOBAL_LOOT_MODIFIER_SERIALIZERS,
            NautilusEquivalence.MOD_ID
        );

    public static final DeferredHolder<
        MapCodec<? extends IGlobalLootModifier>,
        MapCodec<NautilusArmorLootModifier>
    > ADD_NAUTILUS_ARMOR = SERIALIZERS.register(
        "add_nautilus_armor",
        () -> NautilusArmorLootModifier.CODEC
    );

    private NautilusLootModifiers() {
    }

    public static void register(IEventBus modBus) {
        SERIALIZERS.register(modBus);
    }
}
