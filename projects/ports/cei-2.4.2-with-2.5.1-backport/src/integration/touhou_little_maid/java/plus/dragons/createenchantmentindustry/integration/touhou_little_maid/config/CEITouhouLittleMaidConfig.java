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

package plus.dragons.createenchantmentindustry.integration.touhou_little_maid.config;

import net.minecraft.Util;
import net.minecraft.util.Unit;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.config.ModConfig.Type;
import net.neoforged.fml.event.config.ModConfigEvent;
import net.neoforged.neoforge.common.ModConfigSpec;

public class CEITouhouLittleMaidConfig {
    private static final CEITouhouLittleMaidServerConfig SERVER_CONFIG = new CEITouhouLittleMaidServerConfig();
    private static ModConfigSpec SERVER_SPEC;

    public CEITouhouLittleMaidConfig(ModContainer modContainer) {
        SERVER_SPEC = Util.make(new ModConfigSpec.Builder().configure(builder -> {
            SERVER_CONFIG.registerAll(builder);
            return Unit.INSTANCE;
        }).getValue(), spec -> modContainer.registerConfig(Type.SERVER, spec, "create_enchantment_industry-touhou_little_maid-server.toml"));
    }

    public static CEITouhouLittleMaidServerConfig server() {
        return SERVER_CONFIG;
    }

    @SubscribeEvent
    public void onLoad(ModConfigEvent.Loading event) {
        if (event.getConfig().getSpec() == SERVER_SPEC)
            SERVER_CONFIG.onLoad();
    }

    @SubscribeEvent
    public void onReload(ModConfigEvent.Reloading event) {
        if (event.getConfig().getSpec() == SERVER_SPEC)
            SERVER_CONFIG.onReload();
    }
}
