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

import net.minecraft.core.component.DataComponentType;
import net.minecraft.core.registries.Registries;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.OverlimitAffixes;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.template.AffixTemplateData;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.CEIACommon;

public class CEIAXDataComponents {
    public static final DeferredRegister.DataComponents REGISTRAR = DeferredRegister.createDataComponents(Registries.DATA_COMPONENT_TYPE, CEIACommon.ID);

    public static final DeferredHolder<DataComponentType<?>, DataComponentType<AffixTemplateData>> AFFIX_TEMPLATE = REGISTRAR.registerComponentType(
            "affix_template",
            builder -> builder
                    .persistent(AffixTemplateData.CODEC)
                    .networkSynchronized(AffixTemplateData.STREAM_CODEC));

    public static final DeferredHolder<DataComponentType<?>, DataComponentType<OverlimitAffixes>> OVERLIMIT_AFFIXES = REGISTRAR.registerComponentType(
            "overlimit_affixes",
            builder -> builder
                    .persistent(OverlimitAffixes.CODEC)
                    .networkSynchronized(OverlimitAffixes.STREAM_CODEC));

    public static void register(IEventBus modBus) {
        REGISTRAR.register(modBus);
    }
}
