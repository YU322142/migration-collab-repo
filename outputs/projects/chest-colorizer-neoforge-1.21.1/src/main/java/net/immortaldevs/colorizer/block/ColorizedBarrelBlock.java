package net.immortaldevs.colorizer.block;

import net.immortaldevs.colorizer.BlockColor;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.BarrelBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.EnumProperty;

public final class ColorizedBarrelBlock extends Block {
    public static final EnumProperty<BlockColor> COLOR = EnumProperty.create("color", BlockColor.class);

    public ColorizedBarrelBlock(BlockBehaviour.Properties properties) {
        super(properties);
        registerDefaultState(stateDefinition.any()
                .setValue(BarrelBlock.FACING, Direction.NORTH)
                .setValue(BarrelBlock.OPEN, false)
                .setValue(COLOR, BlockColor.DEFAULT));
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(BarrelBlock.FACING, BarrelBlock.OPEN, COLOR);
    }
}
