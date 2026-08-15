package dev.migration.deferred_content_protection.mixin;

import dev.migration.deferred_content_protection.DeferredContentProtection;
import java.util.List;
import java.util.Optional;
import javax.annotation.Nullable;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.crafting.Recipe;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.item.crafting.RecipeInput;
import net.minecraft.world.item.crafting.RecipeManager;
import net.minecraft.world.item.crafting.RecipeType;
import net.minecraft.world.level.Level;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(RecipeManager.class)
public abstract class RecipeManagerMixin {
    @Inject(
            method = "getRecipeFor(Lnet/minecraft/world/item/crafting/RecipeType;Lnet/minecraft/world/item/crafting/RecipeInput;Lnet/minecraft/world/level/Level;Lnet/minecraft/resources/ResourceLocation;)Ljava/util/Optional;",
            at = @At("HEAD"),
            cancellable = true
    )
    private <I extends RecipeInput, T extends Recipe<I>> void deferredContentProtection$blockRecipeLookup(
            RecipeType<T> recipeType,
            I input,
            Level level,
            @Nullable ResourceLocation preferredRecipe,
            CallbackInfoReturnable<Optional<RecipeHolder<T>>> callback
    ) {
        if (containsProtectedCarrier(input)) {
            callback.setReturnValue(Optional.empty());
        }
    }

    @Inject(method = "getRecipesFor", at = @At("HEAD"), cancellable = true)
    private <I extends RecipeInput, T extends Recipe<I>> void deferredContentProtection$blockRecipeList(
            RecipeType<T> recipeType,
            I input,
            Level level,
            CallbackInfoReturnable<List<RecipeHolder<T>>> callback
    ) {
        if (containsProtectedCarrier(input)) {
            callback.setReturnValue(List.of());
        }
    }

    private static boolean containsProtectedCarrier(RecipeInput input) {
        for (int slot = 0; slot < input.size(); slot++) {
            if (DeferredContentProtection.isProtected(input.getItem(slot))) {
                return true;
            }
        }
        return false;
    }
}
