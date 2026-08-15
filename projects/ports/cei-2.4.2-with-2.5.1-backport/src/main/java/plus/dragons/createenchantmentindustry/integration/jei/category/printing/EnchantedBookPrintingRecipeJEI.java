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

import com.mojang.serialization.Codec;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import mezz.jei.api.gui.builder.IRecipeSlotBuilder;
import mezz.jei.api.helpers.ICodecHelper;
import mezz.jei.api.recipe.IRecipeManager;
import net.minecraft.client.Minecraft;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.EnchantedBookItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.enchantment.Enchantment;
import net.minecraft.world.item.enchantment.EnchantmentInstance;
import plus.dragons.createdragonsplus.util.Pairs;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.common.processing.enchanter.CEIEnchantmentHelper;
import plus.dragons.createenchantmentindustry.common.registry.CEIDataMaps;
import plus.dragons.createenchantmentindustry.common.registry.CEIEnchantments;
import plus.dragons.createenchantmentindustry.common.registry.CEIFluids;
import plus.dragons.createenchantmentindustry.config.CEIConfig;
import plus.dragons.createenchantmentindustry.util.CEIIntIntPair;

public class EnchantedBookPrintingRecipeJEI implements PrintingRecipeJEI {
    public static final PrintingRecipeJEI.Type TYPE = PrintingRecipeJEI
            .register(CEICommon.asResource("enchanted_book"), EnchantedBookPrintingRecipeJEI::createCodec);
    private final ResourceLocation id;
    private final ResourceKey<Enchantment> enchantmentKey;
    private final int level;

    public EnchantedBookPrintingRecipeJEI(ResourceKey<Enchantment> enchantmentKey, int level) {
        this.id = PrintingRecipeJEI.super.getRegistryName().withSuffix("/" +
                enchantmentKey.location().getNamespace() + "/" +
                enchantmentKey.location().getPath() + "/" +
                level);
        this.enchantmentKey = enchantmentKey;
        this.level = level;
    }

    public static MapCodec<EnchantedBookPrintingRecipeJEI> createCodec(ICodecHelper codecHelper, IRecipeManager recipeManager) {
        return RecordCodecBuilder.mapCodec(instance -> instance.group(
                ResourceLocation.CODEC.fieldOf("enchantment")
                        .forGetter((EnchantedBookPrintingRecipeJEI recipe) -> recipe.enchantmentKey.location()),
                Codec.INT.fieldOf("level")
                        .forGetter(recipe -> recipe.level))
                .apply(instance, (enchantment, level) -> new EnchantedBookPrintingRecipeJEI(ResourceKey.create(Registries.ENCHANTMENT, enchantment), level)));
    }

    public static List<PrintingRecipeJEI> listAll() {
        var minecraft = Minecraft.getInstance();
        if (minecraft.level == null)
            return List.of();
        return minecraft.level.registryAccess()
                .lookupOrThrow(Registries.ENCHANTMENT)
                .listElements()
                .filter(enchantment -> !enchantment.is(CEIEnchantments.MOD_TAGS.printingDeny))
                .flatMap(enchantment -> enchantment.unwrapKey().stream()
                        .flatMap(key -> IntStream
                                .rangeClosed(enchantment.value().getMinLevel(), CEIEnchantmentHelper.maxLevel(enchantment))
                                .mapToObj(level -> new EnchantedBookPrintingRecipeJEI(key, level))))
                .collect(Collectors.toList());
    }

    private Optional<Holder.Reference<Enchantment>> resolveEnchantment() {
        var minecraft = Minecraft.getInstance();
        if (minecraft.level == null)
            return Optional.empty();
        return minecraft.level.registryAccess()
                .lookupOrThrow(Registries.ENCHANTMENT)
                .get(enchantmentKey);
    }

    private Optional<ItemStack> createEnchantmentBook() {
        return resolveEnchantment()
                .map(enchantment -> EnchantedBookItem.createForEnchantment(new EnchantmentInstance(enchantment, level)));
    }

    private OptionalInt getCost() {
        return resolveEnchantment()
                .map(enchantment -> {
                    Optional<CEIIntIntPair> optional = Optional.empty();
                    var customCost = enchantment.getData(CEIDataMaps.PRINTING_ENCHANTED_BOOK_COST);
                    if (customCost != null) {
                        optional = customCost.stream().filter(pair -> pair.level() == level).findFirst();
                    }
                    return (int) (optional.map(CEIIntIntPair::value).orElseGet(() -> CEIEnchantmentHelper.getEnchantmentCost(enchantment, level)) * CEIConfig.fluids().printingEnchantedBookCostMultiplier.get());
                })
                .map(OptionalInt::of)
                .orElseGet(OptionalInt::empty);
    }

    @Override
    public void setBase(IRecipeSlotBuilder slot) {
        slot.addItemLike(Items.BOOK);
    }

    @Override
    public void setTemplate(IRecipeSlotBuilder slot) {
        createEnchantmentBook().ifPresent(slot::addItemStack);
    }

    @Override
    public void setFluid(IRecipeSlotBuilder slot) {
        getCost().ifPresent(cost -> {
            slot.addFluidStack(CEIFluids.EXPERIENCE.get(), cost);
            CEIDataMaps.getSourceFluidEntries(CEIDataMaps.FLUID_UNIT_EXPERIENCE)
                    .forEach(Pairs.accept((fluid, unit) -> slot.addFluidStack(fluid, (long) unit * cost)));
        });
    }

    @Override
    public void setOutput(IRecipeSlotBuilder slot) {
        createEnchantmentBook().ifPresent(slot::addItemStack);
    }

    @Override
    public Type getType() {
        return TYPE;
    }

    @Override
    public ResourceLocation getRegistryName() {
        return id;
    }
}
