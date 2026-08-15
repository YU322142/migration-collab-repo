package com.crabmod.hotbath.item;

import com.crabmod.hotbath.HotBath;
import com.crabmod.hotbath.registers.ItemRegister;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.ItemStack;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public class ItemGroup {
    public static final DeferredRegister<CreativeModeTab> HOT_BATH_TABS =
            DeferredRegister.create(Registries.CREATIVE_MODE_TAB, HotBath.MOD_ID);

    public static final DeferredHolder<CreativeModeTab, CreativeModeTab> HOT_BATH_TAB =
            HOT_BATH_TABS.register(
                    "hotbath_tab",
                    () ->
                            CreativeModeTab.builder()
                                    .icon(() -> new ItemStack(ItemRegister.HOT_WATER_BUCKET.get()))
                                    .title(Component.translatable("itemGroup.hotbath.hotbath_tab"))
                                    .displayItems(
                                            (pParameters, pOutput) -> {
                                                pOutput.accept(ItemRegister.HOT_WATER_BUCKET.get());
                                                pOutput.accept(ItemRegister.HERBAL_BATH_BUCKET.get());
                                                pOutput.accept(ItemRegister.HONEY_BATH_BUCKET.get());
                                                pOutput.accept(ItemRegister.MILK_BATH_BUCKET.get());
                                                pOutput.accept(ItemRegister.PEONY_BATH_BUCKET.get());
                                                pOutput.accept(ItemRegister.ROSE_BATH_BUCKET.get());
                                                pOutput.accept(ItemRegister.HOT_WATER_BOTTLE.get());
                                                pOutput.accept(ItemRegister.HONEY_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.MILK_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.HERBAL_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.PEONY_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.ROSE_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.SPLASH_HOT_WATER_BOTTLE.get());
                                                pOutput.accept(ItemRegister.SPLASH_HONEY_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.SPLASH_MILK_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.SPLASH_HERBAL_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.SPLASH_PEONY_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.SPLASH_ROSE_BATH_BOTTLE.get());
                                                pOutput.accept(ItemRegister.BATH_HERB.get());
                                            })
                                    .build());

    public static void register(IEventBus eventBus) {
        HOT_BATH_TABS.register(eventBus);
    }
}
