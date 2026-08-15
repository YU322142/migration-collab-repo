package org.xiyu.yee.xiyuslogin.mixin;

import net.minecraft.network.protocol.game.ServerboundContainerButtonClickPacket;
import net.minecraft.network.protocol.game.ServerboundContainerClickPacket;
import net.minecraft.network.protocol.game.ServerboundAcceptTeleportationPacket;
import net.minecraft.network.protocol.game.ServerboundMovePlayerPacket;
import net.minecraft.network.protocol.game.ServerboundPickItemPacket;
import net.minecraft.network.protocol.game.ServerboundPlayerActionPacket;
import net.minecraft.network.protocol.game.ServerboundSetCarriedItemPacket;
import net.minecraft.network.protocol.game.ServerboundSetCreativeModeSlotPacket;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginConfig;
import org.xiyu.yee.xiyuslogin.manager.AuthManager;
import org.xiyu.yee.xiyuslogin.manager.FreezeManager;

@Mixin(ServerGamePacketListenerImpl.class)
public abstract class ServerGamePacketListenerImplMixin {
    @Shadow
    public ServerPlayer player;

    @Shadow
    private boolean clientIsFloating;

    @Shadow
    private int aboveGroundTickCount;

    @Shadow
    private boolean clientVehicleIsFloating;

    @Shadow
    private int aboveGroundVehicleTickCount;

    @Inject(method = "tick", at = @At("HEAD"))
    private void xiyuslogin$legalizeUnauthenticatedFloating(CallbackInfo ci) {
        if (isUnauthenticated() && XiyusLoginConfig.LEGALIZE_UNAUTHENTICATED_FLOATING.get()) {
            clientIsFloating = false;
            aboveGroundTickCount = 0;
            clientVehicleIsFloating = false;
            aboveGroundVehicleTickCount = 0;
            player.resetFallDistance();
        }
    }

    @Inject(method = "handleContainerClick", at = @At("HEAD"), cancellable = true)
    private void xiyuslogin$blockContainerClick(ServerboundContainerClickPacket packet, CallbackInfo ci) {
        blockInventoryMutation(ci);
    }

    @Inject(method = "handleSetCreativeModeSlot", at = @At("HEAD"), cancellable = true)
    private void xiyuslogin$blockCreativeSlot(ServerboundSetCreativeModeSlotPacket packet, CallbackInfo ci) {
        blockInventoryMutation(ci);
    }

    @Inject(method = "handleContainerButtonClick", at = @At("HEAD"), cancellable = true)
    private void xiyuslogin$blockContainerButton(ServerboundContainerButtonClickPacket packet, CallbackInfo ci) {
        blockInventoryMutation(ci);
    }

    @Inject(method = "handlePickItem", at = @At("HEAD"), cancellable = true)
    private void xiyuslogin$blockPickItem(ServerboundPickItemPacket packet, CallbackInfo ci) {
        blockInventoryMutation(ci);
    }

    @Inject(method = "handleSetCarriedItem", at = @At("HEAD"), cancellable = true)
    private void xiyuslogin$blockSetCarriedItem(ServerboundSetCarriedItemPacket packet, CallbackInfo ci) {
        blockInventoryMutation(ci);
    }

    @Inject(method = "handlePlayerAction", at = @At("HEAD"), cancellable = true)
    private void xiyuslogin$blockInventoryActions(ServerboundPlayerActionPacket packet, CallbackInfo ci) {
        if (packet.getAction() == ServerboundPlayerActionPacket.Action.DROP_ITEM
                || packet.getAction() == ServerboundPlayerActionPacket.Action.DROP_ALL_ITEMS
                || packet.getAction() == ServerboundPlayerActionPacket.Action.SWAP_ITEM_WITH_OFFHAND) {
            blockInventoryMutation(ci);
        }
    }

    @Inject(method = "handleAcceptTeleportPacket", at = @At("HEAD"), cancellable = true)
    private void xiyuslogin$blockFakeTeleportAck(ServerboundAcceptTeleportationPacket packet, CallbackInfo ci) {
        if (isUnauthenticated()) {
            ci.cancel();
        }
    }

    @Inject(method = "handleMovePlayer", at = @At("HEAD"), cancellable = true)
    private void xiyuslogin$blockFakePositionMovement(ServerboundMovePlayerPacket packet, CallbackInfo ci) {
        if (isUnauthenticated()) {
            ci.cancel();
        }
    }

    private void blockInventoryMutation(CallbackInfo ci) {
        if (isUnauthenticated()) {
            FreezeManager.getInstance().syncFrozenInventoryView(player);
            ci.cancel();
        }
    }

    private boolean isUnauthenticated() {
        return player != null && !AuthManager.getInstance().isAuthenticated(player.getUUID());
    }
}
