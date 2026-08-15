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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.template;

import dev.shadowsoffire.apotheosis.affix.AttributeProvidingAffix;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.contents.PlainTextContents;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.neoforged.neoforge.common.util.AttributeTooltipContext;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXDataComponents;

public class AffixTemplateItem extends Item {
    private final AffixTemplateTier tier;

    public AffixTemplateItem(Properties properties, AffixTemplateTier tier) {
        super(properties);
        this.tier = tier;
    }

    public static AffixTemplateItem brass(Properties properties) {
        return new AffixTemplateItem(properties, AffixTemplateTier.BRASS);
    }

    public static AffixTemplateItem crystal(Properties properties) {
        return new AffixTemplateItem(properties, AffixTemplateTier.CRYSTAL);
    }

    public static AffixTemplateItem apotheotic(Properties properties) {
        return new AffixTemplateItem(properties, AffixTemplateTier.APOTHEOTIC);
    }

    public AffixTemplateTier tier() {
        return tier;
    }

    @Override
    public boolean isFoil(ItemStack stack) {
        return stack.has(CEIAXDataComponents.AFFIX_TEMPLATE.get());
    }

    @Override
    public boolean isEnchantable(ItemStack stack) {
        return false;
    }

    @Override
    public void appendHoverText(ItemStack stack, TooltipContext context, List<Component> tooltip, TooltipFlag flag) {
        var data = stack.get(CEIAXDataComponents.AFFIX_TEMPLATE.get());
        if (data == null) {
            tooltip.add(Component.translatable("tooltip.create_enchantment_industry.affix_template.blank")
                    .withStyle(ChatFormatting.GRAY));
            tooltip.add(Component.translatable("tooltip.create_enchantment_industry.affix_template.level_capacity", AffixTemplateDisplay.formatLevel(tier.getMaxLevel()))
                    .withStyle(ChatFormatting.DARK_GRAY));
            return;
        }
        if (!data.isBound()) {
            tooltip.add(Component.translatable("tooltip.create_enchantment_industry.affix_template.unbound")
                    .withStyle(ChatFormatting.RED));
            data.entries().stream()
                    .map(entry -> entry.affix().getId().toString())
                    .map(id -> Component.literal(id).withStyle(ChatFormatting.DARK_GRAY))
                    .forEach(tooltip::add);
            return;
        }
        var rarity = data.rarity().get();
        tooltip.add(Component.translatable("tooltip.create_enchantment_industry.affix_template.rarity", data.rarity().get().toComponent()
                .withStyle(style -> style.withColor(rarity.color())))
                .withStyle(ChatFormatting.GRAY));
        tooltip.add(Component.translatable("tooltip.create_enchantment_industry.affix_template.affixes", data.size())
                .withStyle(ChatFormatting.GRAY));
        tooltip.add(Component.translatable("tooltip.create_enchantment_industry.affix_template.level_capacity", AffixTemplateDisplay.formatLevel(tier.getMaxLevel()))
                .withStyle(ChatFormatting.DARK_GRAY));
        for (AffixTemplateEntry entry : data.entries()) {
            addEntryTooltip(stack, context, tooltip, flag, data, entry);
        }
        if (flag.isAdvanced()) {
            data.entries().stream()
                    .map(entry -> Component.literal(entry.affix().getId().toString()).withStyle(ChatFormatting.DARK_GRAY))
                    .forEach(tooltip::add);
        }
    }

    private void addEntryTooltip(ItemStack stack, TooltipContext context, List<Component> tooltip, TooltipFlag flag, AffixTemplateData data, AffixTemplateEntry entry) {
        var e = Component.translatable(
                "tooltip.create_enchantment_industry.affix_template.affix",
                AffixTemplateDisplay.affixName(entry, data.rarity(), stack),
                AffixTemplateDisplay.formatLevel(entry.level()))
                .withStyle(entry.level() > tier.getMaxLevel() ? ChatFormatting.RED : entry.transcendent() ? ChatFormatting.LIGHT_PURPLE : ChatFormatting.GRAY);
        if (entry.transcendent()) {
            e.append(" ").append(Component.translatable("tooltip.create_enchantment_industry.affix_template.transcendent")
                    .withStyle(ChatFormatting.LIGHT_PURPLE));
        }
        tooltip.add(e);
        if (!entry.sourceCategories().isEmpty()) {
            Component categories = Component.literal(entry.sourceCategories().stream()
                    .map(AffixTemplateDisplay::sourceCategoryName)
                    .map(Component::getString)
                    .collect(Collectors.joining(", ")));
            tooltip.add(Component.translatable("tooltip.create_enchantment_industry.affix_template.category", categories)
                    .withStyle(ChatFormatting.DARK_GRAY));
        }
        addAffixEffectTooltip(stack, context, tooltip, flag, data, entry);
    }

    private static void addAffixEffectTooltip(ItemStack stack, TooltipContext context, List<Component> tooltip, TooltipFlag flag, AffixTemplateData data, AffixTemplateEntry entry) {
        var instance = entry.toInstance(data.rarity(), stack);
        var tooltipContext = AttributeTooltipContext.of(null, context, flag);
        List<Component> effects = new ArrayList<>();
        Component description = instance.getDescription(tooltipContext);
        if (description.getContents() != PlainTextContents.EMPTY) {
            effects.add(description);
        }
        if (instance.getAffix() instanceof AttributeProvidingAffix provider) {
            provider.gatherModifierTooltips(instance, tooltipContext, effects::add);
        }
        if (effects.isEmpty()) {
            tooltip.add(Component.translatable("tooltip.create_enchantment_industry.affix_template.effect.unknown")
                    .withStyle(ChatFormatting.GRAY));
            return;
        }
        for (Component effect : effects) {
            tooltip.add(Component.translatable("tooltip.create_enchantment_industry.affix_template.effect.line", effect)
                    .withStyle(ChatFormatting.YELLOW));
        }
    }
}
