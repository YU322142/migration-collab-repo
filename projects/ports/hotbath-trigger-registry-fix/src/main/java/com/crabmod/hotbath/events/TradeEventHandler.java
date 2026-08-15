package com.crabmod.hotbath.events;

import net.minecraft.world.entity.npc.VillagerProfession;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.trading.ItemCost;
import net.minecraft.world.item.trading.MerchantOffer;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.village.VillagerTradesEvent;
import net.neoforged.neoforge.event.village.WandererTradesEvent;

import static com.crabmod.hotbath.HotBath.MOD_ID;
import static com.crabmod.hotbath.registers.ItemRegister.BATH_HERB;

@EventBusSubscriber(modid = MOD_ID)
public class TradeEventHandler {
    @SubscribeEvent
    public static void onVillagerTradesEvent(VillagerTradesEvent event) {
        if (event.getType() == VillagerProfession.FARMER) {
            event
                    .getTrades()
                    .get(1)
                    .add(
                            (entity, random) ->
                                    new MerchantOffer(
                                            new ItemCost(Items.EMERALD, 10),
                                            new ItemStack(BATH_HERB.get(), 1),
                                            16, // maxUses
                                            2, // xpValue
                                            0.05F // priceMultiplier
                                    ));
        }
    }

    @SubscribeEvent
    public static void onWanderingTraderEvent(WandererTradesEvent event) {
        event
                .getGenericTrades()
                .add(
                        (entity, random) ->
                                new MerchantOffer(
                                        new ItemCost(Items.EMERALD, 15),
                                        new ItemStack(BATH_HERB.get(), 1),
                                        12, // maxUses
                                        1, // xpValue
                                        0.05F // priceMultiplier
                                ));
    }
}
