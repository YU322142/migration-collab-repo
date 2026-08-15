package net.immortaldevs.colorizer;

import com.mojang.logging.LogUtils;
import net.immortaldevs.colorizer.block.ColorizedBarrelBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.registries.DeferredBlock;
import net.neoforged.neoforge.registries.DeferredRegister;
import org.slf4j.Logger;

@Mod(value = ChestColorizer.MOD_ID, dist = Dist.CLIENT)
public final class ChestColorizer {
    public static final String MOD_ID = "colorizer";
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final DeferredRegister.Blocks BLOCKS = DeferredRegister.createBlocks(MOD_ID);
    public static final DeferredBlock<ColorizedBarrelBlock> BARREL_BLOCK = BLOCKS.register(
            "barrel",
            ignored -> new ColorizedBarrelBlock(BlockBehaviour.Properties.ofFullCopy(Blocks.BARREL))
    );

    public ChestColorizer(IEventBus modBus) {
        BLOCKS.register(modBus);
        ColorizerConfig.load();
        LOGGER.info("[Chest Colorizer] Native NeoForge 1.21.1 equivalence port loaded");
    }

    public static Block barrelBlock() {
        return BARREL_BLOCK.get();
    }
}
