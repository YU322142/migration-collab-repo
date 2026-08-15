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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common;

import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.EventPriority;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.event.lifecycle.FMLConstructModEvent;
import net.neoforged.fml.loading.FMLLoader;
import net.neoforged.neoforge.client.extensions.common.RegisterClientExtensionsEvent;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.data.event.GatherDataEvent;
import net.neoforged.neoforge.event.AddReloadListenerEvent;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.integration.ModIntegration;
import plus.dragons.createenchantmentindustry.integration.apotheosis.client.ponder.CEIAXPonderPlugin;
import plus.dragons.createenchantmentindustry.integration.apotheosis.client.registry.CEIAXPartialModels;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.AffixComposingRules;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.BlazeComposerItemRenderer;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.*;
import plus.dragons.createenchantmentindustry.integration.apotheosis.config.CEIAXConfig;
import plus.dragons.createenchantmentindustry.integration.apotheosis.data.CEIAXConditionalLootTableProvider;
import plus.dragons.createenchantmentindustry.integration.apotheosis.data.CEIAXRecipeProvider;

@Mod(CEICommon.ID)
public class CEIAXCommon {
    public CEIAXCommon(IEventBus modBus, ModContainer modContainer) {
        if (ModIntegration.APOTHEOSIS.enabled() && ModIntegration.APOTHIC_ENCHANTING.enabled()) {
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
            CEIAXItems.register();
            CEIAXDataComponents.register(modBus);
            CEIAXBlocks.register(modBus);
            CEIAXBlockEntities.register(modBus);
            CEIAXFluids.register(modBus);
            CEIAXCreativeModeTabs.register(modBus);
            CEIAXRecipes.register(modBus);
            CEIAXItemAttributes.register(modBus);
            CEIAXFanProcessingTypes.register(modBus);
            CEIAXArmInteractionPoints.register(modBus);
            CEIAXStats.register(modBus);
            modBus.register(new CEIAXConfig(modContainer));
            NeoForge.EVENT_BUS.addListener(Common::addReloadListeners);
        }

        @SubscribeEvent(priority = EventPriority.LOWEST)
        public void generate(final GatherDataEvent event) {
            var generator = event.getGenerator();
            var existingFileHelper = event.getExistingFileHelper();
            var lookupProvider = event.getLookupProvider();
            var output = generator.getPackOutput();
            var client = event.includeClient();
            var server = event.includeServer();
            generator.addProvider(server, new CEIAXRecipeProvider(output, lookupProvider));
            generator.addProvider(server, new CEIAXConditionalLootTableProvider(output, lookupProvider));
        }

        public static void addReloadListeners(AddReloadListenerEvent event) {
            event.addListener(AffixComposingRules.INSTANCE);
        }
    }

    public static class Client {
        @SubscribeEvent
        public void construct(final FMLConstructModEvent event) {
            CEIAXPartialModels.register();
            CEIAXPonderPlugin.register();
        }

        @SubscribeEvent
        public void registerClientExtensions(final RegisterClientExtensionsEvent event) {
            BlazeComposerItemRenderer.register(event);
        }
    }
}
