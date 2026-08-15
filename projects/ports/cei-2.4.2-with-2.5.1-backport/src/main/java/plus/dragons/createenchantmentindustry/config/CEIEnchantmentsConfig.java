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

import com.electronwill.nightconfig.core.CommentedConfig;
import java.util.List;
import net.createmod.catnip.config.ConfigBase;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class CEIEnchantmentsConfig extends ConfigBase {
    private static final Logger LOGGER = LoggerFactory.getLogger(CEIEnchantmentsConfig.class);
    private static final int DEFAULT_MAX_LEVEL_EXTENSION = 1;
    private static final List<String> LEGACY_MAX_LEVEL_EXTENSION_PATH = List.of("enchantments", "enchantmentMaxLevelExtension");
    private static final List<String> ENCHANTER_MAX_LEVEL_EXTENSION_PATH = List.of("enchantments", "blazeEnchanterMaxLevelExtension");
    private static final List<String> FORGER_MAX_LEVEL_EXTENSION_PATH = List.of("enchantments", "blazeForgerMaxLevelExtension");

    public final ConfigInt blazeEnchanterMaxEnchantLevel = i(30, 0,
            "blazeEnchanterMaxEnchantLevel",
            Comments.blazeEnchanterMaxEnchantLevel);
    public final ConfigInt blazeEnchanterMaxSuperEnchantLevel = i(60, 0,
            "blazeEnchanterMaxSuperEnchantLevel",
            Comments.blazeEnchanterMaxSuperEnchantLevel);
    public final ConfigFloat blazeEnchanterBlockedLightningCurseChance = f(0.5f, 0.0f, 1.0f,
            "blazeEnchanterBlockedLightningCurseChance",
            Comments.blazeEnchanterBlockedLightningCurseChance);
    public final ConfigInt blazeEnchanterBlockedLightningCurseCount = i(1, 0, 16,
            "blazeEnchanterBlockedLightningCurseCount",
            Comments.blazeEnchanterBlockedLightningCurseCount);
    public final ConfigInt blazeEnchanterBlockedLightningCurseMaxLevel = i(1, 1, 255,
            "blazeEnchanterBlockedLightningCurseMaxLevel",
            Comments.blazeEnchanterBlockedLightningCurseMaxLevel);
    /**
     * Retained so an existing 2.4.2 server config remains readable. When this
     * value is customized and both replacement values are still at their
     * defaults, {@link #migrateLegacyMaxLevelExtension(CommentedConfig)} copies it to both.
     */
    @Deprecated
    public final ConfigInt enchantmentMaxLevelExtension = i(DEFAULT_MAX_LEVEL_EXTENSION, 0, 255,
            "enchantmentMaxLevelExtension",
            Comments.enchantmentMaxLevelExtension);
    public final ConfigInt blazeEnchanterMaxLevelExtension = i(DEFAULT_MAX_LEVEL_EXTENSION, 0, 255,
            "blazeEnchanterMaxLevelExtension",
            Comments.blazeEnchanterMaxLevelExtension);
    public final ConfigInt blazeForgerMaxLevelExtension = i(DEFAULT_MAX_LEVEL_EXTENSION, 0, 255,
            "blazeForgerMaxLevelExtension",
            Comments.blazeForgerMaxLevelExtension);
    public final ConfigBool ignoreEnchantmentCompatibility = b(true,
            "ignoreEnchantmentCompatibility",
            Comments.ignoreEnchantmentCompatibility);
    public final ConfigBool extractEnchantmentRespectLevelExtension = b(false,
            "extractEnchantmentRespectLevelExtension",
            Comments.extractEnchantmentRespectLevelExtension);

    @Override
    public String getName() {
        return "enchantments";
    }

    public boolean migrateLegacyMaxLevelExtension(CommentedConfig values) {
        int legacy = values.getOrElse(LEGACY_MAX_LEVEL_EXTENSION_PATH, DEFAULT_MAX_LEVEL_EXTENSION);
        int enchanter = values.getOrElse(ENCHANTER_MAX_LEVEL_EXTENSION_PATH, DEFAULT_MAX_LEVEL_EXTENSION);
        int forger = values.getOrElse(FORGER_MAX_LEVEL_EXTENSION_PATH, DEFAULT_MAX_LEVEL_EXTENSION);
        if (legacy == DEFAULT_MAX_LEVEL_EXTENSION)
            return false;
        if (shouldMigrateLegacyMaxLevelExtension(legacy, enchanter, forger)) {
            // Mutate both keys before saving. NeoForge's LoadedConfig.save()
            // synchronously emits a Reloading event, so this makes that callback
            // observe the completed migration and keeps the operation idempotent.
            values.set(ENCHANTER_MAX_LEVEL_EXTENSION_PATH, legacy);
            values.set(FORGER_MAX_LEVEL_EXTENSION_PATH, legacy);
            LOGGER.warn("Migrated legacy enchantmentMaxLevelExtension={} to blazeEnchanterMaxLevelExtension and blazeForgerMaxLevelExtension.", legacy);
            return true;
        } else if (enchanter != legacy || forger != legacy) {
            LOGGER.warn("Legacy enchantmentMaxLevelExtension={} was not applied because replacement values are already configured (enchanter={}, forger={}).", legacy, enchanter, forger);
        }
        return false;
    }

    static boolean shouldMigrateLegacyMaxLevelExtension(int legacy, int enchanter, int forger) {
        return legacy != DEFAULT_MAX_LEVEL_EXTENSION
                && enchanter == DEFAULT_MAX_LEVEL_EXTENSION
                && forger == DEFAULT_MAX_LEVEL_EXTENSION;
    }

    static class Comments {
        static final String blazeEnchanterMaxEnchantLevel = "The max experience level a Blaze Enchanter can use in Regular Enchanting";
        static final String blazeEnchanterMaxSuperEnchantLevel = "The max experience level a Blaze Enchanter can use in Super Enchanting";
        static final String blazeEnchanterBlockedLightningCurseChance = "Chance per curse roll for blocked-lightning Super Enchanting to add an applicable curse to the result";
        static final String blazeEnchanterBlockedLightningCurseCount = "Maximum curse rolls for blocked-lightning Super Enchanting";
        static final String blazeEnchanterBlockedLightningCurseMaxLevel = "Maximum curse level blocked-lightning Super Enchanting can add";
        static final String enchantmentMaxLevelExtension = "Deprecated 2.4.2 compatibility value. A customized value is copied to both replacement options when they are still at defaults";
        static final String blazeEnchanterMaxLevelExtension = "Max enchantment level in Super Enchanting will be extended by this value when no per-enchantment processing rule exists";
        static final String blazeForgerMaxLevelExtension = "Max enchantment level in Super Forging will be extended by this value when no per-enchantment processing rule exists";
        static final String ignoreEnchantmentCompatibility = "If Super Enchanting and Super Forging ignores enchantment compatibility";
        static final String extractEnchantmentRespectLevelExtension = "If Enchantment extraction respects over-capped level";
    }
}
