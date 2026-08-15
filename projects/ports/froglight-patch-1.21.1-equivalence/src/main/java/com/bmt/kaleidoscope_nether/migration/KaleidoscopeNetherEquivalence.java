package com.bmt.kaleidoscope_nether.migration;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.food.FoodProperties;
import net.minecraft.world.level.block.Block;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModList;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

import java.util.ArrayList;
import java.util.List;

@Mod(KaleidoscopeNetherEquivalence.MOD_ID)
public final class KaleidoscopeNetherEquivalence {
    public static final String MOD_ID = "kaleidoscope_nether_equivalence";
    public static final String NETHER_ID = "kaleidoscope_nether";
    private static final ResourceKey<CreativeModeTab> NETHER_TAB = ResourceKey.create(
            Registries.CREATIVE_MODE_TAB, ResourceLocation.fromNamespaceAndPath(NETHER_ID, "kaleidoscope_nether_tab"));

    private static final DeferredRegister<Block> DOLL_BLOCKS = DeferredRegister.create(Registries.BLOCK, NETHER_ID);
    private static final DeferredRegister<Item> DOLL_ITEMS = DeferredRegister.create(Registries.ITEM, NETHER_ID);
    private static final DeferredRegister<Item> EXTRA_ITEMS = DeferredRegister.create(Registries.ITEM, NETHER_ID);
    private static final List<DeferredHolder<Block, NetherDollBlock>> BLOCKS = new ArrayList<>(13);
    private static final List<DeferredHolder<Item, NetherDollItem>> ITEMS = new ArrayList<>(13);
    private static final FoodProperties BACKPORT_FOOD = new FoodProperties.Builder()
            .nutrition(2)
            .saturationModifier(0.3F)
            .alwaysEdible()
            .build();
    private static final DeferredHolder<Item, Item> GIANT_BEAST_CROISSANT = EXTRA_ITEMS.register(
            "giant_beast_croissant",
            () -> new Item(new Item.Properties().fireResistant().food(BACKPORT_FOOD)));
    private static final DeferredHolder<Item, Item> MAGMA_SWEET_AND_SOUR_PORK = EXTRA_ITEMS.register(
            "magma_sweet_and_sour_pork",
            () -> new Item(new Item.Properties().fireResistant().food(BACKPORT_FOOD)));

    static {
        for (int index = 0; index < 13; index++) {
            int dollIndex = index;
            String name = "doll_" + dollIndex;
            DeferredHolder<Block, NetherDollBlock> block = DOLL_BLOCKS.register(name, NetherDollBlock::new);
            DeferredHolder<Item, NetherDollItem> item = DOLL_ITEMS.register(name,
                    () -> new NetherDollItem(block.get(), dollIndex));
            BLOCKS.add(block);
            ITEMS.add(item);
        }
    }

    private final boolean standaloneDolls;

    public KaleidoscopeNetherEquivalence(IEventBus modBus) {
        NetherJuiceFluids.register(modBus);
        EXTRA_ITEMS.register(modBus);
        standaloneDolls = !ModList.get().isLoaded("kaleidoscope_doll");
        if (standaloneDolls) {
            DOLL_BLOCKS.register(modBus);
            DOLL_ITEMS.register(modBus);
        }
        modBus.addListener(this::addBackportsToCreativeTab);
        RuntimeEquivalenceGuard.register();
    }

    private void addBackportsToCreativeTab(BuildCreativeModeTabContentsEvent event) {
        if (!event.getTabKey().equals(NETHER_TAB)) {
            return;
        }
        if (standaloneDolls) {
            for (int index = ITEMS.size() - 1; index >= 0; index--) {
                event.insertFirst(new ItemStack(ITEMS.get(index).get()),
                        CreativeModeTab.TabVisibility.PARENT_AND_SEARCH_TABS);
            }
        }

        ItemStack hamYogurt = new ItemStack(BuiltInRegistries.ITEM.get(netherId("ham_yogurt")));
        ItemStack magmaPork = new ItemStack(MAGMA_SWEET_AND_SOUR_PORK.get());
        event.insertAfter(hamYogurt, magmaPork, CreativeModeTab.TabVisibility.PARENT_AND_SEARCH_TABS);
        event.insertAfter(magmaPork, new ItemStack(GIANT_BEAST_CROISSANT.get()),
                CreativeModeTab.TabVisibility.PARENT_AND_SEARCH_TABS);
    }

    public static ResourceLocation netherId(String path) {
        return ResourceLocation.fromNamespaceAndPath(NETHER_ID, path);
    }
}
