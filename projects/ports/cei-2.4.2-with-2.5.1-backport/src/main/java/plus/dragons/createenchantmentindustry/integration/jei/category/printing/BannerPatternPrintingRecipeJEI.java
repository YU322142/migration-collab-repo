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

package plus.dragons.createenchantmentindustry.integration.jei.category.printing;

import com.mojang.serialization.MapCodec;
import java.util.ArrayList;
import mezz.jei.api.gui.builder.IRecipeSlotBuilder;
import mezz.jei.api.gui.ingredient.IRecipeSlotDrawable;
import mezz.jei.api.neoforge.NeoForgeTypes;
import mezz.jei.api.recipe.IFocusGroup;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.core.RegistryAccess;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.Registries;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.item.DyeColor;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.level.block.entity.BannerPatternLayers;
import net.neoforged.neoforge.fluids.FluidStack;
import plus.dragons.createdragonsplus.util.Pairs;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.common.registry.CEIDataMaps;
import plus.dragons.createenchantmentindustry.util.CEIDyeFluids;
import plus.dragons.createenchantmentindustry.util.CEILang;

public enum BannerPatternPrintingRecipeJEI implements PrintingRecipeJEI {
    INSTANCE;

    public static final Type TYPE = PrintingRecipeJEI
            .register(CEICommon.asResource("banner_pattern"), MapCodec.unit(INSTANCE));

    @Override
    public void setBase(IRecipeSlotBuilder slot) {
        slot.addIngredients(Ingredient.of(ItemTags.BANNERS));
        slot.addRichTooltipCallback((view, tooltip) -> tooltip.add(CEILang
                .translate("recipe.printing.banner_pattern.base")
                .style(ChatFormatting.GRAY)
                .component()));
    }

    @Override
    public void setTemplate(IRecipeSlotBuilder slot) {
        RegistryAccess registryAccess = Minecraft.getInstance().level.registryAccess();
        registryAccess.lookup(Registries.BANNER_PATTERN).get().listElements().forEach(element -> {
            var stack = new ItemStack(Items.WHITE_BANNER);
            ArrayList<BannerPatternLayers.Layer> l = new ArrayList<>();
            l.add(new BannerPatternLayers.Layer(element.getDelegate(), DyeColor.BLACK));
            stack.set(DataComponents.BANNER_PATTERNS, new BannerPatternLayers(l));
            slot.addItemStack(stack);
        });
        slot.addRichTooltipCallback((view, tooltip) -> tooltip.add(CEILang
                .translate("recipe.printing.banner_pattern.template")
                .style(ChatFormatting.GRAY)
                .component()));
    }

    @Override
    public void setFluid(IRecipeSlotBuilder slot) {
        CEIDataMaps.getSourceFluidEntries(CEIDataMaps.PRINTING_BANNER_PATTERN_INGREDIENT)
                .filter(Pairs.filterFirst(fluid -> CEIDyeFluids.color(fluid).isPresent()))
                .forEach(Pairs.accept(slot::addFluidStack));
    }

    @Override
    public void setOutput(IRecipeSlotBuilder slot) {
        slot.addItemLike(Items.WHITE_BANNER);
        slot.addRichTooltipCallback((view, tooltip) -> tooltip.add(CEILang
                .translate("recipe.printing.banner_pattern.color_follow_dye")
                .style(ChatFormatting.GRAY)
                .component()));
    }

    @Override
    public Type getType() {
        return TYPE;
    }

    @Override
    public void onDisplayedIngredientsUpdate(IRecipeSlotDrawable baseSlot, IRecipeSlotDrawable templateSlot, IRecipeSlotDrawable fluidSlot, IRecipeSlotDrawable outputSlot, IFocusGroup focuses) {
        var fluid = fluidSlot.getDisplayedIngredient(NeoForgeTypes.FLUID_STACK).orElse(new FluidStack(CEIDyeFluids.get(DyeColor.BLACK), 100)); // Fallback
        var base = baseSlot.getDisplayedItemStack();
        var template = templateSlot.getDisplayedItemStack();
        var output = base.get().copy();
        ArrayList<BannerPatternLayers.Layer> l = new ArrayList<>();
        var pattern = template.get().get(DataComponents.BANNER_PATTERNS);
        var color = CEIDyeFluids.color(fluid);
        if (color.isEmpty())
            return;
        l.add(new BannerPatternLayers.Layer(pattern.layers().getFirst().pattern(), color.get()));
        output.set(DataComponents.BANNER_PATTERNS, new BannerPatternLayers(l));
        outputSlot.createDisplayOverrides().addItemStack(output);
    }
}
