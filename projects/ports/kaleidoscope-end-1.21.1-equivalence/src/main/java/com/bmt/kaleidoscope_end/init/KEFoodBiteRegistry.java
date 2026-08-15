package com.bmt.kaleidoscope_end.init;

import com.bmt.kaleidoscope_end.KaleidoscopeEnd;
import com.github.ysbbbbbb.kaleidoscopecookery.init.registry.FoodBiteRegistry;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.block.Block;

public class KEFoodBiteRegistry {
    public static ResourceLocation END_SALAD;
    public static ResourceLocation DARK_DRAGON_STEAK;
    public static ResourceLocation OPTIC_NERVE_SWEET_AND_SOUR_PORK;
    public static ResourceLocation VOID_MUTTON_STEAK;
    public static ResourceLocation DRAGON_HEAD_WITH_SAUCE;
    public static ResourceLocation END_CATERPILLAR_SASHIMI;
    public static ResourceLocation DARK_DRAGON_EGG_STEW;
    public static ResourceLocation DRAGON_EGG_CUSTARD;
    public static ResourceLocation DRAGON_EGG_ICE_CREAM;

    public static void init() {
        FoodBiteRegistry registry = new FoodBiteRegistry();
        END_SALAD = registry.registerFoodData(KaleidoscopeEnd.id("end_salad"),
                FoodBiteRegistry.FoodData.create(3, KEFoods.END_SALAD_BLOCK, KEFoods.END_SALAD_ITEM));
        DARK_DRAGON_STEAK = registry.registerFoodData(KaleidoscopeEnd.id("dark_dragon_steak"),
                FoodBiteRegistry.FoodData.create(4, KEFoods.DARK_DRAGON_STEAK_BLOCK, KEFoods.DARK_DRAGON_STEAK_ITEM));
        OPTIC_NERVE_SWEET_AND_SOUR_PORK = registry.registerFoodData(KaleidoscopeEnd.id("optic_nerve_sweet_and_sour_pork"),
                FoodBiteRegistry.FoodData.create(3, KEFoods.OPTIC_NERVE_SWEET_AND_SOUR_PORK_BLOCK,
                        KEFoods.OPTIC_NERVE_SWEET_AND_SOUR_PORK_ITEM));
        VOID_MUTTON_STEAK = registry.registerFoodData(KaleidoscopeEnd.id("void_mutton_steak"),
                FoodBiteRegistry.FoodData.create(3, KEFoods.VOID_MUTTON_STEAK_BLOCK, KEFoods.VOID_MUTTON_STEAK_ITEM));
        DRAGON_HEAD_WITH_SAUCE = registry.registerFoodData(KaleidoscopeEnd.id("dragon_head_with_sauce"),
                FoodBiteRegistry.FoodData.createOneByTwo(7, KEFoods.DRAGON_HEAD_WITH_SAUCE_BLOCK,
                        KEFoods.DRAGON_HEAD_WITH_SAUCE_ITEM));
        END_CATERPILLAR_SASHIMI = registry.registerFoodData(KaleidoscopeEnd.id("end_caterpillar_sashimi"),
                FoodBiteRegistry.FoodData.create(3, KEFoods.END_CATERPILLAR_SASHIMI_BLOCK,
                        KEFoods.END_CATERPILLAR_SASHIMI_ITEM));
        DARK_DRAGON_EGG_STEW = registry.registerFoodData(KaleidoscopeEnd.id("dark_dragon_egg_stew"),
                FoodBiteRegistry.FoodData.create(4, KEFoods.DARK_DRAGON_EGG_STEW_BLOCK,
                                KEFoods.DARK_DRAGON_EGG_STEW_ITEM)
                        .setLootItem(() -> KEItem.DRAGON_EGG_SHELL.get())
                        .setAABB(Block.box(1.0, 0.0, 1.0, 15.0, 11.0, 15.0)));
        DRAGON_EGG_CUSTARD = registry.registerFoodData(KaleidoscopeEnd.id("dragon_egg_custard"),
                FoodBiteRegistry.FoodData.create(4, KEFoods.DRAGON_EGG_CUSTARD_BLOCK,
                                KEFoods.DRAGON_EGG_CUSTARD_ITEM)
                        .setLootItem(() -> KEItem.DRAGON_EGG_SHELL.get())
                        .setAABB(Block.box(1.0, 0.0, 1.0, 15.0, 11.0, 15.0)));
        DRAGON_EGG_ICE_CREAM = registry.registerFoodData(KaleidoscopeEnd.id("dragon_egg_ice_cream"),
                FoodBiteRegistry.FoodData.create(3, KEFoods.DRAGON_EGG_ICE_CREAM_BLOCK,
                                KEFoods.DRAGON_EGG_ICE_CREAM_ITEM)
                        .setLootItem(() -> KEItem.DRAGON_EGG_SHELL.get())
                        .setAABB(Block.box(1.0, 0.0, 1.0, 15.0, 11.0, 15.0)));
    }
}
