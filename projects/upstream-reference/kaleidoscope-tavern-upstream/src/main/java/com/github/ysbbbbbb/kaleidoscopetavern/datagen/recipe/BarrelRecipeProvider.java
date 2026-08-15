package com.github.ysbbbbbb.kaleidoscopetavern.datagen.recipe;

import com.github.ysbbbbbb.kaleidoscopetavern.datagen.builder.BarrelBuilder;
import com.github.ysbbbbbb.kaleidoscopetavern.init.ModFluids;
import com.github.ysbbbbbb.kaleidoscopetavern.init.ModItems;
import net.minecraft.data.PackOutput;
import net.minecraft.data.recipes.FinishedRecipe;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.material.Fluids;

import java.util.function.Consumer;

public class BarrelRecipeProvider extends ModRecipeProvider {
    public BarrelRecipeProvider(PackOutput output) {
        super(output);
    }

    @Override
    public void buildRecipes(Consumer<FinishedRecipe> consumer) {
        // 葡萄酒
        BarrelBuilder.builder()
                .setFluid(ModFluids.GRAPE_JUICE.get())
                .setResult(ModItems.WINE.get())
                .save(consumer);

        // 香槟
        BarrelBuilder.builder()
                .setFluid(ModFluids.GRAPE_JUICE.get())
                .addIngredient(Items.SUGAR)
                .setResult(ModItems.CHAMPAGNE.get())
                .save(consumer);

        // 樱花葡萄酒
        BarrelBuilder.builder()
                .setFluid(ModFluids.GRAPE_JUICE.get())
                .addIngredient(Items.PINK_PETALS)
                .setResult(ModItems.SAKURA_WINE.get())
                .save(consumer);

        // 白兰地
        BarrelBuilder.builder()
                .setFluid(ModFluids.GRAPE_JUICE.get())
                .addIngredient(Items.APPLE)
                .setResult(ModItems.BRANDY.get())
                .save(consumer);

        // 佳丽酿
        BarrelBuilder.builder()
                .setFluid(ModFluids.GRAPE_JUICE.get())
                .addIngredient(Items.SWEET_BERRIES)
                .setResult(ModItems.CARIGNAN.get())
                .save(consumer);

        // 冰葡萄酒
        BarrelBuilder.builder()
                .setFluid(ModFluids.ICE_GRAPE_JUICE.get())
                .setResult(ModItems.ICE_WINE.get())
                .save(consumer);

        // 北极星甜白
        BarrelBuilder.builder()
                .setFluid(ModFluids.ICE_GRAPE_JUICE.get())
                .addIngredient(Items.PACKED_ICE)
                .setResult(ModItems.POLARIS_SWEET_WHITE.get())
                .save(consumer);

        // 雪婆婆
        BarrelBuilder.builder()
                .setFluid(ModFluids.ICE_GRAPE_JUICE.get())
                .addIngredient(Items.ICE)
                .setResult(ModItems.MOTHER_SNOW.get())
                .save(consumer);

        // 雪莉
        BarrelBuilder.builder()
                .setFluid(ModFluids.ICE_GRAPE_JUICE.get())
                .addIngredient(Items.BLUE_ICE)
                .setResult(ModItems.SHERRY.get())
                .save(consumer);

        // 矿工之星
        BarrelBuilder.builder()
                .setFluid(ModFluids.GOLD_GRAPE_JUICE.get())
                .addIngredient(Items.IRON_NUGGET)
                .setResult(ModItems.MINERS_STAR.get())
                .save(consumer);

        // 蜂蜜葡萄酒
        BarrelBuilder.builder()
                .setFluid(ModFluids.GOLD_GRAPE_JUICE.get())
                .addIngredient(Items.HONEYCOMB)
                .setResult(ModItems.HONEY_WINE.get())
                .save(consumer);

        // 奢香夫人
        BarrelBuilder.builder()
                .setFluid(ModFluids.GOLD_GRAPE_JUICE.get())
                .addIngredient(Items.GOLD_NUGGET)
                .setResult(ModItems.MADAME_SHEXIANG.get())
                .save(consumer);

        // 落日余晖
        BarrelBuilder.builder()
                .setFluid(ModFluids.GOLD_GRAPE_JUICE.get())
                .addIngredient(Items.BLAZE_POWDER)
                .setResult(ModItems.SUNSET_GLOW.get())
                .save(consumer);

        // 长相思干白
        BarrelBuilder.builder()
                .setFluid(ModFluids.GREEN_GRAPE_JUICE.get())
                .addIngredient(Items.SUGAR_CANE)
                .addIngredient(Items.SUGAR)
                .setResult(ModItems.SAUVIGNON_BLANC_DRY_WHITE.get())
                .save(consumer);

        // 雷司令干白
        BarrelBuilder.builder()
                .setFluid(ModFluids.GREEN_GRAPE_JUICE.get())
                .addIngredient(Items.GUNPOWDER)
                .addIngredient(Items.SUGAR)
                .setResult(ModItems.RIESLING_DRY_WHITE.get())
                .save(consumer);

        // 夜光新娘
        BarrelBuilder.builder()
                .setFluid(ModFluids.GLOW_BERRIES_JUICE.get())
                .addIngredient(Items.GLOW_INK_SAC)
                .setResult(ModItems.LUMINOUS_BRIDE.get())
                .save(consumer);

        // 萤花酿
        BarrelBuilder.builder()
                .setFluid(ModFluids.GLOW_BERRIES_JUICE.get())
                .addIngredient(Items.GLOWSTONE_DUST)
                .setResult(ModItems.GLOWFLOWER_BREW.get())
                .save(consumer);

        // 梅酒
        BarrelBuilder.builder()
                .setFluid(ModFluids.SWEET_BERRIES_JUICE.get())
                .addIngredient(Items.SUGAR)
                .setResult(ModItems.PLUM_WINE.get())
                .save(consumer);

        // 甜浆果酒
        BarrelBuilder.builder()
                .setFluid(ModFluids.SWEET_BERRIES_JUICE.get())
                .addIngredient(Items.SWEET_BERRIES)
                .setResult(ModItems.SWEET_BERRY_WINE.get())
                .save(consumer);

        // 红皇后
        BarrelBuilder.builder()
                .setFluid(ModFluids.SWEET_BERRIES_JUICE.get())
                .addIngredient(Items.REDSTONE)
                .setResult(ModItems.RED_QUEEN.get())
                .save(consumer);

        // 伏特加
        BarrelBuilder.builder()
                .setFluid(Fluids.WATER)
                .addIngredient(Items.POTATO)
                .setResult(ModItems.VODKA.get())
                .save(consumer);

        // 威士忌
        BarrelBuilder.builder()
                .setFluid(Fluids.WATER)
                .addIngredient(Items.WHEAT)
                .setResult(ModItems.WHISKEY.get())
                .save(consumer);

        // 朗姆酒
        BarrelBuilder.builder()
                .setFluid(Fluids.WATER)
                .addIngredient(Items.SUGAR_CANE)
                .setResult(ModItems.RUM.get())
                .save(consumer);

        // 燃烧瓶
        BarrelBuilder.builder()
                .setFluid(Fluids.LAVA)
                .setResult(ModItems.MOLOTOV.get())
                .save(consumer);
    }
}
