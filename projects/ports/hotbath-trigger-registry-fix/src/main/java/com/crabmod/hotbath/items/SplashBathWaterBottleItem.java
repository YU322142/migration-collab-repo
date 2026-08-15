package com.crabmod.hotbath.items;

import net.minecraft.ChatFormatting;
import net.minecraft.core.particles.SimpleParticleType;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.stats.Stats;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.level.Level;
import org.jetbrains.annotations.NotNull;

import java.util.List;
import java.util.function.Consumer;
import java.util.function.Supplier;

public class SplashBathWaterBottleItem extends Item {
    private final Consumer<LivingEntity> drinkEffect;
    private final Supplier<SimpleParticleType> particleType;
    private final Supplier<SimpleParticleType> bubbleParticleType;
    private final Supplier<SimpleParticleType> effectParticleType;
    private final int color;

    public SplashBathWaterBottleItem(Properties properties, Consumer<LivingEntity> drinkEffect, Supplier<SimpleParticleType> particleType, Supplier<SimpleParticleType> bubbleParticleType, Supplier<SimpleParticleType> effectParticleType, int color) {
        super(properties);
        this.drinkEffect = drinkEffect;
        this.particleType = particleType;
        this.bubbleParticleType = bubbleParticleType;
        this.effectParticleType = effectParticleType;
        this.color = color;
    }

    public int getColor() {
        return color;
    }

    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack itemstack = player.getItemInHand(hand);
        level.playSound(null, player.getX(), player.getY(), player.getZ(), 
                net.minecraft.sounds.SoundEvents.SPLASH_POTION_THROW, 
                net.minecraft.sounds.SoundSource.PLAYERS, 0.5F, 
                0.4F / (level.getRandom().nextFloat() * 0.4F + 0.8F));
        
        if (!level.isClientSide) {
            ThrownBathWater thrownBathWater = new ThrownBathWater(level, player);
            thrownBathWater.setItem(itemstack);
            thrownBathWater.shootFromRotation(player, player.getXRot(), player.getYRot(), -20.0F, 0.5F, 1.0F);
            level.addFreshEntity(thrownBathWater);
        }

        player.awardStat(Stats.ITEM_USED.get(this));
        if (!player.getAbilities().instabuild) {
            itemstack.shrink(1);
        }

        return InteractionResultHolder.sidedSuccess(itemstack, level.isClientSide());
    }

    public void applyEffect(LivingEntity entity) {
        if (drinkEffect != null) {
            drinkEffect.accept(entity);
        }
    }

    public SimpleParticleType getParticleType() {
        return particleType.get();
    }

    public SimpleParticleType getBubbleParticleType() {
        return bubbleParticleType.get();
    }

    public SimpleParticleType getEffectParticleType() {
        return effectParticleType.get();
    }

    @Override
    public void appendHoverText(@NotNull ItemStack stack, @NotNull TooltipContext context, @NotNull List<Component> tooltipComponents, @NotNull TooltipFlag tooltipFlag) {
        super.appendHoverText(stack, context, tooltipComponents, tooltipFlag);
        tooltipComponents.add(Component.translatable(this.getDescriptionId() + ".desc").withStyle(ChatFormatting.GRAY, ChatFormatting.ITALIC));
    }
}
