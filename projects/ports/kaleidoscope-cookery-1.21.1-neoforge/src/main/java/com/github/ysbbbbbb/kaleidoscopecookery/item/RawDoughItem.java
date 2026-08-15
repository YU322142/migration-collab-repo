package com.github.ysbbbbbb.kaleidoscopecookery.item;

import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
import com.github.ysbbbbbb.kaleidoscopecookery.advancements.critereon.ModEventTriggerType;
import com.github.ysbbbbbb.kaleidoscopecookery.init.ModItems;
import com.github.ysbbbbbb.kaleidoscopecookery.init.ModSounds;
import com.github.ysbbbbbb.kaleidoscopecookery.init.ModTrigger;
import com.github.ysbbbbbb.kaleidoscopecookery.util.ItemUtils;
import net.minecraft.ChatFormatting;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.item.UseAnim;
import net.minecraft.world.level.Level;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.api.distmarker.OnlyIn;

import javax.annotation.Nullable;
import java.util.List;

public class RawDoughItem extends Item {
    public static final ResourceLocation PULL_PROPERTY = ResourceLocation.fromNamespaceAndPath(KaleidoscopeCookery.MOD_ID, "pull");
    private static final int MIN_USE_DURATION = 30;

    public RawDoughItem() {
        super(new Properties());
    }

    @OnlyIn(Dist.CLIENT)
    public static float getTexture(ItemStack stack, @Nullable ClientLevel level, @Nullable LivingEntity entity, int seed) {
        if (entity == null) {
            return 0;
        }
        if (entity.getUseItem() != stack) {
            return 0;
        }
        return entity.getTicksUsingItem() / 10F;
    }

    @Override
    public int getUseDuration(ItemStack stack, LivingEntity entity) {
        return 72000;
    }

    @Override
    public UseAnim getUseAnimation(ItemStack pStack) {
        return UseAnim.BOW;
    }

    @Override
    public InteractionResultHolder<ItemStack> use(Level worldIn, Player playerIn, InteractionHand handIn) {
        ItemStack stack = playerIn.getItemInHand(handIn);
        playerIn.startUsingItem(handIn);
        return InteractionResultHolder.consume(stack);
    }

    @Override
    public void releaseUsing(ItemStack stack, Level worldIn, LivingEntity entityLiving, int timeLeft) {
        int time = stack.getUseDuration(entityLiving) - timeLeft;
        if (time >= MIN_USE_DURATION) {
            int count = stack.getCount();
            ItemStack noodles = new ItemStack(ModItems.RAW_NOODLES.get(), count);
            stack.setCount(0);
            ItemUtils.getItemToLivingEntity(entityLiving, noodles);
            if (worldIn.isClientSide()) {
                entityLiving.playSound(ModSounds.ITEM_DOUGH_TRANSFORM.get(), 1.0F, 1.0F);
            }
            if (entityLiving instanceof ServerPlayer serverPlayer) {
                ModTrigger.EVENT.get().trigger(serverPlayer, ModEventTriggerType.PULL_THE_DOUGH);
            }
        }
    }

    @Override
    public void appendHoverText(ItemStack stack, TooltipContext context, List<Component> tooltip, TooltipFlag flag) {
        tooltip.add(Component.translatable("tooltip.kaleidoscope_cookery.raw_dough").withStyle(ChatFormatting.GRAY));
    }
}
