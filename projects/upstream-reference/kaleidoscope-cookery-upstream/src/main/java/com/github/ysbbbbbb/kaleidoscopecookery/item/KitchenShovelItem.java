package com.github.ysbbbbbb.kaleidoscopecookery.item;

import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
import com.github.ysbbbbbb.kaleidoscopecookery.blockentity.kitchen.PotBlockEntity;
import net.minecraft.ChatFormatting;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.ShovelItem;
import net.minecraft.world.item.Tiers;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.item.context.UseOnContext;
import net.minecraft.world.level.Level;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;

import javax.annotation.Nullable;
import java.util.List;

public class KitchenShovelItem extends ShovelItem {
    public static final ResourceLocation HAS_OIL_PROPERTY = new ResourceLocation(KaleidoscopeCookery.MOD_ID, "has_oil");
    private static final int NO_OIL = 0;
    private static final int HAS_OIL = 1;

    public KitchenShovelItem() {
        super(Tiers.IRON, -1, -2.0F, new Properties());
    }

    public static void setHasOil(ItemStack stack, boolean hasOil) {
        CompoundTag tag = stack.getOrCreateTag();
        tag.putBoolean("hasOil", hasOil);
    }

    public static boolean hasOil(ItemStack stack) {
        CompoundTag tag = stack.getTag();
        return tag != null && tag.getBoolean("hasOil");
    }

    @OnlyIn(Dist.CLIENT)
    public static float getTexture(ItemStack stack, @Nullable ClientLevel level, @Nullable LivingEntity entity, int seed) {
        if (hasOil(stack)) {
            return HAS_OIL;
        }
        return NO_OIL;
    }

    @Override
    public InteractionResult useOn(UseOnContext context) {
        InteractionResult result = super.useOn(context);
        if (result.shouldAwardStats() && hasOil(context.getItemInHand())) {
            setHasOil(context.getItemInHand(), false);
        }
        return result;
    }

    @Override
    public InteractionResult onItemUseFirst(ItemStack stack, UseOnContext context) {
        BlockPos clickedPos = context.getClickedPos();
        Level level = context.getLevel();
        Player player = context.getPlayer();
        if (level.getBlockEntity(clickedPos) instanceof PotBlockEntity potBlockEntity
            && player != null && player.isSecondaryUseActive()
            && potBlockEntity.getStatus() == PotBlockEntity.FINISHED
            && !potBlockEntity.hasCarrier()) {
            potBlockEntity.takeOutProduct(level, player, stack);
            return InteractionResult.SUCCESS;
        }
        return super.onItemUseFirst(stack, context);
    }

    @Override
    public void appendHoverText(ItemStack stack, @org.jetbrains.annotations.Nullable Level level, List<Component> tooltip, TooltipFlag flag) {
        tooltip.add(Component.translatable("tooltip.kaleidoscope_cookery.kitchen_shovel").withStyle(ChatFormatting.GRAY));
    }
}
