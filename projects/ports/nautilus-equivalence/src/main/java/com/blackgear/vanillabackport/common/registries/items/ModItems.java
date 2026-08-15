package com.blackgear.vanillabackport.common.registries.items;

import com.blackgear.vanillabackport.common.level.item.NautilusArmorItem;
import com.blackgear.vanillabackport.common.registries.entities.ModEntityTypes;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.ArmorMaterials;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.SpawnEggItem;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModItems {
    public static final DeferredRegister<Item> ITEMS =
        DeferredRegister.create(BuiltInRegistries.ITEM, "minecraft");

    public static final DeferredHolder<Item, Item> COPPER_NAUTILUS_ARMOR =
        ITEMS.register("copper_nautilus_armor", () -> new NautilusArmorItem(ModArmorMaterials.COPPER, new Item.Properties().durability(176), 4, 0.0F, 0.0F));
    public static final DeferredHolder<Item, Item> IRON_NAUTILUS_ARMOR =
        ITEMS.register("iron_nautilus_armor", () -> new NautilusArmorItem(ArmorMaterials.IRON, new Item.Properties().durability(240), 5, 0.0F, 0.0F));
    public static final DeferredHolder<Item, Item> GOLDEN_NAUTILUS_ARMOR =
        ITEMS.register("golden_nautilus_armor", () -> new NautilusArmorItem(ArmorMaterials.GOLD, new Item.Properties().durability(112), 7, 0.0F, 0.0F));
    public static final DeferredHolder<Item, Item> DIAMOND_NAUTILUS_ARMOR =
        ITEMS.register("diamond_nautilus_armor", () -> new NautilusArmorItem(ArmorMaterials.DIAMOND, new Item.Properties().durability(528), 11, 2.0F, 0.0F));
    public static final DeferredHolder<Item, Item> NETHERITE_NAUTILUS_ARMOR =
        ITEMS.register("netherite_nautilus_armor", () -> new NautilusArmorItem(ArmorMaterials.NETHERITE, new Item.Properties().durability(592).fireResistant(), 19, 3.0F, 0.1F));

    public static final DeferredHolder<Item, Item> NAUTILUS_SPAWN_EGG =
        ITEMS.register("nautilus_spawn_egg", () -> new SpawnEggItem(ModEntityTypes.NAUTILUS.get(), 0x746626, 0xDDC68E, new Item.Properties()));
    public static final DeferredHolder<Item, Item> ZOMBIE_NAUTILUS_SPAWN_EGG =
        ITEMS.register("zombie_nautilus_spawn_egg", () -> new SpawnEggItem(ModEntityTypes.ZOMBIE_NAUTILUS.get(), 0x746626, 0xDDC68E, new Item.Properties()));

    private ModItems() {
    }
}
