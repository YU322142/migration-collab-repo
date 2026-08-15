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

package plus.dragons.createenchantmentindustry.integration.apotheosis.data;

import static com.simibubi.create.AllBlocks.*;
import static com.simibubi.create.AllItems.*;
import static net.minecraft.world.item.Items.AMETHYST_SHARD;
import static net.minecraft.world.item.Items.NETHER_STAR;
import static net.minecraft.world.item.Items.PAPER;
import static plus.dragons.createdragonsplus.common.registry.CDPItems.BLAZE_UPGRADE_SMITHING_TEMPLATE;
import static plus.dragons.createdragonsplus.data.recipe.VanillaRecipeBuilders.shaped;
import static plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXBlocks.AFFIX_AUGMENTOR;
import static plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXBlocks.BLAZE_COMPOSER;
import static plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXBlocks.GEM_CUTTER;
import static plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXItems.APOTHEOTIC_AFFIX_TEMPLATE;
import static plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXItems.BRASS_AFFIX_TEMPLATE;
import static plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXItems.CRYSTAL_AFFIX_TEMPLATE;
import static plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXItems.INCOMPLETE_APOTHEOTIC_AFFIX_TEMPLATE;
import static plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXItems.INCOMPLETE_BRASS_AFFIX_TEMPLATE;
import static plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXItems.INCOMPLETE_CRYSTAL_AFFIX_TEMPLATE;

import com.simibubi.create.content.fluids.transfer.FillingRecipe;
import com.simibubi.create.content.kinetics.deployer.DeployerApplicationRecipe;
import com.simibubi.create.content.kinetics.press.PressingRecipe;
import dev.shadowsoffire.apotheosis.Apoth;
import java.util.concurrent.CompletableFuture;
import net.minecraft.core.HolderLookup.Provider;
import net.minecraft.data.PackOutput;
import net.minecraft.data.recipes.RecipeCategory;
import net.minecraft.data.recipes.RecipeOutput;
import net.minecraft.data.recipes.RecipeProvider;
import net.minecraft.data.recipes.SmithingTransformRecipeBuilder;
import net.minecraft.world.item.crafting.Ingredient;
import plus.dragons.createdragonsplus.data.recipe.CreateRecipeBuilders;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.integration.ModIntegration;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXFluids;

public class CEIAXRecipeProvider extends RecipeProvider {
    public CEIAXRecipeProvider(PackOutput output, CompletableFuture<Provider> registries) {
        super(output, registries);
    }

    @Override
    protected void buildRecipes(RecipeOutput output) {
        CreateRecipeBuilders.mixing(CEICommon.asResource("dissolve_common_material"))
                .withCondition(ModIntegration.APOTHEOSIS.condition())
                .require(Apoth.Items.COMMON_MATERIAL.value())
                .output(CEIAXFluids.APOTHEOTIC_ESSENCE.get(), 1)
                .duration(5)
                .build(output);

        CreateRecipeBuilders.mixing(CEICommon.asResource("dissolve_uncommon_material"))
                .withCondition(ModIntegration.APOTHEOSIS.condition())
                .require(Apoth.Items.UNCOMMON_MATERIAL.value())
                .output(CEIAXFluids.APOTHEOTIC_ESSENCE.get(), 3)
                .duration(6)
                .build(output);

        CreateRecipeBuilders.mixing(CEICommon.asResource("dissolve_rare_material"))
                .withCondition(ModIntegration.APOTHEOSIS.condition())
                .require(Apoth.Items.RARE_MATERIAL.value())
                .output(CEIAXFluids.APOTHEOTIC_ESSENCE.get(), 9)
                .duration(7)
                .build(output);

        CreateRecipeBuilders.mixing(CEICommon.asResource("dissolve_epic_material"))
                .withCondition(ModIntegration.APOTHEOSIS.condition())
                .require(Apoth.Items.EPIC_MATERIAL.value())
                .output(CEIAXFluids.APOTHEOTIC_ESSENCE.get(), 27)
                .duration(8)
                .build(output);

        CreateRecipeBuilders.mixing(CEICommon.asResource("dissolve_mythic_material"))
                .withCondition(ModIntegration.APOTHEOSIS.condition())
                .require(Apoth.Items.MYTHIC_MATERIAL.value())
                .output(CEIAXFluids.APOTHEOTIC_ESSENCE.get(), 81)
                .duration(8)
                .build(output);

        CreateRecipeBuilders.mixing(CEICommon.asResource("dissolve_gem_dust"))
                .withCondition(ModIntegration.APOTHEOSIS.condition())
                .require(Apoth.Items.GEM_DUST.value())
                .output(CEIAXFluids.CRYSTAL_ESSENCE.get(), 10)
                .duration(8)
                .build(output);

        shaped().define('-', NETHER_STAR)
                .define('=', ORANGE_NIXIE_TUBE)
                .define('o', BRASS_SHEET)
                .define('x', AMETHYST_SHARD)
                .define('S', Apoth.Items.MYTHIC_MATERIAL.value())
                .pattern("oxo")
                .pattern(" - ")
                .pattern("S=S")
                .output(AFFIX_AUGMENTOR)
                .withCondition(ModIntegration.APOTHEOSIS.condition())
                .unlockedBy("nether_star", has(NETHER_STAR))
                .accept(output);

        shaped().define('o', BRASS_INGOT)
                .define('x', AMETHYST_SHARD)
                .define('S', Apoth.Items.GEM_DUST.value())
                .pattern("xxx")
                .pattern("oSo")
                .pattern("xxx")
                .output(GEM_CUTTER)
                .withCondition(ModIntegration.APOTHEOSIS.condition())
                .unlockedBy("amethyst_shard", has(AMETHYST_SHARD))
                .accept(output);

        CreateRecipeBuilders.sequencedAssembly(BRASS_AFFIX_TEMPLATE.getId())
                .require(PAPER)
                .transitionTo(INCOMPLETE_BRASS_AFFIX_TEMPLATE)
                .addOutput(BRASS_AFFIX_TEMPLATE, 1)
                .loops(1)
                .addStep(DeployerApplicationRecipe::new, rb -> rb.require(COPPER_SHEET))
                .addStep(DeployerApplicationRecipe::new, rb -> rb.require(Apoth.Items.COMMON_MATERIAL.value()))
                .addStep(PressingRecipe::new, rb -> rb)
                .build(output.withConditions(ModIntegration.APOTHEOSIS.condition()));

        CreateRecipeBuilders.sequencedAssembly(CRYSTAL_AFFIX_TEMPLATE.getId())
                .require(PAPER)
                .transitionTo(INCOMPLETE_CRYSTAL_AFFIX_TEMPLATE)
                .addOutput(CRYSTAL_AFFIX_TEMPLATE, 1)
                .loops(1)
                .addStep(DeployerApplicationRecipe::new, rb -> rb.require(BRASS_SHEET))
                .addStep(FillingRecipe::new, rb -> rb.require(CEIAXFluids.CRYSTAL_ESSENCE.get(), 50))
                .addStep(DeployerApplicationRecipe::new, rb -> rb.require(AMETHYST_SHARD))
                .addStep(PressingRecipe::new, rb -> rb)
                .build(output.withConditions(ModIntegration.APOTHEOSIS.condition()));

        CreateRecipeBuilders.sequencedAssembly(APOTHEOTIC_AFFIX_TEMPLATE.getId())
                .require(PAPER)
                .transitionTo(INCOMPLETE_APOTHEOTIC_AFFIX_TEMPLATE)
                .addOutput(APOTHEOTIC_AFFIX_TEMPLATE, 1)
                .loops(1)
                .addStep(DeployerApplicationRecipe::new, rb -> rb.require(STURDY_SHEET))
                .addStep(FillingRecipe::new, rb -> rb.require(CEIAXFluids.APOTHEOTIC_ESSENCE.get(), 50))
                .addStep(DeployerApplicationRecipe::new, rb -> rb.require(Apoth.Items.MYTHIC_MATERIAL.value()))
                .addStep(PressingRecipe::new, rb -> rb)
                .build(output.withConditions(ModIntegration.APOTHEOSIS.condition()));

        SmithingTransformRecipeBuilder.smithing(
                Ingredient.of(BLAZE_UPGRADE_SMITHING_TEMPLATE),
                Ingredient.of(BLAZE_BURNER),
                Ingredient.of(AFFIX_AUGMENTOR),
                RecipeCategory.MISC,
                BLAZE_COMPOSER.asItem())
                .unlocks("has_affix_augmentor", has(AFFIX_AUGMENTOR))
                .save(output.withConditions(ModIntegration.APOTHEOSIS.condition()), BLAZE_COMPOSER.getId().withPrefix("smithing/"));
    }

    @Override
    public String getName() {
        return "Create: Enchantment Industry Apotheosis Recipes";
    }
}
