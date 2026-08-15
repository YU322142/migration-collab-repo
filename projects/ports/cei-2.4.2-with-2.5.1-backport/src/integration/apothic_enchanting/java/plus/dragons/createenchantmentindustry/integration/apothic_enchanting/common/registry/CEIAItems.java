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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.registry;

import static plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.CEIACommon.REGISTRATE;

import com.simibubi.create.AllTags;
import com.simibubi.create.content.processing.sequenced.SequencedAssemblyItem;
import com.tterrag.registrate.util.entry.ItemEntry;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.neoforge.common.Tags;
import plus.dragons.createdragonsplus.common.registry.CDPItems;
import plus.dragons.createdragonsplus.data.tag.ItemTagRegistry;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.CEIACommon;

public class CEIAItems {
    public static final ModTags MOD_TAGS = new ModTags();

    public static final ItemEntry<SequencedAssemblyItem> INCOMPLETE_BRASS_BOOKSHELF = REGISTRATE
            .item("incomplete_brass_bookshelf", SequencedAssemblyItem::new)
            .asOptional()
            .model((ctx, prov) -> prov
                    .cubeColumn(ctx.getName(), prov.modLoc("block/brass_bookshelf_top"), prov.modLoc("block/brass_bookshelf_bottom")))
            .register();

    public static class ModTags extends ItemTagRegistry {
        public ModTags() {
            super(CEIACommon.ID);
            addOptional(AllTags.AllItemTags.UPRIGHT_ON_BELT.tag, ResourceLocation.fromNamespaceAndPath("apothic_enchanting", "infused_breath"));
            addOptional(Tags.Items.BUCKETS, CEICommon.asResource("infused_dragon_breath_bucket"));
            addOptional(CDPItems.COMMON_TAGS.dragonBreathBuckets, CEICommon.asResource("infused_dragon_breath_bucket"));
        }
    }

    public static void register() {
        REGISTRATE.registerItemTags(MOD_TAGS);
    }
}
