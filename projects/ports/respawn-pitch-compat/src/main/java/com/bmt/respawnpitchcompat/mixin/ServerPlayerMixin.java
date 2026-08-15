package com.bmt.respawnpitchcompat.mixin;

import com.bmt.respawnpitchcompat.RespawnPitchAccess;
import net.minecraft.core.BlockPos;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.Tag;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Unit;
import net.minecraft.world.level.Level;
import com.mojang.datafixers.util.Either;
import org.objectweb.asm.Opcodes;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(ServerPlayer.class)
public abstract class ServerPlayerMixin implements RespawnPitchAccess {
    @Unique
    private static final String RESPAWN_PITCH_KEY = "respawn_pitch_compat:respawn_pitch";

    @Unique
    private float respawnPitchCompat$pitch;

    @Unique
    private boolean respawnPitchCompat$present;

    @Unique
    private long respawnPitchCompat$revision;

    @Unique
    private long respawnPitchCompat$copyRevision;

    @Unique
    private long respawnPitchCompat$sleepRevision;

    @Unique
    private float respawnPitchCompat$sleepPitch;

    @Inject(method = "readAdditionalSaveData", at = @At("TAIL"))
    private void respawnPitchCompat$load(CompoundTag tag, CallbackInfo callback) {
        ServerPlayer self = (ServerPlayer) (Object) this;
        if (self.getRespawnPosition() != null && tag.contains(RESPAWN_PITCH_KEY, Tag.TAG_ANY_NUMERIC)) {
            float stored = tag.getFloat(RESPAWN_PITCH_KEY);
            if (Float.isFinite(stored)) {
                this.respawnPitchCompat$pitch = stored;
                this.respawnPitchCompat$present = true;
                return;
            }
        }
        this.respawnPitchCompat$pitch = 0.0F;
        this.respawnPitchCompat$present = false;
    }

    @Inject(method = "addAdditionalSaveData", at = @At("TAIL"))
    private void respawnPitchCompat$save(CompoundTag tag, CallbackInfo callback) {
        ServerPlayer self = (ServerPlayer) (Object) this;
        if (self.getRespawnPosition() != null && this.respawnPitchCompat$present) {
            tag.putFloat(RESPAWN_PITCH_KEY, this.respawnPitchCompat$pitch);
        } else {
            tag.remove(RESPAWN_PITCH_KEY);
        }
    }

    @Inject(
            method = "setRespawnPosition",
            at = @At(
                    value = "FIELD",
                    target = "Lnet/minecraft/server/level/ServerPlayer;respawnForced:Z",
                    opcode = Opcodes.PUTFIELD,
                    shift = At.Shift.AFTER),
            require = 2)
    private void respawnPitchCompat$onVanillaSpawnSet(
            ResourceKey<Level> dimension,
            BlockPos pos,
            float yaw,
            boolean forced,
            boolean sendMessage,
            CallbackInfo callback) {
        this.respawnPitchCompat$pitch = 0.0F;
        this.respawnPitchCompat$present = pos != null;
        this.respawnPitchCompat$revision++;
    }

    @Inject(method = "startSleepInBed", at = @At("HEAD"))
    private void respawnPitchCompat$beforeSleep(
            BlockPos pos,
            CallbackInfoReturnable<Either<net.minecraft.world.entity.player.Player.BedSleepingProblem, Unit>> callback) {
        ServerPlayer self = (ServerPlayer) (Object) this;
        this.respawnPitchCompat$sleepRevision = this.respawnPitchCompat$revision;
        this.respawnPitchCompat$sleepPitch = self.getXRot();
    }

    @Inject(method = "startSleepInBed", at = @At("RETURN"))
    private void respawnPitchCompat$afterSleep(
            BlockPos pos,
            CallbackInfoReturnable<Either<net.minecraft.world.entity.player.Player.BedSleepingProblem, Unit>> callback) {
        if (this.respawnPitchCompat$revision != this.respawnPitchCompat$sleepRevision) {
            this.respawnPitchCompat$setPitch(this.respawnPitchCompat$sleepPitch, true);
        }
    }

    @Inject(method = "copyRespawnPosition", at = @At("HEAD"))
    private void respawnPitchCompat$beforeCopy(ServerPlayer source, CallbackInfo callback) {
        this.respawnPitchCompat$copyRevision = this.respawnPitchCompat$revision;
    }

    @Inject(method = "copyRespawnPosition", at = @At("TAIL"))
    private void respawnPitchCompat$afterCopy(ServerPlayer source, CallbackInfo callback) {
        if (this.respawnPitchCompat$revision != this.respawnPitchCompat$copyRevision) {
            RespawnPitchAccess sourceAccess = (RespawnPitchAccess) source;
            this.respawnPitchCompat$setPitch(
                    sourceAccess.respawnPitchCompat$getPitch(),
                    sourceAccess.respawnPitchCompat$hasPitch());
        }
    }

    @Override
    public float respawnPitchCompat$getPitch() {
        return this.respawnPitchCompat$pitch;
    }

    @Override
    public boolean respawnPitchCompat$hasPitch() {
        return this.respawnPitchCompat$present;
    }

    @Override
    public long respawnPitchCompat$getRevision() {
        return this.respawnPitchCompat$revision;
    }

    @Override
    public void respawnPitchCompat$setPitch(float pitch, boolean present) {
        this.respawnPitchCompat$pitch = pitch;
        this.respawnPitchCompat$present = present;
    }
}
