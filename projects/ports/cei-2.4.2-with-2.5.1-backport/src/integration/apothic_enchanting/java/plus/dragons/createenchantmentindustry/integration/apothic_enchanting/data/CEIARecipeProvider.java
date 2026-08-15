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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.data;

import static com.simibubi.create.AllBlocks.*;
import static com.simibubi.create.AllItems.*;
import static dev.shadowsoffire.apothic_enchanting.Ench.Items.ENDER_LEAD;
import static plus.dragons.createdragonsplus.data.recipe.VanillaRecipeBuilders.shaped;
import static plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.registry.CEIABlocks.*;
import static plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.registry.CEIAItems.INCOMPLETE_BRASS_BOOKSHELF;

import com.simibubi.create.content.fluids.transfer.FillingRecipe;
import com.simibubi.create.content.kinetics.deployer.DeployerApplicationRecipe;
import dev.shadowsoffire.apothic_enchanting.Ench;
import java.util.concurrent.CompletableFuture;
import net.minecraft.core.HolderLookup.Provider;
import net.minecraft.data.PackOutput;
import net.minecraft.data.recipes.RecipeOutput;
import net.minecraft.data.recipes.RecipeProvider;
import net.neoforged.neoforge.fluids.FluidStack;
import net.neoforged.neoforge.fluids.crafting.SizedFluidIngredient;
import plus.dragons.createdragonsplus.common.registry.CDPFluids;
import plus.dragons.createdragonsplus.data.recipe.CreateRecipeBuilders;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.integration.ModIntegration;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.processing.infuser.InfusingRecipe;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.processing.infuser.InfusionStats;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.registry.CEIAFluids;

public class CEIARecipeProvider extends RecipeProvider {
    private static final String BRASS = "brass";

    public CEIARecipeProvider(PackOutput output, CompletableFuture<Provider> registries) {
        super(output, registries);
    }

    @Override
    protected void buildRecipes(RecipeOutput output) {
        shaped().define('-', BRASS_SHEET)
                .define('o', SPOUT)
                .define('=', ORANGE_NIXIE_TUBE)
                .pattern(" - ")
                .pattern(" o ")
                .pattern("===")
                .output(INFUSER)
                .withCondition(ModIntegration.APOTHIC_ENCHANTING.condition())
                .unlockedBy(BRASS, has(BRASS_INGOT))
                .accept(output);

        shaped().define('-', BRASS_CASING)
                .define('o', ENDER_LEAD.value())
                .define('=', PRECISION_MECHANISM)
                .define('x', ROSE_QUARTZ_LAMP)
                .pattern("oxo")
                .pattern("o=o")
                .pattern("o-o")
                .output(ENDER_WOVEN_BAG)
                .withCondition(ModIntegration.APOTHIC_ENCHANTING.condition())
                .unlockedBy(BRASS, has(BRASS_INGOT))
                .accept(output);

        new InfusingRecipe.Builder(CEICommon.asResource("infused_dragon_breath"), new InfusionStats(80, 15, 60))
                .withCondition(ModIntegration.APOTHIC_ENCHANTING.condition())
                .require(SizedFluidIngredient.of(CDPFluids.DRAGON_BREATH.get().getSource(), 250))
                .output(new FluidStack(CEIAFluids.INFUSED_DRAGON_BREATH, 750))
                .build(output);

        CreateRecipeBuilders.sequencedAssembly(BRASS_BOOKSHELF.getId())
                .require(Ench.Blocks.PEARL_ENDSHELF.value())
                .transitionTo(INCOMPLETE_BRASS_BOOKSHELF)
                .addOutput(BRASS_BOOKSHELF, 1)
                .loops(3)
                .addStep(DeployerApplicationRecipe::new,
                        rb -> rb.require(BRASS_INGOT))
                .addStep(FillingRecipe::new, rb -> rb.require(CEIAFluids.MOD_TAGS.infusing_ingredients, 250))
                .addStep(DeployerApplicationRecipe::new,
                        rb -> rb.require(PRECISION_MECHANISM))
                .build(output.withConditions(ModIntegration.APOTHIC_ENCHANTING.condition()));
    }

    @Override
    public String getName() {
        return "Create: Enchantment Industry Apothic Enchanting Recipes";
    }
}
