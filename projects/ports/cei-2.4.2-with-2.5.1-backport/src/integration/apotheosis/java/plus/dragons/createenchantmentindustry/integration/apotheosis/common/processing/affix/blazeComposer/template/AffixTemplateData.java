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

import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import dev.shadowsoffire.apotheosis.affix.Affix;
import dev.shadowsoffire.apotheosis.loot.LootRarity;
import dev.shadowsoffire.apotheosis.loot.RarityRegistry;
import dev.shadowsoffire.placebo.reload.DynamicHolder;
import io.netty.buffer.ByteBuf;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Optional;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.resources.ResourceLocation;

public record AffixTemplateData(
        DynamicHolder<LootRarity> rarity,
        List<AffixTemplateEntry> entries) {
    // Network decode guard only; gameplay does not cap how many affixes a template may store.
    private static final int MAX_ENTRIES = 256;

    public static final Codec<AffixTemplateData> CODEC = RecordCodecBuilder.create(instance -> instance.group(
            RarityRegistry.INSTANCE.holderCodec().fieldOf("rarity").forGetter(AffixTemplateData::rarity),
            AffixTemplateEntry.CODEC.listOf().fieldOf("entries").forGetter(AffixTemplateData::entries))
            .apply(instance, AffixTemplateData::new));

    public static final StreamCodec<ByteBuf, AffixTemplateData> STREAM_CODEC = StreamCodec.composite(
            RarityRegistry.INSTANCE.holderStreamCodec(), AffixTemplateData::rarity,
            AffixTemplateEntry.STREAM_CODEC.apply(ByteBufCodecs.list(MAX_ENTRIES)), AffixTemplateData::entries,
            AffixTemplateData::new);

    public AffixTemplateData {
        entries = normalizeEntries(entries);
    }

    public static AffixTemplateData single(DynamicHolder<LootRarity> rarity, AffixTemplateEntry entry) {
        return new AffixTemplateData(rarity, List.of(entry));
    }

    public boolean isBound() {
        return rarity.isBound() && entries.stream().allMatch(AffixTemplateEntry::isBound);
    }

    public boolean isEmpty() {
        return entries.isEmpty();
    }

    public int size() {
        return entries.size();
    }

    public Optional<AffixTemplateEntry> get(DynamicHolder<Affix> affix) {
        return entries.stream()
                .filter(entry -> entry.affix().equals(affix))
                .findFirst();
    }

    public boolean contains(DynamicHolder<Affix> affix) {
        return get(affix).isPresent();
    }

    public AffixTemplateData withEntries(List<AffixTemplateEntry> entries) {
        return new AffixTemplateData(rarity, entries);
    }

    private static List<AffixTemplateEntry> normalizeEntries(List<AffixTemplateEntry> entries) {
        if (entries.isEmpty())
            return List.of();
        LinkedHashMap<ResourceLocation, AffixTemplateEntry> merged = new LinkedHashMap<>();
        entries.stream()
                .sorted(Comparator.comparing(entry -> entry.affix().getId()))
                .forEach(entry -> {
                    ResourceLocation id = entry.affix().getId();
                    AffixTemplateEntry existing = merged.get(id);
                    if (existing == null) {
                        merged.put(id, entry);
                    } else {
                        merged.put(id, existing.mergeMetadata(entry, Math.max(existing.level(), entry.level())));
                    }
                });
        return List.copyOf(new ArrayList<>(merged.values()));
    }
}
