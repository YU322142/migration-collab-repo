package com.crabmod.hotbath.util;

import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.CraftingContainer;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.entity.player.PlayerEvent.ItemCraftedEvent;

import static com.crabmod.hotbath.registers.ItemRegister.HOT_WATER_BUCKET;

@EventBusSubscriber(modid = "hotbath")
public class CraftingEventHandler {

    @SubscribeEvent
    public static void onItemCrafted(ItemCraftedEvent event) {
        if (event.getInventory() instanceof CraftingContainer craftingInventory) {
            boolean foundHotWaterBucket = false;

            // Check if hot water bucket was used in the recipe
            for (int i = 0; i < craftingInventory.getContainerSize(); i++) {
                ItemStack itemStack = craftingInventory.getItem(i);
                if (itemStack.getItem() == HOT_WATER_BUCKET.get()) {
                    foundHotWaterBucket = true;
                    break;
                }
            }

            // If hot water bucket was used, give back an empty bucket to the player
            if (foundHotWaterBucket) {
                if (event.getEntity() instanceof Player player) {
                    ItemStack emptyBucket = new ItemStack(Items.BUCKET);
                    if (!player.getInventory().add(emptyBucket)) {
                        player.drop(emptyBucket, false);
                    }
                }
            }
        }
    }
}
