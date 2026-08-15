package com.github.ysbbbbbb.kaleidoscopetavern.compat.jade;

import com.github.ysbbbbbb.kaleidoscopetavern.KaleidoscopeTavern;
import com.github.ysbbbbbb.kaleidoscopetavern.block.brew.BarrelBlock;
import com.github.ysbbbbbb.kaleidoscopetavern.block.brew.PressingTubBlock;
import com.github.ysbbbbbb.kaleidoscopetavern.blockentity.brew.PressingTubBlockEntity;
import com.github.ysbbbbbb.kaleidoscopetavern.compat.jade.block.BarrelComponentProvider;
import com.github.ysbbbbbb.kaleidoscopetavern.compat.jade.block.PressingTubComponentProvider;
import com.github.ysbbbbbb.kaleidoscopetavern.compat.jade.block.PressingTubDataProvider;
import com.github.ysbbbbbb.kaleidoscopetavern.init.ModBlocks;
import net.minecraft.resources.ResourceLocation;
import snownee.jade.api.IWailaClientRegistration;
import snownee.jade.api.IWailaCommonRegistration;
import snownee.jade.api.IWailaPlugin;
import snownee.jade.api.WailaPlugin;

@WailaPlugin
public class ModPlugin implements IWailaPlugin {
    public static final ResourceLocation BARREL = ResourceLocation.fromNamespaceAndPath(KaleidoscopeTavern.MOD_ID, "barrel");
    public static final ResourceLocation PRESSING_TUB = ResourceLocation.fromNamespaceAndPath(KaleidoscopeTavern.MOD_ID, "pressing_tub");

    @Override
    public void registerClient(IWailaClientRegistration registration) {
        registration.registerBlockComponent(BarrelComponentProvider.INSTANCE, BarrelBlock.class);
        registration.registerBlockComponent(PressingTubComponentProvider.INSTANCE, PressingTubBlock.class);
        registration.usePickedResult(ModBlocks.POTION_BOTTLE.get());
    }

    @Override
    public void register(IWailaCommonRegistration registration) {
        registration.registerBlockDataProvider(PressingTubDataProvider.INSTANCE, PressingTubBlockEntity.class);
    }
}
