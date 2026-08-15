package com.crabmod.hotbath.advancements;

import com.mojang.serialization.Codec;
import net.minecraft.advancements.CriterionTrigger;
import net.minecraft.advancements.CriterionTriggerInstance;
import net.minecraft.advancements.critereon.CriterionValidator;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.PlayerAdvancements;
import net.minecraft.server.level.ServerPlayer;
import org.jetbrains.annotations.NotNull;

import java.util.HashMap;
import java.util.Map;

public class AdvancementTrigger implements CriterionTrigger<AdvancementTrigger.Instance> {
    private final Map<PlayerAdvancements, Listener> listeners = new HashMap<>();
    private final ResourceLocation ID;

    public AdvancementTrigger(String modName, String advancementName) {
        this.ID = ResourceLocation.fromNamespaceAndPath(modName, advancementName);
    }

    @Override
    public void addPlayerListener(
            @NotNull PlayerAdvancements playerAdvancements, @NotNull Listener listener) {
        this.listeners.put(playerAdvancements, listener);
    }

    @Override
    public void removePlayerListener(
            @NotNull PlayerAdvancements playerAdvancements, @NotNull Listener listener) {
        this.listeners.remove(playerAdvancements);
    }

    @Override
    public void removePlayerListeners(@NotNull PlayerAdvancements playerAdvancements) {
        this.listeners.remove(playerAdvancements);
    }

    public void trigger(ServerPlayer player) {
        Listener listener = this.listeners.get(player.getAdvancements());
        if (listener != null) {
            listener.run(player.getAdvancements());
        }
    }

    @Override
    public @NotNull Codec<Instance> codec() {
        return Codec.unit(() -> new Instance(this.ID));
    }

    public static class Instance implements CriterionTriggerInstance {
        private final ResourceLocation id;

        public Instance(ResourceLocation id) {
            this.id = id;
        }

        @Override
        public void validate(@NotNull CriterionValidator validator) {
        }
    }
}
