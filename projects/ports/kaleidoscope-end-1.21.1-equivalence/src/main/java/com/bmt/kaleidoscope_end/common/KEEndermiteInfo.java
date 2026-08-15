package com.bmt.kaleidoscope_end.common;

import com.bmt.kaleidoscope_end.api.IEndermiteExtension;
import java.util.List;
import java.util.Optional;
import javax.annotation.Nullable;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.MobSpawnType;
import net.minecraft.world.entity.monster.Endermite;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.neoforged.neoforge.common.util.INBTSerializable;

public class KEEndermiteInfo implements INBTSerializable<CompoundTag> {
    private final Endermite endermite;
    public boolean fed = false;
    public int inLove = 0;
    public int loveTime = 0;
    public int cooldown = 0;

    public KEEndermiteInfo(Endermite endermite) {
        this.endermite = endermite;
    }

    public boolean isInLove() {
        return this.inLove > 0;
    }

    @Override
    public CompoundTag serializeNBT(HolderLookup.Provider provider) {
        CompoundTag tag = new CompoundTag();
        tag.putBoolean("fed", this.fed);
        tag.putInt("inLove", this.inLove);
        tag.putInt("loveTime", this.loveTime);
        tag.putInt("cooldown", this.cooldown);
        return tag;
    }

    @Override
    public void deserializeNBT(HolderLookup.Provider provider, CompoundTag tag) {
        this.fed = tag.getBoolean("fed");
        this.inLove = tag.getInt("inLove");
        this.loveTime = tag.getInt("loveTime");
        this.cooldown = tag.getInt("cooldown");
    }

    public CompoundTag serializeNBT() {
        return this.serializeNBT(null);
    }

    public void deserializeNBT(CompoundTag tag) {
        this.deserializeNBT(null, tag);
    }

    public void aiStep() {
        if (!this.endermite.level().isClientSide) {
            if (this.isInLove()) {
                this.findValidBreedPartner(this.endermite).ifPresent(target -> {
                    this.endermite.getNavigation().moveTo(target, 1.0);
                    this.endermite.lookAt(target, 30.0F, 30.0F);
                    ++this.loveTime;
                    if (this.loveTime >= 60 && this.endermite.distanceToSqr(target) < 9.0) {
                        Entity child = this.endermite.getType().create(
                                (ServerLevel) this.endermite.level(),
                                null,
                                this.endermite.blockPosition(),
                                MobSpawnType.BREEDING,
                                false,
                                false);
                        if (child != null) {
                            child.setPos(this.endermite.getPosition(1.0F));
                            this.endermite.level().addFreshEntity(child);
                            KEEndermiteInfo partnerInfo = IEndermiteExtension.getInfo(target);
                            partnerInfo.cooldown = 6000;
                            partnerInfo.inLove = 0;
                            partnerInfo.loveTime = 0;
                            this.inLove = 0;
                            this.loveTime = 0;
                            this.cooldown = 6000;
                        }
                    }
                });
            }

            RandomSource random = this.endermite.getRandom();
            Level level = this.endermite.level();
            if (this.inLove > 0) {
                --this.inLove;
                if (this.inLove % 10 == 0) {
                    double x = random.nextGaussian() * 0.02;
                    double y = random.nextGaussian() * 0.02;
                    double z = random.nextGaussian() * 0.02;
                    level.addParticle(ParticleTypes.HEART,
                            this.endermite.getRandomX(1.0),
                            this.endermite.getRandomY() + 0.5,
                            this.endermite.getRandomZ(1.0), x, y, z);
                }
            }
        }
        this.cooldown = Math.max(0, this.cooldown - 1);
    }

    public void setInLove(@Nullable Player player) {
        if (this.cooldown <= 0) {
            this.inLove = 600;
            this.fed = true;
            this.burstLoveParticle(this.endermite);
            this.endermite.setPersistenceRequired();
        }
    }

    public void burstLoveParticle(Endermite endermite) {
        if (!endermite.level().isClientSide) {
            RandomSource random = endermite.getRandom();
            for (int i = 0; i < 7; ++i) {
                double x = random.nextGaussian() * 0.02;
                double y = random.nextGaussian() * 0.02;
                double z = random.nextGaussian() * 0.02;
                ((ServerLevel) endermite.level()).sendParticles(ParticleTypes.HEART,
                        endermite.getRandomX(1.0),
                        endermite.getRandomY() + 0.5,
                        endermite.getRandomZ(1.0), 1, x, y, z, 1.0);
            }
        }
    }

    private Optional<Endermite> findValidBreedPartner(Endermite endermite) {
        List<Endermite> nearby = endermite.level().getEntitiesOfClass(
                Endermite.class,
                endermite.getBoundingBox().inflate(8.0),
                other -> other != endermite && other.isAlive());
        return nearby.stream().filter(other -> IEndermiteExtension.getInfo(other).isInLove()).findFirst();
    }
}
