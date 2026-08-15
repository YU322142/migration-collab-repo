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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer;

import dev.shadowsoffire.apotheosis.Apoth;
import dev.shadowsoffire.apotheosis.affix.Affix;
import dev.shadowsoffire.apotheosis.affix.AffixInstance;
import dev.shadowsoffire.apotheosis.affix.ItemAffixes;
import dev.shadowsoffire.placebo.reload.DynamicHolder;
import java.util.HashMap;
import java.util.Map;
import net.minecraft.world.item.ItemStack;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXDataComponents;

public class OverlimitAffixHelper {
    public static Map<DynamicHolder<Affix>, AffixInstance> applyTrueLevels(ItemStack stack, Map<DynamicHolder<Affix>, AffixInstance> affixes) {
        OverlimitAffixes overlimit = stack.get(CEIAXDataComponents.OVERLIMIT_AFFIXES.get());
        if (overlimit == null || overlimit.isEmpty() || affixes.isEmpty())
            return affixes;
        Map<DynamicHolder<Affix>, AffixInstance> result = null;
        for (var entry : affixes.entrySet()) {
            float trueLevel = overlimit.getLevel(entry.getKey());
            if (trueLevel > entry.getValue().level()) {
                if (result == null)
                    result = new HashMap<>(affixes);
                var instance = entry.getValue();
                result.put(entry.getKey(), new AffixInstance(instance.affix(), trueLevel, instance.rarity(), instance.stack()));
            }
        }
        return result == null ? affixes : Map.copyOf(result);
    }

    public static float getTrueLevel(ItemStack stack, DynamicHolder<Affix> affix, float fallback) {
        OverlimitAffixes overlimit = stack.get(CEIAXDataComponents.OVERLIMIT_AFFIXES.get());
        return overlimit == null ? fallback : Math.max(fallback, overlimit.getLevel(affix));
    }

    public static void setAffixLevel(ItemStack stack, DynamicHolder<Affix> affix, float level) {
        setAffixLevels(stack, Map.of(affix, level));
    }

    public static void setAffixLevels(ItemStack stack, Map<DynamicHolder<Affix>, Float> changedLevels) {
        ItemAffixes.Builder nativeBuilder = stack.getOrDefault(Apoth.Components.AFFIXES, ItemAffixes.EMPTY).toBuilder();
        for (var entry : changedLevels.entrySet()) {
            DynamicHolder<Affix> affix = entry.getKey();
            float level = entry.getValue();
            if (level <= 0) {
                nativeBuilder.remove(affix);
            } else {
                nativeBuilder.put(affix, Math.min(level, Affix.MAX_LEVEL));
            }
        }
        ItemAffixes nativeAffixes = nativeBuilder.build();
        if (nativeAffixes.isEmpty()) {
            stack.remove(Apoth.Components.AFFIXES);
        } else {
            stack.set(Apoth.Components.AFFIXES, nativeAffixes);
        }

        Map<DynamicHolder<Affix>, Float> levels = new HashMap<>();
        OverlimitAffixes old = stack.get(CEIAXDataComponents.OVERLIMIT_AFFIXES.get());
        if (old != null) {
            levels.putAll(old.levels());
        }
        for (var entry : changedLevels.entrySet()) {
            DynamicHolder<Affix> affix = entry.getKey();
            float level = entry.getValue();
            if (level > Affix.MAX_LEVEL) {
                levels.put(affix, level);
            } else {
                levels.remove(affix);
            }
        }
        if (levels.isEmpty()) {
            stack.remove(CEIAXDataComponents.OVERLIMIT_AFFIXES.get());
        } else {
            stack.set(CEIAXDataComponents.OVERLIMIT_AFFIXES.get(), new OverlimitAffixes(Map.copyOf(levels)));
        }
    }

    public static void removeAffix(ItemStack stack, DynamicHolder<Affix> affix) {
        setAffixLevel(stack, affix, 0);
    }
}
