/*
 * Copyright (C) 2025  DragonsPlus
 * SPDX-License-Identifier: LGPL-3.0-or-later
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.processing.infuser;

import com.mojang.serialization.MapCodec;
import com.simibubi.create.content.processing.basin.BasinBlockEntity;
import com.simibubi.create.content.processing.recipe.ProcessingRecipe;
import com.simibubi.create.content.processing.recipe.ProcessingRecipeBuilder;
import com.simibubi.create.foundation.blockEntity.behaviour.filtering.FilteringBehaviour;
import dev.shadowsoffire.apothic_enchanting.table.infusion.InfusionRecipe;
import dev.shadowsoffire.apothic_enchanting.util.MiscUtil;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.Recipe;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.item.crafting.RecipeSerializer;
import net.minecraft.world.item.crafting.SingleRecipeInput;
import net.minecraft.world.level.Level;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.fluids.FluidStack;
import net.neoforged.neoforge.fluids.capability.IFluidHandler;
import net.neoforged.neoforge.fluids.crafting.SizedFluidIngredient;
import net.neoforged.neoforge.items.IItemHandler;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.registry.CEIAFluids;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.registry.CEIARecipes;

public class InfusingRecipe extends ProcessingRecipe<SingleRecipeInput, InfusingRecipeParams> {
    public InfusingRecipe(InfusingRecipeParams params) {
        super(CEIARecipes.INFUSING, params);
    }

    @Override
    protected int getMaxInputCount() {
        return 1;
    }

    @Override
    protected int getMaxOutputCount() {
        return 1;
    }

    @Override
    protected int getMaxFluidInputCount() {
        return 1;
    }

    @Override
    protected int getMaxFluidOutputCount() {
        return 1;
    }

    public static boolean match(InfuserBlockEntity infuser, BasinBlockEntity basin, Recipe<?> recipe) {
        return process(infuser, basin, recipe, true);
    }

    public static boolean apply(InfuserBlockEntity infuser, BasinBlockEntity basin, Recipe<?> recipe) {
        return process(infuser, basin, recipe, false);
    }

    private static boolean process(InfuserBlockEntity infuser, BasinBlockEntity basin, Recipe<?> recipe, boolean simulateOnly) {
        if (recipe instanceof InfusingRecipe infusingRecipe)
            return processNative(infuser, basin, infusingRecipe, simulateOnly);
        if (recipe instanceof InfusionRecipe infusionRecipe)
            return processApothic(infuser, basin, infusionRecipe, simulateOnly);
        return false;
    }

    private static boolean processNative(InfuserBlockEntity infuser, BasinBlockEntity basin, InfusingRecipe recipe, boolean simulateOnly) {
        if (!recipe.params.stats.qualified(infuser.infusionStats))
            return false;

        var level = infuser.getLevel();
        IItemHandler availableItems = level.getCapability(Capabilities.ItemHandler.BLOCK, basin.getBlockPos(), null);
        IFluidHandler availableFluids = level.getCapability(Capabilities.FluidHandler.BLOCK, basin.getBlockPos(), null);
        IFluidHandler infusingIngredient = level.getCapability(Capabilities.FluidHandler.BLOCK, infuser.getBlockPos(), null);
        if (infusingIngredient == null)
            return false;

        int inputSlot = -1;
        FluidStack fluidInput = FluidStack.EMPTY;
        if (!recipe.ingredients.isEmpty()) {
            if (availableItems == null)
                return false;
            inputSlot = findMatchingItemSlot(availableItems, recipe.ingredients.getFirst());
            if (inputSlot < 0)
                return false;
        } else if (!recipe.fluidIngredients.isEmpty()) {
            if (availableFluids == null)
                return false;
            fluidInput = findMatchingFluid(availableFluids, recipe.fluidIngredients.getFirst());
            if (fluidInput.isEmpty())
                return false;
        } else {
            return false;
        }

        List<ItemStack> outputItems = new ArrayList<>(recipe.rollResults(level.random));
        List<FluidStack> outputFluids = recipe.getFluidResults().stream()
                .filter(stack -> !stack.isEmpty())
                .map(FluidStack::copy)
                .toList();
        if (!matchesFilter(basin.getFilter(), outputItems, outputFluids))
            return false;
        if (!basin.acceptOutputs(outputItems, outputFluids, true))
            return false;

        int requiredAmount = MiscUtil.getExpCostForSlot((int) recipe.params.stats.eterna(), 0);
        FluidStack reagent = findInfusingIngredient(infusingIngredient, requiredAmount);
        if (reagent.isEmpty())
            return false;
        if (simulateOnly)
            return true;

        if (inputSlot >= 0) {
            ItemStack extracted = availableItems.extractItem(inputSlot, 1, false);
            if (!recipe.ingredients.getFirst().test(extracted))
                return false;
        } else {
            FluidStack drained = availableFluids.drain(fluidInput, IFluidHandler.FluidAction.EXECUTE);
            if (!sameFluidAndAmount(fluidInput, drained))
                return false;
        }
        if (!drainInfusingIngredient(infusingIngredient, reagent))
            return false;
        return basin.acceptOutputs(outputItems, outputFluids, false);
    }

    private static boolean processApothic(InfuserBlockEntity infuser, BasinBlockEntity basin, InfusionRecipe recipe, boolean simulateOnly) {
        var level = infuser.getLevel();
        IItemHandler availableItems = level.getCapability(Capabilities.ItemHandler.BLOCK, basin.getBlockPos(), null);
        IFluidHandler infusingIngredient = level.getCapability(Capabilities.FluidHandler.BLOCK, infuser.getBlockPos(), null);
        if (availableItems == null || infusingIngredient == null)
            return false;

        int inputSlot = findMatchingItemSlot(availableItems, recipe, infuser.infusionStats);
        if (inputSlot < 0)
            return false;
        ItemStack input = availableItems.extractItem(inputSlot, 1, true);
        ItemStack output = recipe.assemble(
                input,
                infuser.infusionStats.eterna(),
                infuser.infusionStats.quanta(),
                infuser.infusionStats.arcana());
        if (output.isEmpty() || !matchesFilter(basin.getFilter(), List.of(output), List.of()))
            return false;
        if (!basin.acceptOutputs(List.of(output), List.of(), true))
            return false;

        int requiredAmount = MiscUtil.getExpCostForSlot((int) recipe.getRequirements().eterna(), 0);
        FluidStack reagent = findInfusingIngredient(infusingIngredient, requiredAmount);
        if (reagent.isEmpty())
            return false;
        if (simulateOnly)
            return true;

        ItemStack extracted = availableItems.extractItem(inputSlot, 1, false);
        if (!recipe.matches(
                extracted,
                infuser.infusionStats.eterna(),
                infuser.infusionStats.quanta(),
                infuser.infusionStats.arcana()))
            return false;
        if (!drainInfusingIngredient(infusingIngredient, reagent))
            return false;
        return basin.acceptOutputs(List.of(output), List.of(), false);
    }

    private static int findMatchingItemSlot(IItemHandler items, Ingredient ingredient) {
        for (int slot = 0; slot < items.getSlots(); slot++) {
            if (ingredient.test(items.extractItem(slot, 1, true)))
                return slot;
        }
        return -1;
    }

    private static int findMatchingItemSlot(IItemHandler items, InfusionRecipe recipe, InfusionStats stats) {
        for (int slot = 0; slot < items.getSlots(); slot++) {
            ItemStack input = items.extractItem(slot, 1, true);
            if (recipe.matches(input, stats.eterna(), stats.quanta(), stats.arcana()))
                return slot;
        }
        return -1;
    }

    private static FluidStack findMatchingFluid(IFluidHandler fluids, SizedFluidIngredient ingredient) {
        for (int tank = 0; tank < fluids.getTanks(); tank++) {
            FluidStack available = fluids.getFluidInTank(tank);
            if (available.isEmpty())
                continue;
            FluidStack requested = available.copyWithAmount(ingredient.amount());
            if (!ingredient.test(requested))
                continue;
            FluidStack drained = fluids.drain(requested, IFluidHandler.FluidAction.SIMULATE);
            if (sameFluidAndAmount(requested, drained))
                return requested;
        }
        return FluidStack.EMPTY;
    }

    private static FluidStack findInfusingIngredient(IFluidHandler fluids, int amount) {
        for (int tank = 0; tank < fluids.getTanks(); tank++) {
            FluidStack available = fluids.getFluidInTank(tank);
            if (!available.is(CEIAFluids.MOD_TAGS.infusing_ingredients))
                continue;
            FluidStack requested = available.copyWithAmount(amount);
            FluidStack drained = fluids.drain(requested, IFluidHandler.FluidAction.SIMULATE);
            if (sameFluidAndAmount(requested, drained))
                return requested;
        }
        return FluidStack.EMPTY;
    }

    private static boolean drainInfusingIngredient(IFluidHandler fluids, FluidStack requested) {
        return sameFluidAndAmount(requested, fluids.drain(requested, IFluidHandler.FluidAction.EXECUTE));
    }

    private static boolean sameFluidAndAmount(FluidStack expected, FluidStack actual) {
        return actual.getAmount() == expected.getAmount() && FluidStack.isSameFluidSameComponents(expected, actual);
    }

    private static boolean matchesFilter(FilteringBehaviour filter, List<ItemStack> itemOutputs, List<FluidStack> fluidOutputs) {
        if (filter == null)
            return false;
        if (!itemOutputs.isEmpty())
            return filter.test(itemOutputs.getFirst());
        if (!fluidOutputs.isEmpty())
            return filter.test(fluidOutputs.getFirst());
        return false;
    }

    public static boolean canProcessInput(Recipe<?> recipe, ItemStack stack) {
        if (recipe instanceof InfusionRecipe infusionRecipe)
            return infusionRecipe.getInput().test(stack);
        return !recipe.getIngredients().isEmpty() && recipe.getIngredients().getFirst().test(stack);
    }

    @Override
    public boolean matches(SingleRecipeInput basin, Level level) {
        return false;
    }

    public static class Builder extends ProcessingRecipeBuilder<InfusingRecipeParams, InfusingRecipe, InfusingRecipe.Builder> {
        public Builder(ResourceLocation recipeId, InfusionStats stats) {
            super(InfusingRecipe::new, recipeId);
            this.params.stats = stats;
        }

        @Override
        protected InfusingRecipeParams createParams() {
            return new InfusingRecipeParams();
        }

        @Override
        public InfusingRecipe.Builder self() {
            return this;
        }
    }

    public static class Serializer<R extends InfusingRecipe> implements RecipeSerializer<R> {
        private final MapCodec<R> codec;
        private final StreamCodec<RegistryFriendlyByteBuf, R> streamCodec;

        public Serializer(ProcessingRecipe.Factory<InfusingRecipeParams, R> factory) {
            this.codec = ProcessingRecipe.codec(factory, InfusingRecipeParams.CODEC);
            this.streamCodec = ProcessingRecipe.streamCodec(factory, InfusingRecipeParams.STREAM_CODEC);
        }

        @Override
        public MapCodec<R> codec() {
            return codec;
        }

        @Override
        public StreamCodec<RegistryFriendlyByteBuf, R> streamCodec() {
            return streamCodec;
        }
    }

    public static RecipeHolder<InfusingRecipe> createDisplayRecipe(RecipeHolder<?> recipe) {
        InfusionRecipe infusionRecipe = (InfusionRecipe) recipe.value();
        var requirements = infusionRecipe.getRequirements();
        var stats = new InfusionStats(requirements.eterna(), requirements.quanta(), requirements.arcana());
        InfusingRecipe infusingRecipe = new InfusingRecipe.Builder(recipe.id(), stats).withItemIngredients(infusionRecipe.getInput())
                .withSingleItemOutput(infusionRecipe.getOutput())
                .build();
        return new RecipeHolder<>(recipe.id(), infusingRecipe);
    }
}
