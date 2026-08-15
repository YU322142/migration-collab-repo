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

import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import com.simibubi.create.content.processing.recipe.ProcessingRecipeParams;
import java.util.function.Function;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;

public class InfusingRecipeParams extends ProcessingRecipeParams {
    public static final MapCodec<InfusingRecipeParams> CODEC = RecordCodecBuilder.mapCodec(instance -> instance.group(
            codec(InfusingRecipeParams::new).forGetter(Function.identity()),
            InfusionStats.CODEC.fieldOf("stats").forGetter(InfusingRecipeParams::getStats)).apply(instance, InfusingRecipeParams::setStats));
    public static final StreamCodec<RegistryFriendlyByteBuf, InfusingRecipeParams> STREAM_CODEC = streamCodec(InfusingRecipeParams::new);
    protected InfusionStats stats;

    protected InfusingRecipeParams() {
        super();
    }

    public InfusingRecipeParams(InfusionStats stats) {
        this.stats = stats;
    }

    public InfusionStats getStats() {
        return stats;
    }

    protected InfusingRecipeParams setStats(InfusionStats stats) {
        this.stats = stats;
        return this;
    }

    @Override
    protected void encode(RegistryFriendlyByteBuf buffer) {
        super.encode(buffer);
        InfusionStats.STREAM_CODEC.encode(buffer, stats);
    }

    @Override
    protected void decode(RegistryFriendlyByteBuf buffer) {
        super.decode(buffer);
        stats = InfusionStats.STREAM_CODEC.decode(buffer);
    }
}
