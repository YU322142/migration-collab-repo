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

import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import dev.shadowsoffire.apotheosis.affix.Affix;
import dev.shadowsoffire.apotheosis.affix.AffixRegistry;
import dev.shadowsoffire.placebo.reload.DynamicHolder;
import io.netty.buffer.ByteBuf;
import java.util.HashMap;
import java.util.Map;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;

public record OverlimitAffixes(Map<DynamicHolder<Affix>, Float> levels) {
    public static final OverlimitAffixes EMPTY = new OverlimitAffixes(Map.of());
    public static final Codec<OverlimitAffixes> CODEC = RecordCodecBuilder.create(instance -> instance.group(
            Codec.unboundedMap(AffixRegistry.INSTANCE.holderCodec(), Codec.floatRange(0, Float.MAX_VALUE))
                    .fieldOf("levels")
                    .forGetter(OverlimitAffixes::levels))
            .apply(instance, OverlimitAffixes::new));
    public static final StreamCodec<ByteBuf, OverlimitAffixes> STREAM_CODEC = ByteBufCodecs
            .map(HashMap::new, AffixRegistry.INSTANCE.holderStreamCodec(), ByteBufCodecs.FLOAT)
            .map(OverlimitAffixes::new, overlimit -> new HashMap<>(overlimit.levels()));

    public boolean isEmpty() {
        return levels.isEmpty();
    }

    public float getLevel(DynamicHolder<Affix> affix) {
        return levels.getOrDefault(affix, 0F);
    }
}
