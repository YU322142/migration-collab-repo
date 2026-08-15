package com.github.ysbbbbbb.kaleidoscopetavern.init.register;

import com.github.ysbbbbbb.kaleidoscopetavern.KaleidoscopeTavern;
import com.github.ysbbbbbb.kaleidoscopetavern.block.brew.BottleBlock;
import com.github.ysbbbbbb.kaleidoscopetavern.block.dispenser.BottleBlockDispenseBehavior;
import com.github.ysbbbbbb.kaleidoscopetavern.game.tap.TapBehaviorManager;
import com.github.ysbbbbbb.kaleidoscopetavern.game.tap.impl.*;
import com.github.ysbbbbbb.kaleidoscopetavern.init.ModBlocks;
import com.github.ysbbbbbb.kaleidoscopetavern.item.BottleBlockItem;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.DispenserBlock;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent;

@EventBusSubscriber(bus = EventBusSubscriber.Bus.MOD, modid = KaleidoscopeTavern.MOD_ID)
public class CommonRegistry {
    @SubscribeEvent
    public static void onSetupEvent(FMLCommonSetupEvent event) {
        event.enqueueWork(CommonRegistry::addTapBehavior);
        event.enqueueWork(CommonRegistry::addDispenserBehavior);
    }

    private static void addTapBehavior() {
        TapBehaviorManager.register(ModBlocks.BARREL.get(), new BarrelTapBehavior());
        TapBehaviorManager.register(Blocks.WATER_CAULDRON, new WaterCauldronTapBehavior());
        TapBehaviorManager.register(Blocks.LAVA_CAULDRON, new LavaCauldronTapBehavior());
        TapBehaviorManager.register(Blocks.BEE_NEST, new BeehiveTapBehavior());
        TapBehaviorManager.register(Blocks.BEEHIVE, new BeehiveTapBehavior());
        TapBehaviorManager.register(Blocks.DRAGON_HEAD, new DragonHeadTapBehavior());
        TapBehaviorManager.register(Blocks.DRAGON_WALL_HEAD, new DragonHeadTapBehavior());
        TapBehaviorManager.register(Blocks.MELON, new WatermelonTapBehavior());
    }

    private static void addDispenserBehavior() {
        // 遍历物品列表，注册所有的 Bottle Block 子类方块
        BuiltInRegistries.BLOCK.forEach(block -> {
            if (block instanceof BottleBlock) {
                if (block.asItem() instanceof BottleBlockItem blockItem) {
                    DispenserBlock.registerBehavior(blockItem, new BottleBlockDispenseBehavior());
                }
            }
        });
    }
}
