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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.logistics.attributes;

import com.mojang.serialization.MapCodec;
import com.simibubi.create.content.logistics.item.filter.attribute.ItemAttribute;
import com.simibubi.create.content.logistics.item.filter.attribute.ItemAttributeType;
import dev.shadowsoffire.apotheosis.Apoth;
import dev.shadowsoffire.apotheosis.socket.gem.GemItem;
import dev.shadowsoffire.apotheosis.socket.gem.Purity;
import io.netty.buffer.ByteBuf;
import java.util.List;
import net.createmod.catnip.lang.LangBuilder;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import org.jetbrains.annotations.NotNull;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXItemAttributes;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.CEIACommon;

public record GemPurityAttributes(Purity purity) implements ItemAttribute {
    public static final MapCodec<GemPurityAttributes> CODEC = Purity.CODEC
            .xmap(GemPurityAttributes::new, GemPurityAttributes::purity)
            .fieldOf("value");

    public static final StreamCodec<ByteBuf, GemPurityAttributes> STREAM_CODEC = Purity.STREAM_CODEC
            .map(GemPurityAttributes::new, GemPurityAttributes::purity);

    @Override
    public boolean appliesTo(ItemStack stack, Level world) {
        return (stack.is(Apoth.Items.GEM));
    }

    @Override
    public ItemAttributeType getType() {
        return CEIAXItemAttributes.GEM_PURITY.value();
    }

    @Override
    public String getTranslationKey() {
        return CEIACommon.ID + ".gem_purity";
    }

    @Override
    public Object[] getTranslationParameters() {
        LangBuilder parameter = new LangBuilder(CEIACommon.ID).add(purity.toComponent());
        return new Object[] { parameter };
    }

    public static class Type implements ItemAttributeType {
        @Override
        public @NotNull ItemAttribute createAttribute() {
            return new GemPurityAttributes(Purity.CRACKED);
        }

        @Override
        public List<ItemAttribute> getAllAttributes(ItemStack stack, Level level) {
            if (stack.is(Apoth.Items.GEM))
                return List.of(new GemPurityAttributes(GemItem.getPurity(stack)));
            return List.of();
        }

        @Override
        public MapCodec<? extends ItemAttribute> codec() {
            return CODEC;
        }

        @Override
        public StreamCodec<? super RegistryFriendlyByteBuf, ? extends ItemAttribute> streamCodec() {
            return STREAM_CODEC;
        }
    }
}
