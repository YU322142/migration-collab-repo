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

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry;

import static plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.CEIACommon.REGISTRATE;

import com.simibubi.create.AllTags;
import com.tterrag.registrate.providers.RegistrateTagsProvider;
import com.tterrag.registrate.util.entry.FluidEntry;
import net.createmod.catnip.theme.Color;
import net.minecraft.core.registries.Registries;
import net.minecraft.tags.TagKey;
import net.minecraft.world.item.Rarity;
import net.minecraft.world.level.material.Fluid;
import net.minecraft.world.level.pathfinder.PathType;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.fluids.BaseFlowingFluid;
import net.neoforged.neoforge.registries.DeferredHolder;
import plus.dragons.createdragonsplus.common.fluids.SolidRenderFluidType;
import plus.dragons.createdragonsplus.data.tag.IntrinsicTagRegistry;
import plus.dragons.createenchantmentindustry.common.CEICommon;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.CEIACommon;

public class CEIAXFluids {
    public static final ModTags MOD_TAGS = new ModTags();
    public static final FluidEntry<BaseFlowingFluid.Source> APOTHEOTIC_ESSENCE = new FluidEntry<>(REGISTRATE,
            DeferredHolder.create(Registries.FLUID, REGISTRATE.asResource("apotheotic_essence")));
    public static final FluidEntry<BaseFlowingFluid.Flowing> APOTHEOTIC_ESSENCE_FLOWING = REGISTRATE
            .fluid("apotheotic_essence", SolidRenderFluidType.create(new Color(0xf56f22).asVectorF(), () -> 1f)) // TODO need adjust
            .asOptional()
            .properties(builder -> builder
                    .rarity(Rarity.EPIC)
                    .lightLevel(15)
                    .pathType(PathType.BLOCKED)
                    .adjacentPathType(PathType.BLOCKED))
            .fluidProperties(p -> p.levelDecreasePerBlock(2).explosionResistance(100f))
            .source(BaseFlowingFluid.Source::new)
            .block()
            .properties(properties -> properties
                    .lightLevel((b) -> 15))
            .build()
            .bucket()
            .properties(properties -> properties
                    .rarity(Rarity.EPIC))
            .build()
            .register();

    public static final FluidEntry<BaseFlowingFluid.Source> CRYSTAL_ESSENCE = new FluidEntry<>(REGISTRATE,
            DeferredHolder.create(Registries.FLUID, REGISTRATE.asResource("crystal_essence")));
    public static final FluidEntry<BaseFlowingFluid.Flowing> CRYSTAL_ESSENCE_FLOWING = REGISTRATE
            .fluid("crystal_essence", SolidRenderFluidType.create(new Color(0x8778fa).asVectorF(), () -> 1f)) // TODO need adjust
            .asOptional()
            .properties(builder -> builder
                    .rarity(Rarity.RARE)
                    .lightLevel(8)
                    .pathType(PathType.BLOCKED)
                    .adjacentPathType(PathType.BLOCKED))
            .fluidProperties(p -> p.levelDecreasePerBlock(2).explosionResistance(100f))
            .source(BaseFlowingFluid.Source::new)
            .block()
            .properties(properties -> properties
                    .lightLevel((b) -> 8))
            .build()
            .bucket()
            .properties(properties -> properties
                    .rarity(Rarity.RARE))
            .build()
            .register();

    public static void register(IEventBus modBus) {
        // modBus.register(CEIAXFluids.class);  // TODO Highly WIP, fluid interaction, dispenser behavior, pipe interaction, open end pipe effect...
        REGISTRATE.registerFluidTags(MOD_TAGS);
    }

    public static class ModTags extends IntrinsicTagRegistry<Fluid, RegistrateTagsProvider.IntrinsicImpl<Fluid>> {
        public final TagKey<Fluid> fanSalvagingCatalysts = tag("fan_processing_catalysts/salvaging", "Bulk Salvaging Catalysts");

        public ModTags() {
            super(CEIACommon.ID, Registries.FLUID);
        }

        @Override
        public void generate(RegistrateTagsProvider.IntrinsicImpl<Fluid> provider) {
            super.generate(provider);
            provider.addTag(fanSalvagingCatalysts)
                    .addOptional(CEICommon.asResource("infused_dragon_breath"));
            provider.addTag(AllTags.AllFluidTags.BOTTOMLESS_DENY.tag)
                    .addOptional(CEICommon.asResource("apotheotic_essence"))
                    .addOptional(CEICommon.asResource("flowing_apotheotic_essence"))
                    .addOptional(CEICommon.asResource("crystal_essence"))
                    .addOptional(CEICommon.asResource("flowing_crystal_essence"));
        }
    }
}
