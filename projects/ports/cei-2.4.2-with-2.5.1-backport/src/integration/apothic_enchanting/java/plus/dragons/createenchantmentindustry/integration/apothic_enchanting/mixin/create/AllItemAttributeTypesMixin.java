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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.mixin.create;

import com.simibubi.create.content.logistics.item.filter.attribute.AllItemAttributeTypes;
import dev.shadowsoffire.apothic_enchanting.asm.EnchHooks;
import me.fallenbreath.conditionalmixin.api.annotation.Condition;
import me.fallenbreath.conditionalmixin.api.annotation.Restriction;
import net.minecraft.world.item.enchantment.Enchantment;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;
import plus.dragons.createenchantmentindustry.integration.ModIntegration;

@Restriction(require = @Condition(ModIntegration.Constants.APOTHIC_ENCHANTING))
@Mixin(AllItemAttributeTypes.class)
public class AllItemAttributeTypesMixin {
    @Redirect(method = "maxEnchanted", at = @At(value = "INVOKE", target = "Lnet/minecraft/world/item/enchantment/Enchantment;getMaxLevel()I"))
    private static int fixMaxLevelFilter(Enchantment instance) {
        return EnchHooks.getMaxLevel(instance);
    }
}
