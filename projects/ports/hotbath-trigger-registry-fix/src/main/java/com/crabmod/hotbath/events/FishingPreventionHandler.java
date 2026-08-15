package com.crabmod.hotbath.events;

import com.crabmod.hotbath.HotBath;
import com.crabmod.hotbath.fluid_blocks.AbstractHotbathBlock;
import net.minecraft.core.BlockPos;
import net.minecraft.world.item.FishingRodItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.entity.player.ItemFishedEvent;
import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;

@EventBusSubscriber(modid = HotBath.MOD_ID)
public class FishingPreventionHandler {

    private static BlockPos lastFishingRodPosition = null;

    @SubscribeEvent
    public static void onPlayerRightClickItem(PlayerInteractEvent.RightClickItem event) {
        ItemStack itemStack = event.getItemStack();

        // Check if the player is using a fishing rod
        if (itemStack.getItem() instanceof FishingRodItem) {
            HitResult rayTraceResult = event.getEntity().pick(5.0D, 1.0F, true);
            Level world = event.getLevel();

            // Check if the ray trace hits a block
            if (rayTraceResult.getType() == HitResult.Type.BLOCK) {
                Vec3 hitVec = rayTraceResult.getLocation();
                lastFishingRodPosition =
                        new BlockPos(
                                (int) Math.round(hitVec.x), (int) Math.round(hitVec.y), (int) Math.round(hitVec.z));
            }
        }
    }

    @SubscribeEvent
    public static void onItemFished(ItemFishedEvent event) {
        if (lastFishingRodPosition != null) {
            Level world = event.getEntity().getCommandSenderWorld();
            boolean isHotBathBlock =
                    world.getBlockState(lastFishingRodPosition).getBlock() instanceof AbstractHotbathBlock;

            // If the fishing rod is in a HotBath block, cancel the fishing event
            if (isHotBathBlock) {
                event.setCanceled(true);
            }
        }
    }
}
