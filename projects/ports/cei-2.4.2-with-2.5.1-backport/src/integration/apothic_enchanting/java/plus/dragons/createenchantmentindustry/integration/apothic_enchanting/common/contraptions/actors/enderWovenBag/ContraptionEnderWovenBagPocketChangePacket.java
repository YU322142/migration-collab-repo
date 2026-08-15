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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.contraptions.actors.enderWovenBag;

import io.netty.buffer.ByteBuf;
import net.minecraft.core.BlockPos;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.loading.FMLLoader;
import net.neoforged.neoforge.network.handling.IPayloadContext;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.client.contraptions.actors.enderWovenBag.EnderWovenBagClientPacketHandler;

public record ContraptionEnderWovenBagPocketChangePacket(int entityId, BlockPos localPos, boolean open) implements CustomPacketPayload {

    public static final StreamCodec<ByteBuf, ContraptionEnderWovenBagPocketChangePacket> STREAM_CODEC = StreamCodec.composite(
            ByteBufCodecs.INT, ContraptionEnderWovenBagPocketChangePacket::entityId,
            BlockPos.STREAM_CODEC, ContraptionEnderWovenBagPocketChangePacket::localPos,
            ByteBufCodecs.BOOL, ContraptionEnderWovenBagPocketChangePacket::open,
            ContraptionEnderWovenBagPocketChangePacket::new);

    public static final CustomPacketPayload.Type<ContraptionEnderWovenBagPocketChangePacket> TYPE = new CustomPacketPayload.Type<>(CEICommon.asResource("contraption_ewb_change"));
    public static void handle(ContraptionEnderWovenBagPocketChangePacket packet, IPayloadContext context) {
        context.enqueueWork(() -> {
            if (FMLLoader.getDist() == Dist.CLIENT)
                EnderWovenBagClientPacketHandler.handle(packet);
        });
    }

    @Override
    public CustomPacketPayload.Type<? extends CustomPacketPayload> type() {
        return TYPE;
    }
}
