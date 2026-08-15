package com.blackgear.vanillabackport.core.mixin.common;

import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.ZombieNautilus;
import com.blackgear.vanillabackport.common.registries.entities.ModEntityTypes;
import net.minecraft.tags.BiomeTags;
import net.minecraft.world.DifficultyInstance;
import net.minecraft.world.entity.MobSpawnType;
import net.minecraft.world.entity.SpawnGroupData;
import net.minecraft.world.entity.monster.Drowned;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.ServerLevelAccessor;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(Drowned.class)
public class DrownedMixin {
    @Inject(method = "finalizeSpawn", at = @At("RETURN"))
    private void nautilusEquivalence$spawnZombieNautilusJockey(
        ServerLevelAccessor level,
        DifficultyInstance difficulty,
        MobSpawnType spawnType,
        SpawnGroupData spawnData,
        CallbackInfoReturnable<SpawnGroupData> cir
    ) {
        Drowned drowned = (Drowned) (Object) this;
        if ((spawnType != MobSpawnType.NATURAL && spawnType != MobSpawnType.STRUCTURE)
            || !drowned.getMainHandItem().is(Items.TRIDENT)
            || level.getRandom().nextFloat() >= 0.5F
            || drowned.isBaby()
            || level.getBiome(drowned.blockPosition()).is(BiomeTags.MORE_FREQUENT_DROWNED_SPAWNS)) {
            return;
        }

        ZombieNautilus mount = ModEntityTypes.ZOMBIE_NAUTILUS.get().create(drowned.level());
        if (mount == null) {
            return;
        }
        if (spawnType == MobSpawnType.STRUCTURE) {
            mount.setPersistenceRequired();
        }
        mount.moveTo(drowned.getX(), drowned.getY(), drowned.getZ(), drowned.getYRot(), 0.0F);
        mount.finalizeSpawn(level, difficulty, MobSpawnType.JOCKEY, null);
        drowned.startRiding(mount, false);
        level.addFreshEntity(mount);
    }
}
