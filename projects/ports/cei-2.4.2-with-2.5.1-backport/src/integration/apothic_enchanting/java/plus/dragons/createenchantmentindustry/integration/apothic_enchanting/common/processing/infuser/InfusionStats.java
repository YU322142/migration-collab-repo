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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.processing.infuser;

import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import com.simibubi.create.api.equipment.goggles.IHaveGoggleInformation;
import java.util.List;
import net.minecraft.ChatFormatting;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtOps;
import net.minecraft.nbt.Tag;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.network.chat.Component;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.util.CEIALang;

public record InfusionStats(float eterna, float quanta, float arcana) implements IHaveGoggleInformation {

    private static final Logger LOGGER = LoggerFactory.getLogger(InfusionStats.class);
    public static final InfusionStats EMPTY = new InfusionStats(0f, 15f, 0f);

    public static Codec<InfusionStats> CODEC = RecordCodecBuilder.create(instance -> instance.group(
            Codec.floatRange(0, 100).fieldOf("eterna").forGetter(InfusionStats::eterna),
            Codec.floatRange(0, 100).fieldOf("quanta").forGetter(InfusionStats::quanta),
            Codec.floatRange(0, 100).fieldOf("arcana").forGetter(InfusionStats::arcana)).apply(instance, InfusionStats::new));

    public static StreamCodec<FriendlyByteBuf, InfusionStats> STREAM_CODEC = StreamCodec.composite(
            ByteBufCodecs.FLOAT, InfusionStats::eterna,
            ByteBufCodecs.FLOAT, InfusionStats::quanta,
            ByteBufCodecs.FLOAT, InfusionStats::arcana,
            InfusionStats::new);
    public static InfusionStats parse(HolderLookup.Provider lookupProvider, Tag tag) {
        if (tag == null)
            return EMPTY;
        return CODEC.parse(lookupProvider.createSerializationContext(NbtOps.INSTANCE), tag)
                .resultOrPartial(error -> LOGGER.warn("Failed to read infuser stats: {}", error))
                .orElse(EMPTY);
    }

    public Tag tag(HolderLookup.Provider lookupProvider) {
        return CODEC.encodeStart(lookupProvider.createSerializationContext(NbtOps.INSTANCE), this)
                .resultOrPartial(error -> LOGGER.warn("Failed to write infuser stats: {}", error))
                .orElseGet(CompoundTag::new);
    }

    public boolean qualified(InfusionStats input) {
        return input.eterna() >= eterna && input.quanta() >= quanta && input.arcana() >= arcana;
    }

    @Override
    public boolean addToGoggleTooltip(List<Component> tooltip, boolean isPlayerSneaking) {
        CEIALang.translate("gui.goggles.apotheotic_stats")
                .forGoggles(tooltip);
        CEIALang.translate("gui.goggles.infuser.stats.eterna", eterna).style(ChatFormatting.GREEN)
                .add(CEIALang.translate("gui.goggles.infuser.stats.arcana", arcana).text("% ").style(ChatFormatting.LIGHT_PURPLE))
                .add(CEIALang.translate("gui.goggles.infuser.stats.quanta", quanta).text("%").style(ChatFormatting.RED))
                .forGoggles(tooltip, 1);
        return true;
    }
}
