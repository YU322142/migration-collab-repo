package com.github.ysbbbbbb.kaleidoscopecookery.init;

import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
import com.google.common.collect.ImmutableSet;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.world.entity.npc.VillagerProfession;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;

@SuppressWarnings("all")
public class ModVillager {
    public static final DeferredRegister<VillagerProfession> VILLAGER_PROFESSION = DeferredRegister.create(ForgeRegistries.VILLAGER_PROFESSIONS, KaleidoscopeCookery.MOD_ID);

    public static final RegistryObject<VillagerProfession> CHEF = VILLAGER_PROFESSION.register("chef", () -> new VillagerProfession("chef",
            poi -> poi.get() == ModPoi.STOVE.get(),
            poi -> poi.get() == ModPoi.STOVE.get(),
            ImmutableSet.of(), ImmutableSet.of(), SoundEvents.VILLAGER_WORK_BUTCHER));
}
