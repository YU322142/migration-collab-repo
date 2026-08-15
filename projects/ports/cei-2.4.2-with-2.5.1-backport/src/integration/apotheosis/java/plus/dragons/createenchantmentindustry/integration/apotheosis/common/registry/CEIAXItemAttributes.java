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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry;

import static plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.CEIACommon.REGISTRATE;

import com.simibubi.create.api.registry.CreateRegistries;
import com.simibubi.create.content.logistics.item.filter.attribute.ItemAttributeType;
import com.simibubi.create.content.logistics.item.filter.attribute.SingletonItemAttribute;
import dev.shadowsoffire.apotheosis.Apoth;
import dev.shadowsoffire.apotheosis.socket.SocketHelper;
import dev.shadowsoffire.apotheosis.socket.gem.GemInstance;
import java.util.function.BiPredicate;
import java.util.function.Supplier;
import net.minecraft.core.Holder;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.SingleRecipeInput;
import net.minecraft.world.level.Level;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.registries.DeferredRegister;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.logistics.attributes.GemPurityAttributes;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.affixEnhancer.AffixAugmentorBlockEntity;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.socket.gem.gemCutter.GemCutterBlockEntity;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.CEIACommon;

public class CEIAXItemAttributes {
    private static final DeferredRegister<ItemAttributeType> ITEM_ATTRIBUTES = DeferredRegister
            .create(CreateRegistries.ITEM_ATTRIBUTE_TYPE, CEIACommon.ID);

    public static final Holder<ItemAttributeType> CAN_BE_SALVAGED = singleton("can_be_salvaged",
            "can be Salvaged",
            "cannot be Salvaged",
            (stack, level) -> {
                var recipeManager = level.getRecipeManager();
                var input = new SingleRecipeInput(stack);
                if (recipeManager
                        .getRecipeFor(CEIAXRecipes.SALVAGING.getType(), input, level)
                        .isPresent())
                    return true;
                return level.getRecipeManager()
                        .getRecipeFor(Apoth.RecipeTypes.SALVAGING, new SingleRecipeInput(stack), level)
                        .isPresent();
            });
    public static final Holder<ItemAttributeType> HAS_GEM = singleton("has_gem",
            "has gem socketed",
            "has no socketed gem",
            (stack, level) -> SocketHelper.getGems(stack).stream().anyMatch(GemInstance::isValid));

    public static final Holder<ItemAttributeType> HAS_EMPTY_SOCKET = singleton("has_empty_socket",
            "has empty socket",
            "has no empty socket",
            (stack, level) -> SocketHelper.hasEmptySockets(stack));

    public static final Holder<ItemAttributeType> IS_UPGRADABLE_GEM = singleton("is_upgradable_gem",
            "is upgradable gem",
            "is not upgradable gem",
            (stack, level) -> GemCutterBlockEntity.isUpgradableGem(stack));

    public static final Holder<ItemAttributeType> HAS_UPGRADABLE_AFFIX = singleton("has_upgradable_affix",
            "has upgradable affix",
            "has no upgradable affix",
            (stack, level) -> AffixAugmentorBlockEntity.hasUpgradableAffix(stack));

    public static final Holder<ItemAttributeType> GEM_PURITY = complex("gem_purity",
            "is a gem of %1$s purity",
            "is not a gem of %1$s purity",
            GemPurityAttributes.Type::new);

    private static Holder<ItemAttributeType> singleton(String name, String description, String invertedDescription, BiPredicate<ItemStack, Level> predicate) {
        String descriptionKey = "create.item_attributes." + CEIACommon.ID + "." + name;
        String invertedDescriptionKey = descriptionKey + ".inverted";
        REGISTRATE.addRawLang(descriptionKey, description);
        REGISTRATE.addRawLang(invertedDescriptionKey, invertedDescription);
        return ITEM_ATTRIBUTES.register(name, () -> new SingletonItemAttribute.Type(type -> new SingletonItemAttribute(type, predicate, CEIACommon.ID + "." + name)));
    }

    private static Holder<ItemAttributeType> complex(String name, String description, String invertedDescription, Supplier<ItemAttributeType> supplier) {
        String descriptionKey = "create.item_attributes." + CEIACommon.ID + "." + name;
        String invertedDescriptionKey = descriptionKey + ".inverted";
        REGISTRATE.addRawLang(descriptionKey, description);
        REGISTRATE.addRawLang(invertedDescriptionKey, invertedDescription);
        return ITEM_ATTRIBUTES.register(name, supplier);
    }

    public static void register(IEventBus modBus) {
        ITEM_ATTRIBUTES.register(modBus);
    }
}
