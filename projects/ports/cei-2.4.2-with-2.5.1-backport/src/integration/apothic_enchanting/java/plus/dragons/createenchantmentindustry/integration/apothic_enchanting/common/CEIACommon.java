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

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common;

import net.createmod.ponder.foundation.PonderIndex;
import net.minecraft.client.renderer.item.ItemProperties;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.event.lifecycle.FMLClientSetupEvent;
import net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent;
import net.neoforged.fml.event.lifecycle.FMLConstructModEvent;
import net.neoforged.fml.event.lifecycle.FMLLoadCompleteEvent;
import net.neoforged.fml.loading.FMLLoader;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.AddReloadListenerEvent;
import plus.dragons.createdragonsplus.common.CDPRegistrate;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.integration.ModIntegration;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.client.ponder.CEIAPonderPlugin;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.client.registry.CEIAPartialModels;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.contraptions.actors.enderWovenBag.EnderWovenBagItem;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.processing.infuser.InfuserBlockEntity;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.registry.*;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.config.CEIAConfig;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.integration.CEIMaxEnchantmentLevel;

@Mod(CEICommon.ID)
public class CEIACommon {
    public static final String ID = CEICommon.ID;
    public static final CDPRegistrate REGISTRATE = CEICommon.REGISTRATE;

    public CEIACommon(IEventBus modBus, ModContainer modContainer) {
        if (ModIntegration.APOTHIC_ENCHANTING.enabled()) {
            modBus.register(new Common(modBus, modContainer));
            if (FMLLoader.getDist() == Dist.CLIENT)
                modBus.register(new Client());
        }
    }

    public static class Common {
        IEventBus modBus;
        ModContainer modContainer;

        Common(IEventBus modBus, ModContainer modContainer) {
            this.modBus = modBus;
            this.modContainer = modContainer;
        }

        @SubscribeEvent
        public void construct(final FMLConstructModEvent event) {
            CEIABlocks.register(modBus);
            CEIAItems.register();
            CEIABlockEntities.register(modBus);
            CEIAFluids.register(modBus);
            CEIACreativeModeTabs.register(modBus);
            CEIARecipes.register(modBus);
            CEIADataComponents.register(modBus);
            CEIAItemAttributes.register(modBus);
            modBus.register(CEIAPackets.class);
            modBus.register(new CEIAConfig(modContainer));
            NeoForge.EVENT_BUS.addListener(Common::addReloadListeners);
            NeoForge.EVENT_BUS.register(CEIAFluids.Events.class);
        }

        @SubscribeEvent
        public void setup(final FMLCommonSetupEvent event) {}

        @SubscribeEvent
        public void complete(final FMLLoadCompleteEvent event) {
            CEIMaxEnchantmentLevel.register();
        }

        public static void addReloadListeners(AddReloadListenerEvent event) {
            event.addListener(InfuserBlockEntity.RELOAD_LISTENER);
        }
    }

    public static class Client {
        @SubscribeEvent
        public void construct(final FMLConstructModEvent event) {
            // CEIPartialModels must be registered here,
            // or when PartialModelEventHandler#onRegisterAdditional triggered,
            // PartialModel.ALL won't include all partial model in 'some cases'
            // AllPartialModels#ini does not do this since AllPartialModels is already triggered at AllBlocks.TRACK
            // Issue: https://github.com/Creators-of-Create/Create/issues/8259
            CEIAPartialModels.register();
        }

        @SubscribeEvent
        public void setup(final FMLClientSetupEvent event) {
            event.enqueueWork(() -> {
                PonderIndex.addPlugin(new CEIAPonderPlugin());
                ItemProperties.register(
                        CEIABlocks.ENDER_WOVEN_BAG.asItem(),
                        CEICommon.asResource("open"),
                        EnderWovenBagItem::override);
            });
        }
    }
}
