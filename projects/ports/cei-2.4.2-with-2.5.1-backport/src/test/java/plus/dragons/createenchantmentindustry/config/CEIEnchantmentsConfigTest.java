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

package plus.dragons.createenchantmentindustry.config;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.electronwill.nightconfig.core.CommentedConfig;
import org.junit.jupiter.api.Test;

class CEIEnchantmentsConfigTest {
    @Test
    void migrationMutatesBothReplacementValuesAtomicallyAndIsIdempotent() {
        CEIEnchantmentsConfig config = new CEIEnchantmentsConfig();
        CommentedConfig values = CommentedConfig.inMemory();
        values.set("enchantments.enchantmentMaxLevelExtension", 7);
        values.set("enchantments.blazeEnchanterMaxLevelExtension", 1);
        values.set("enchantments.blazeForgerMaxLevelExtension", 1);

        assertTrue(config.migrateLegacyMaxLevelExtension(values));
        assertEquals(7, values.<Integer>get("enchantments.blazeEnchanterMaxLevelExtension"));
        assertEquals(7, values.<Integer>get("enchantments.blazeForgerMaxLevelExtension"));

        assertFalse(config.migrateLegacyMaxLevelExtension(values), "the synchronous reload emitted by save must not migrate again");
    }

    @Test
    void explicitlyConfiguredReplacementValuesTakePrecedence() {
        assertFalse(CEIEnchantmentsConfig.shouldMigrateLegacyMaxLevelExtension(7, 2, 1));
        assertFalse(CEIEnchantmentsConfig.shouldMigrateLegacyMaxLevelExtension(7, 1, 2));
        assertFalse(CEIEnchantmentsConfig.shouldMigrateLegacyMaxLevelExtension(7, 7, 7));
        assertFalse(CEIEnchantmentsConfig.shouldMigrateLegacyMaxLevelExtension(1, 1, 1));
        assertTrue(CEIEnchantmentsConfig.shouldMigrateLegacyMaxLevelExtension(7, 1, 1));
    }
}
