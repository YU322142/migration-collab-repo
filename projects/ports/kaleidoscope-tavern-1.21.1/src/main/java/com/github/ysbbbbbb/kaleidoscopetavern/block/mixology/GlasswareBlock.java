package com.github.ysbbbbbb.kaleidoscopetavern.block.mixology;

import com.mojang.serialization.MapCodec;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.ItemInteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LevelAccessor;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.level.block.state.properties.IntegerProperty;
import net.minecraft.world.level.block.state.properties.RotationSegment;
import net.minecraft.world.level.material.FluidState;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.level.material.PushReaction;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;
import net.neoforged.neoforge.items.ItemHandlerHelper;
import org.jetbrains.annotations.Nullable;

@SuppressWarnings("deprecation")
public class GlasswareBlock extends HorizontalDirectionalBlock implements SimpleWaterloggedBlock {
    public static final IntegerProperty ROTATION = BlockStateProperties.ROTATION_16;
    public static final BooleanProperty WATERLOGGED = BlockStateProperties.WATERLOGGED;
    public static final VoxelShape SHAPE = Block.box(4, 0, 4, 12, 10, 12);

    private static final MapCodec<GlasswareBlock> CODEC = simpleCodec(GlasswareBlock::new);

    public GlasswareBlock(Properties properties) {
        super(properties);
        this.registerDefaultState(this.stateDefinition.any()
                .setValue(FACING, Direction.NORTH)
                .setValue(ROTATION, 0)
                .setValue(WATERLOGGED, false));
    }

    public GlasswareBlock() {
        this(Properties.of()
                .noOcclusion()
                .instabreak()
                .pushReaction(PushReaction.DESTROY)
                .sound(SoundType.GLASS));
    }

    @Override
    protected ItemInteractionResult useItemOn(ItemStack stack, BlockState state, Level level, BlockPos pos,
                                              Player player, InteractionHand hand, BlockHitResult hitResult) {
        // 如果是空手，那么可以尝试取回
        if (!player.getItemInHand(hand).isEmpty()) {
            return ItemInteractionResult.PASS_TO_DEFAULT_BLOCK_INTERACTION;
        }
        if (level instanceof ServerLevel serverLevel) {
            getDrops(state, serverLevel, pos, level.getBlockEntity(pos))
                    .forEach(s -> ItemHandlerHelper.giveItemToPlayer(player, s));
            level.setBlock(pos, Blocks.AIR.defaultBlockState(), Block.UPDATE_SUPPRESS_DROPS | Block.UPDATE_ALL);
            level.playSound(null, pos, SoundType.STONE.getPlaceSound(), player.getSoundSource(), 1.0F, 1.0F);
        }
        return ItemInteractionResult.SUCCESS;
    }

    @Override
    public BlockState updateShape(BlockState state, Direction direction, BlockState neighborState,
                                  LevelAccessor level, BlockPos pos, BlockPos neighborPos) {
        if (state.getValue(WATERLOGGED)) {
            level.scheduleTick(pos, Fluids.WATER, Fluids.WATER.getTickDelay(level));
        }
        return super.updateShape(state, direction, neighborState, level, pos, neighborPos);
    }

    @Override
    @Nullable
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        boolean isWaterAt = context.getLevel().isWaterAt(context.getClickedPos());
        Direction direction = context.getHorizontalDirection().getOpposite();
        int rotation = RotationSegment.convertToSegment(context.getRotation());
        return this.defaultBlockState()
                .setValue(FACING, direction)
                .setValue(ROTATION, rotation)
                .setValue(WATERLOGGED, isWaterAt);
    }

    @Override
    public void onProjectileHit(Level level, BlockState state, BlockHitResult hit, Projectile projectile) {
        if (!level.isClientSide) {
            BlockPos pos = hit.getBlockPos();
            if (projectile.mayInteract(level, pos)) {
                level.removeBlock(pos, false);
                // 播放玻璃的粒子效果
                int id = Block.getId(Blocks.GLASS.defaultBlockState());
                level.levelEvent(LevelEvent.PARTICLES_DESTROY_BLOCK, pos, id);
            }
        }
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(FACING, ROTATION, WATERLOGGED);
    }

    @Override
    public FluidState getFluidState(BlockState state) {
        return state.getValue(WATERLOGGED) ? Fluids.WATER.getSource(false) : super.getFluidState(state);
    }

    @Override
    public VoxelShape getShape(BlockState pState, BlockGetter pLevel, BlockPos pPos, CollisionContext pContext) {
        return SHAPE;
    }

    @Override
    public float getShadeBrightness(BlockState pState, BlockGetter pLevel, BlockPos pPos) {
        return 1.0F;
    }

    public static int getEffectiveRotation(BlockState state) {
        int rotation = state.getValue(ROTATION);
        if (rotation != 0) {
            return rotation;
        }
        return switch (state.getValue(FACING)) {
            case EAST -> 4;
            case SOUTH -> 8;
            case WEST -> 12;
            default -> 0;
        };
    }

    public static Direction getLegacyFacing(int rotation) {
        return switch (Math.floorMod(rotation + 2, 16) / 4) {
            case 1 -> Direction.EAST;
            case 2 -> Direction.SOUTH;
            case 3 -> Direction.WEST;
            default -> Direction.NORTH;
        };
    }

    @Override
    public BlockState rotate(BlockState state, Rotation rotation) {
        int max = RotationSegment.getMaxSegmentIndex() + 1;
        int rotated = rotation.rotate(getEffectiveRotation(state), max);
        return state.setValue(ROTATION, rotated).setValue(FACING, getLegacyFacing(rotated));
    }

    @Override
    public BlockState mirror(BlockState state, Mirror mirror) {
        int max = RotationSegment.getMaxSegmentIndex() + 1;
        int mirrored = mirror.mirror(getEffectiveRotation(state), max);
        return state.setValue(ROTATION, mirrored).setValue(FACING, getLegacyFacing(mirrored));
    }

    @Override
    protected MapCodec<? extends HorizontalDirectionalBlock> codec() {
        return CODEC;
    }
}
