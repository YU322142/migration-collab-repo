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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.kinetics.bookshelf;

import com.simibubi.create.foundation.blockEntity.behaviour.scrollValue.INamedIconOptions;
import com.simibubi.create.foundation.gui.AllIcons;
import net.createmod.catnip.lang.Lang;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.client.registry.CEIAIcons;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.CEIACommon;

public enum EnchantmentStatType implements INamedIconOptions {
    ETERNA(CEIAIcons.I_ETERNA),
    QUANTA(CEIAIcons.I_QUANTA),
    ARCANA(CEIAIcons.I_ARCANA);

    private String translationKey;
    private AllIcons icon;

    EnchantmentStatType(AllIcons icon) {
        this.icon = icon;
        translationKey = CEIACommon.ID + ".bookshelf.type." + Lang.asId(name());
    }

    @Override
    public AllIcons getIcon() {
        return icon;
    }

    @Override
    public String getTranslationKey() {
        return translationKey;
    }
}
