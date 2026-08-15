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

package plus.dragons.createenchantmentindustry.data;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import java.util.concurrent.CompletableFuture;
import net.minecraft.core.HolderLookup;
import net.minecraft.data.CachedOutput;
import net.minecraft.data.DataProvider;
import net.minecraft.data.PackOutput;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.neoforge.common.conditions.ICondition;

public final class CEIConditionalLootTables {
    private CEIConditionalLootTables() {}

    public static JsonObject selfDroppingBlock(ResourceLocation block, HolderLookup.Provider registries, ICondition condition) {
        return block(block, itemEntry(block), registries, condition);
    }

    public static JsonObject block(ResourceLocation block, JsonObject entry, HolderLookup.Provider registries, ICondition condition) {
        var table = new JsonObject();
        table.addProperty("type", "minecraft:block");
        table.add("pools", pools(entry));
        table.addProperty("random_sequence", block.withPrefix("blocks/").toString());
        ICondition.writeConditions(registries, table, condition);
        return table;
    }

    public static JsonObject itemEntry(ResourceLocation item) {
        var entry = new JsonObject();
        entry.addProperty("type", "minecraft:item");
        entry.addProperty("name", item.toString());
        return entry;
    }

    public static JsonObject copyComponents(ResourceLocation component) {
        var function = new JsonObject();
        function.addProperty("function", "minecraft:copy_components");
        function.addProperty("source", "block_entity");
        var include = new JsonArray();
        include.add(component.toString());
        function.add("include", include);
        return function;
    }

    public static CompletableFuture<?> saveBlock(PackOutput output, ResourceLocation block, JsonObject table) {
        var pathProvider = output.createPathProvider(PackOutput.Target.DATA_PACK, "loot_table");
        // These tables intentionally overwrite Registrate's default block loot tables at
        // the same path. The shared hash cache can otherwise skip the second write and
        // leave the unconditional table on disk.
        return DataProvider.saveStable(CachedOutput.NO_CACHE, table, pathProvider.json(block.withPrefix("blocks/")));
    }

    private static JsonArray pools(JsonObject entry) {
        var pool = new JsonObject();
        pool.addProperty("bonus_rolls", 0.0);
        pool.add("conditions", explosionConditions());
        var entries = new JsonArray();
        entries.add(entry);
        pool.add("entries", entries);
        pool.addProperty("rolls", 1.0);
        var pools = new JsonArray();
        pools.add(pool);
        return pools;
    }

    private static JsonArray explosionConditions() {
        var condition = new JsonObject();
        condition.addProperty("condition", "minecraft:survives_explosion");
        var conditions = new JsonArray();
        conditions.add(condition);
        return conditions;
    }
}
