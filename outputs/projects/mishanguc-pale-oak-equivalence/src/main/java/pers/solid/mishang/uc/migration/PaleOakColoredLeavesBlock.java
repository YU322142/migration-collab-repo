package pers.solid.mishang.uc.migration;

import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ColorParticleOption;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.storage.loot.LootTable;
import net.minecraft.data.loot.BlockLootSubProvider;
import org.jetbrains.annotations.Nullable;
import pers.solid.mishang.uc.block.ColoredLeavesBlock;
import pers.solid.mishang.uc.blockentity.ColoredBlockEntity;

import java.util.function.BiFunction;

public final class PaleOakColoredLeavesBlock extends ColoredLeavesBlock {
    private static final float LEAF_PARTICLE_CHANCE = 0.02F;

    public PaleOakColoredLeavesBlock(
            BlockBehaviour.Properties properties,
            @Nullable BiFunction<Block, BlockLootSubProvider, LootTable.Builder> lootBuilder,
            String texture) {
        super(properties, lootBuilder, texture);
    }

    @Override
    public void animateTick(BlockState state, Level level, BlockPos pos, RandomSource random) {
        super.animateTick(state, level, pos, random);
        if (random.nextFloat() >= LEAF_PARTICLE_CHANCE) {
            return;
        }
        BlockPos below = pos.below();
        if (level.getBlockState(below).isCollisionShapeFullBlock(level, below)) {
            return;
        }
        BlockEntity entity = level.getBlockEntity(pos);
        int color = entity instanceof ColoredBlockEntity colored ? colored.getColor() : 0xffffff;
        ColorParticleOption particle = ColorParticleOption.create(
                MishangPaleOakParticles.TINTED_LEAVES.get(), 0xff000000 | color);
        level.addParticle(particle,
                pos.getX() + random.nextDouble(), pos.getY() - 0.05, pos.getZ() + random.nextDouble(),
                0.0, 0.0, 0.0);
    }
}
