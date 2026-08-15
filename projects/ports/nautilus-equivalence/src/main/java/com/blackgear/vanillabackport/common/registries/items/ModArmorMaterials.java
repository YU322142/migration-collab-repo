package com.blackgear.vanillabackport.common.registries.items;

import net.minecraft.Util;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.crafting.Ingredient;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

import java.util.EnumMap;
import java.util.List;

public final class ModArmorMaterials {
    public static final DeferredRegister<ArmorMaterial> ARMOR_MATERIALS =
        DeferredRegister.create(BuiltInRegistries.ARMOR_MATERIAL, "nautilus_equivalence");

    public static final DeferredHolder<ArmorMaterial, ArmorMaterial> COPPER =
        ARMOR_MATERIALS.register("copper", () -> new ArmorMaterial(
            Util.make(new EnumMap<>(ArmorItem.Type.class), defense -> {
                defense.put(ArmorItem.Type.BOOTS, 1);
                defense.put(ArmorItem.Type.LEGGINGS, 3);
                defense.put(ArmorItem.Type.CHESTPLATE, 4);
                defense.put(ArmorItem.Type.HELMET, 2);
                defense.put(ArmorItem.Type.BODY, 4);
            }),
            8,
            SoundEvents.ARMOR_EQUIP_IRON,
            () -> Ingredient.of(Items.COPPER_INGOT),
            List.of(new ArmorMaterial.Layer(net.minecraft.resources.ResourceLocation.withDefaultNamespace("copper"))),
            0.0F,
            0.0F
        ));

    private ModArmorMaterials() {
    }
}
