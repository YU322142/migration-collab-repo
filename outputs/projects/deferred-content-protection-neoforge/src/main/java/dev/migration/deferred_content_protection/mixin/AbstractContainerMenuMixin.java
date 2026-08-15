package dev.migration.deferred_content_protection.mixin;

import dev.migration.deferred_content_protection.DeferredContentProtection;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.AbstractFurnaceMenu;
import net.minecraft.world.inventory.AnvilMenu;
import net.minecraft.world.inventory.BeaconMenu;
import net.minecraft.world.inventory.BrewingStandMenu;
import net.minecraft.world.inventory.CartographyTableMenu;
import net.minecraft.world.inventory.ClickType;
import net.minecraft.world.inventory.CrafterMenu;
import net.minecraft.world.inventory.CraftingMenu;
import net.minecraft.world.inventory.GrindstoneMenu;
import net.minecraft.world.inventory.HorseInventoryMenu;
import net.minecraft.world.inventory.InventoryMenu;
import net.minecraft.world.inventory.LoomMenu;
import net.minecraft.world.inventory.MerchantMenu;
import net.minecraft.world.inventory.SmithingMenu;
import net.minecraft.world.inventory.StonecutterMenu;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(AbstractContainerMenu.class)
public abstract class AbstractContainerMenuMixin {
    @Inject(method = "clicked", at = @At("HEAD"), cancellable = true)
    private void deferredContentProtection$blockLossyClick(
            int slotId,
            int button,
            ClickType clickType,
            Player player,
            CallbackInfo callback
    ) {
        AbstractContainerMenu menu = (AbstractContainerMenu) (Object) this;
        ItemStack carried = menu.getCarried();
        ItemStack clicked = slotId >= 0 && slotId < menu.slots.size()
                ? menu.slots.get(slotId).getItem()
                : ItemStack.EMPTY;
        ItemStack swapped = clickType == ClickType.SWAP && (button >= 0 && button < 9 || button == 40)
                ? player.getInventory().getItem(button)
                : ItemStack.EMPTY;

        boolean protectedHorseSlot = menu instanceof HorseInventoryMenu
                && (
                    slotId == 1 && touchesProtectedStack(clickType, clicked, carried, swapped)
                    || clickType == ClickType.QUICK_MOVE && DeferredContentProtection.isProtected(clicked)
                );
        boolean throwOrClone = (clickType == ClickType.THROW || clickType == ClickType.CLONE)
                && (DeferredContentProtection.isProtected(clicked)
                    || DeferredContentProtection.isProtected(carried));
        boolean outsideDrop = slotId == AbstractContainerMenu.SLOT_CLICKED_OUTSIDE
                && DeferredContentProtection.isProtected(carried);
        boolean protectedDrag = clickType == ClickType.QUICK_CRAFT
                && DeferredContentProtection.isProtected(carried);
        boolean pickupAllSweep = clickType == ClickType.PICKUP_ALL
                && (
                    DeferredContentProtection.isProtected(carried)
                    || menu.slots.stream().anyMatch(slot ->
                            DeferredContentProtection.isProtected(slot.getItem()))
                );
        boolean processingTouch = isProcessingMenu(menu)
                && (
                    isProcessingSlot(menu, slotId)
                            && touchesProtectedStack(clickType, clicked, carried, swapped)
                    || clickType == ClickType.QUICK_MOVE
                            && DeferredContentProtection.isProtected(clicked)
                );
        boolean protectedDangerousClick = throwOrClone
                || outsideDrop
                || protectedDrag
                || pickupAllSweep
                || processingTouch;

        if (protectedHorseSlot || protectedDangerousClick) {
            callback.cancel();
            if (!player.level().isClientSide) {
                player.displayClientMessage(
                        Component.translatable("deferred_content_protection.blocked"),
                        true
                );
                menu.broadcastFullState();
            }
        }
    }

    private static boolean touchesProtectedStack(
            ClickType clickType,
            ItemStack clicked,
            ItemStack carried,
            ItemStack swapped
    ) {
        return DeferredContentProtection.isProtected(clicked)
                || DeferredContentProtection.isProtected(carried)
                || (clickType == ClickType.SWAP && DeferredContentProtection.isProtected(swapped));
    }

    private static boolean isProcessingMenu(AbstractContainerMenu menu) {
        return menu instanceof InventoryMenu
                || menu instanceof CraftingMenu
                || menu instanceof CrafterMenu
                || menu instanceof AbstractFurnaceMenu
                || menu instanceof BrewingStandMenu
                || menu instanceof AnvilMenu
                || menu instanceof GrindstoneMenu
                || menu instanceof SmithingMenu
                || menu instanceof StonecutterMenu
                || menu instanceof CartographyTableMenu
                || menu instanceof LoomMenu
                || menu instanceof BeaconMenu
                || menu instanceof MerchantMenu;
    }

    private static boolean isProcessingSlot(AbstractContainerMenu menu, int slotId) {
        if (slotId < 0) {
            return false;
        }
        if (menu instanceof InventoryMenu) {
            return slotId >= 0 && slotId < 9;
        }
        if (menu instanceof CraftingMenu) {
            return slotId >= 0 && slotId < 10;
        }
        if (menu instanceof CrafterMenu) {
            return slotId >= 0 && slotId < 9 || slotId == 45;
        }
        if (menu instanceof AbstractFurnaceMenu) {
            return slotId < 3;
        }
        if (menu instanceof BrewingStandMenu) {
            return slotId < 5;
        }
        if (menu instanceof AnvilMenu || menu instanceof GrindstoneMenu) {
            return slotId < 3;
        }
        if (menu instanceof SmithingMenu) {
            return slotId < 4;
        }
        if (menu instanceof StonecutterMenu) {
            return slotId < 2;
        }
        if (menu instanceof CartographyTableMenu) {
            return slotId < 3;
        }
        if (menu instanceof LoomMenu) {
            return slotId < 4;
        }
        if (menu instanceof BeaconMenu) {
            return slotId == 0;
        }
        return menu instanceof MerchantMenu && slotId < 3;
    }
}
