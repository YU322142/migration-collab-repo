package com.bmt.kaleidoscope_end.item;

import com.bmt.kaleidoscope_end.common.DragonBreathCloudService;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.Tag;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.AreaEffectCloud;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.component.CustomData;
import net.minecraft.world.item.context.UseOnContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

public class DragonBreathBucket extends Item {
    public DragonBreathBucket(Properties properties) {
        super(properties.stacksTo(1));
    }

    @Override
    public InteractionResult useOn(UseOnContext context) {
        Level level = context.getLevel();
        if (level.isClientSide) {
            return InteractionResult.SUCCESS;
        }

        Vec3 clickLocation = context.getClickLocation();
        AreaEffectCloud cloud = new AreaEffectCloud(
                level, clickLocation.x(), clickLocation.y(), clickLocation.z());
        cloud.setParticle(ParticleTypes.DRAGON_BREATH);
        float radius = 3.0F;
        CustomData customData = context.getItemInHand().get(DataComponents.CUSTOM_DATA);
        if (customData != null) {
            CompoundTag tag = customData.copyTag();
            if (tag.contains("radius", Tag.TAG_ANY_NUMERIC)) {
                radius = tag.getFloat("radius");
            }
        }

        cloud.setRadius(radius);
        cloud.setDuration(600);
        cloud.setRadiusPerTick((7.0F - cloud.getRadius()) / cloud.getDuration());
        cloud.addEffect(new MobEffectInstance(MobEffects.HARM, 1, 1));
        DragonBreathCloudService.markBucketPlaced(cloud);
        Player player = context.getPlayer();
        if (player != null) {
            cloud.setOwner(player);
        }
        if (!level.addFreshEntity(cloud)) {
            return InteractionResult.FAIL;
        }

        if (player != null && !player.getAbilities().instabuild) {
            ItemStack itemInHand = context.getItemInHand();
            itemInHand.shrink(1);
            if (itemInHand.isEmpty()) {
                player.setItemInHand(context.getHand(), Items.BUCKET.getDefaultInstance());
            } else if (!player.getInventory().add(Items.BUCKET.getDefaultInstance())) {
                player.drop(Items.BUCKET.getDefaultInstance(), false);
            }
        }
        level.playSound(null, clickLocation.x(), clickLocation.y(), clickLocation.z(),
                SoundEvents.BUCKET_EMPTY, SoundSource.NEUTRAL, 1.0F, 1.0F);
        return InteractionResult.SUCCESS;
    }
}
