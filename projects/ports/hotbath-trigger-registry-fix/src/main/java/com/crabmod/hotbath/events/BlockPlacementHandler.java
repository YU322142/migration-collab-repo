package com.crabmod.hotbath.events;

import com.crabmod.hotbath.fluid_blocks.AbstractHotbathBlock;
import net.minecraft.core.BlockPos;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.SimpleWaterloggedBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.material.FluidState;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;

import static com.crabmod.hotbath.HotBath.MOD_ID;

@EventBusSubscriber(modid = MOD_ID)
public class BlockPlacementHandler {

    @SubscribeEvent
    public static void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {
        Level world = event.getLevel();
        BlockPos pos = event.getPos();
        boolean isHotBathBlock = world.getBlockState(pos).getBlock() instanceof AbstractHotbathBlock;

        if (isHotBathBlock) {
            Item heldItem = event.getItemStack().getItem();
            if (heldItem instanceof BlockItem blockItem) {
                Block heldBlock = blockItem.getBlock();

                // Check if the held block can be waterlogged
                if (heldBlock instanceof SimpleWaterloggedBlock) {
                    // Cancel the original block placement event
                    event.setCanceled(true);

                    // Get the HotBath FluidState
                    FluidState hotBathFluidState = world.getFluidState(pos);

                    // Create a new block state with the waterlogged property set to true
                    BlockState waterloggedState =
                            heldBlock.defaultBlockState().setValue(BlockStateProperties.WATERLOGGED, true);

                    // Set the new block state in the world
                    world.setBlock(pos, waterloggedState, 3);

                    // Manually fill the block with your HotBath fluid
                    world.setBlock(pos, waterloggedState.setValue(BlockStateProperties.WATERLOGGED, true), 3);

                    // Consume the held item
                    if (!event.getEntity().isCreative()) {
                        event.getItemStack().shrink(1);
                    }
                }
            }
        }
    }
}
