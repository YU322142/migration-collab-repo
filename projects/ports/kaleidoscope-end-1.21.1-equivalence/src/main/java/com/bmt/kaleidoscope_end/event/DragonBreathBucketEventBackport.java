package com.bmt.kaleidoscope_end.event;

import com.bmt.kaleidoscope_end.common.DragonBreathCloudService;
import com.bmt.kaleidoscope_end.init.KEItem;
import java.util.List;
import net.minecraft.core.component.DataComponents;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.AreaEffectCloud;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.component.CustomData;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.gameevent.GameEvent;
import net.neoforged.bus.api.EventPriority;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;

@EventBusSubscriber(modid = "kaleidoscope_end")
public final class DragonBreathBucketEventBackport {
    private DragonBreathBucketEventBackport() {
    }

    @SubscribeEvent(priority = EventPriority.HIGHEST)
    public static void onRightClickItem(PlayerInteractEvent.RightClickItem event) {
        if (!event.getItemStack().is(Items.BUCKET)) {
            return;
        }
        Player player = event.getEntity();
        Level level = player.level();
        List<AreaEffectCloud> clouds = level.getEntitiesOfClass(
                AreaEffectCloud.class,
                player.getBoundingBox().inflate(2.0),
                DragonBreathCloudService::isBucketPlaced);
        if (clouds.isEmpty()) {
            return;
        }

        AreaEffectCloud cloud = clouds.getFirst();
        float radius = cloud.getRadius();
        cloud.kill();
        level.playSound(null, player.getX(), player.getY(), player.getZ(),
                SoundEvents.BUCKET_FILL, SoundSource.NEUTRAL, 1.0F, 1.0F);
        level.gameEvent(player, GameEvent.FLUID_PICKUP, player.position());
        ItemStack filledBucket = KEItem.DRAGON_BREATH_BUCKET_ITEM.get().getDefaultInstance();
        CompoundTag tag = new CompoundTag();
        tag.putFloat("radius", radius);
        filledBucket.set(DataComponents.CUSTOM_DATA, CustomData.of(tag));
        ItemStack emptyBucket = event.getItemStack();
        emptyBucket.shrink(1);
        if (emptyBucket.isEmpty()) {
            player.setItemInHand(event.getHand(), filledBucket);
        } else if (!player.getInventory().add(filledBucket)) {
            player.drop(filledBucket, false);
        }
        event.setCancellationResult(InteractionResult.sidedSuccess(level.isClientSide));
        event.setCanceled(true);
    }
}
