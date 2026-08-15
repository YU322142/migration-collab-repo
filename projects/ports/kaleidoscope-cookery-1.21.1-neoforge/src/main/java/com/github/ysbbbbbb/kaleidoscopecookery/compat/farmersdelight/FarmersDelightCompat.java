package com.github.ysbbbbbb.kaleidoscopecookery.compat.farmersdelight;

import com.github.ysbbbbbb.kaleidoscopecookery.crafting.recipe.StockpotRecipe;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.level.Level;
import net.neoforged.fml.ModList;
import net.neoforged.neoforge.common.NeoForge;

import java.util.List;

public class FarmersDelightCompat {
    public static final String ID = "farmersdelight";
    public static boolean IS_LOADED = false;

    public static void init() {
        ModList.get().getModContainerById(ID).ifPresent(modContainer -> {
            IS_LOADED = true;
            // 注册事件监听器
            NeoForge.EVENT_BUS.addListener(CookingPotCompat::afterStockpotRecipeMatch);
        });
    }

    public static void getTransformRecipeForJei(Level level, List<RecipeHolder<StockpotRecipe>> recipes) {
        if (IS_LOADED) {
            CookingPotCompat.getTransformRecipeForJei(level, recipes);
        }
    }
}
