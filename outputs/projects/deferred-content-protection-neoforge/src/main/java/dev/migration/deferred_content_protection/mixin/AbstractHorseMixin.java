package dev.migration.deferred_content_protection.mixin;

import dev.migration.deferred_content_protection.DeferredContentProtection;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.animal.horse.AbstractHorse;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(AbstractHorse.class)
public abstract class AbstractHorseMixin {
    @Inject(
            method = "equipBodyArmor(Lnet/minecraft/world/entity/player/Player;Lnet/minecraft/world/item/ItemStack;)V",
            at = @At("HEAD"),
            cancellable = true
    )
    private void deferredContentProtection$blockNewCarrierEquipment(
            Player player,
            ItemStack stack,
            CallbackInfo callback
    ) {
        if (DeferredContentProtection.isProtected(stack)) {
            callback.cancel();
            if (!player.level().isClientSide) {
                player.displayClientMessage(
                        Component.translatable("deferred_content_protection.blocked"),
                        true
                );
            }
        }
    }
}
