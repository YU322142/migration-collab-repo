package pers.solid.mishang.uc.migration.client;

import net.minecraft.Util;
import net.minecraft.client.renderer.ItemBlockRenderTypes;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.fml.event.lifecycle.FMLClientSetupEvent;
import net.neoforged.neoforge.client.event.RegisterColorHandlersEvent;
import net.neoforged.neoforge.client.event.RegisterParticleProvidersEvent;
import pers.solid.mishang.uc.blockentity.ColoredBlockEntity;
import pers.solid.mishang.uc.components.MishangucComponents;
import pers.solid.mishang.uc.migration.MishangPaleOakContent;
import pers.solid.mishang.uc.migration.MishangPaleOakEquivalence;
import pers.solid.mishang.uc.migration.MishangPaleOakParticles;

import java.awt.Color;

@EventBusSubscriber(
        modid = MishangPaleOakEquivalence.MOD_ID,
        bus = EventBusSubscriber.Bus.MOD,
        value = Dist.CLIENT)
public final class MishangPaleOakClientEvents {
    private MishangPaleOakClientEvents() {
    }

    @SubscribeEvent
    public static void clientSetup(FMLClientSetupEvent event) {
        event.enqueueWork(() -> MishangPaleOakContent.translucentBlocks().forEach(holder ->
                ItemBlockRenderTypes.setRenderLayer(holder.get(), RenderType.translucent())));
    }

    @SubscribeEvent
    public static void registerBlockColors(RegisterColorHandlersEvent.Block event) {
        Block[] blocks = MishangPaleOakContent.coloredBlocks().stream()
                .map(holder -> (Block) holder.get())
                .toArray(Block[]::new);
        event.register((state, world, pos, tintIndex) -> {
            if (world == null || pos == null) {
                return -1;
            }
            BlockEntity entity = world.getBlockEntity(pos);
            if (entity == null) {
                entity = world.getBlockEntity(pos.below());
            }
            if (entity instanceof ColoredBlockEntity colored) {
                return colored.getColor();
            }
            int count = 0;
            int red = 0;
            int green = 0;
            int blue = 0;
            for (BlockPos nearby : BlockPos.withinManhattan(pos, 1, 1, 1)) {
                if (nearby.equals(pos)) {
                    continue;
                }
                BlockEntity nearbyEntity = world.getBlockEntity(nearby);
                if (nearbyEntity instanceof ColoredBlockEntity colored) {
                    int color = colored.getColor();
                    count++;
                    red += color >> 16 & 0xff;
                    green += color >> 8 & 0xff;
                    blue += color & 0xff;
                }
            }
            return count == 0 ? -1 : (red / count << 16) | (green / count << 8) | blue / count;
        }, blocks);
    }

    @SubscribeEvent
    public static void registerItemColors(RegisterColorHandlersEvent.Item event) {
        event.register((stack, tintIndex) -> {
            Integer color = stack.get(MishangucComponents.COLOR);
            if (color != null) {
                return 0xff000000 | color;
            }
            return Color.HSBtoRGB((float) Util.getMillis() / 4096.0F
                    + (float) (stack.getItem().hashCode() >> 16) / 64.0F, 0.5F, 0.95F);
        }, MishangPaleOakContent.COLORED_PALE_OAK_LEAVES.get().asItem(),
                MishangPaleOakContent.COLORED_DECORATED_PALE_OAK.base().get().asItem(),
                MishangPaleOakContent.COLORED_DECORATED_STRIPPED_PALE_OAK.base().get().asItem());
    }

    @SubscribeEvent
    public static void registerParticleProviders(RegisterParticleProvidersEvent event) {
        event.registerSpriteSet(MishangPaleOakParticles.TINTED_LEAVES.get(),
                TintedLeavesParticle.Provider::new);
    }
}
