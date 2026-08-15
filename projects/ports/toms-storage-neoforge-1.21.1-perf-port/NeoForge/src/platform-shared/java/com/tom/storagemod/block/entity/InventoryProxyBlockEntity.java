package com.tom.storagemod.block.entity;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.state.BlockState;

import com.tom.storagemod.Content;
import com.tom.storagemod.block.AbstractInventoryHopperBlock;
import com.tom.storagemod.inventory.IInventoryAccess;
import com.tom.storagemod.inventory.IInventoryAccess.IInventory;
import com.tom.storagemod.inventory.PlatformInventoryAccess.BlockInventoryAccess;
import com.tom.storagemod.inventory.PlatformProxyInventoryAccess;

public class InventoryProxyBlockEntity extends PaintedBlockEntity implements IInventory {
	private BlockInventoryAccess block = new BlockInventoryAccess() {

		@Override
		protected void onInvalid() {
			markCapsInvalid();
		}
	};
	private PlatformProxyInventoryAccess proxy = new PlatformProxyInventoryAccess(block);
	private BlockPos targetPos;
	private Direction targetSide;

	public InventoryProxyBlockEntity(BlockPos pos, BlockState state) {
		super(Content.invProxyBE.get(), pos, state);
	}

	@Override
	public void onLoad() {
		super.onLoad();
		if (!level.isClientSide) {
			refreshTarget();
		}
	}

	private void refreshTarget() {
		BlockState state = level.getBlockState(worldPosition);
		Direction facing = state.getValue(AbstractInventoryHopperBlock.FACING);
		BlockPos nextTarget = worldPosition.relative(facing);
		Direction nextSide = facing.getOpposite();
		if (!nextTarget.equals(targetPos) || nextSide != targetSide) {
			targetPos = nextTarget.immutable();
			targetSide = nextSide;
			block.onLoad(level, targetPos, targetSide, this);
		}
	}

	@Override
	public IInventoryAccess getInventoryAccess() {
		if (level != null && !level.isClientSide)refreshTarget();
		return proxy;
	}
}
