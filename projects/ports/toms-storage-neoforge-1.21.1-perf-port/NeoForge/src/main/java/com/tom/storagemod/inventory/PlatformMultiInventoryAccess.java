package com.tom.storagemod.inventory;

import java.util.Arrays;

import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.items.IItemHandler;
import net.neoforged.neoforge.items.wrapper.EmptyItemHandler;

public class PlatformMultiInventoryAccess extends MultiInventoryAccess implements IItemHandler {
	private int[] offsets = new int[0];
	private int[] inventoryIndexes = new int[0];
	private int invSize, offsetsSize;
	private boolean calling;

	@Override
	public IItemHandler get() {
		return this;
	}

	private int findInventory(int slot) {
		int arrayIndex = Arrays.binarySearch(offsets, 0, offsetsSize, slot);
		if (arrayIndex < 0) {
			arrayIndex = -arrayIndex - 2;
		}
		return arrayIndex;
	}

	@Override
	public boolean isItemValid(int slot, ItemStack stack) {
		if(calling)return false;
		if(slot >= invSize)return false;
		calling = true;

		int arrayIndex = findInventory(slot);
		int invSlot = slot - offsets[arrayIndex];

		boolean r = getHandler(arrayIndex, invSlot).isItemValid(invSlot, stack);
		calling = false;
		return r;
	}

	@Override
	public ItemStack insertItem(int slot, ItemStack stack, boolean simulate) {
		if(calling)return stack;
		if(slot >= invSize)return stack;
		calling = true;

		int arrayIndex = findInventory(slot);
		int invSlot = slot - offsets[arrayIndex];

		ItemStack s = getHandler(arrayIndex, invSlot).insertItem(invSlot, stack, simulate);
		calling = false;
		return s;
	}

	@Override
	public ItemStack getStackInSlot(int slot) {
		if(calling)return ItemStack.EMPTY;
		if(slot >= invSize)return ItemStack.EMPTY;
		calling = true;

		int arrayIndex = findInventory(slot);
		int invSlot = slot - offsets[arrayIndex];

		ItemStack s = getHandler(arrayIndex, invSlot).getStackInSlot(invSlot);
		calling = false;
		return s;
	}

	@Override
	public int getSlots() {
		return invSize;
	}

	@Override
	public int getSlotLimit(int slot) {
		if(calling)return 0;
		if(slot >= invSize)return 0;
		calling = true;

		int arrayIndex = findInventory(slot);
		int invSlot = slot - offsets[arrayIndex];

		int r = getHandler(arrayIndex, invSlot).getSlotLimit(invSlot);
		calling = false;
		return r;
	}

	@Override
	public ItemStack extractItem(int slot, int amount, boolean simulate) {
		if(calling)return ItemStack.EMPTY;
		if(slot >= invSize)return ItemStack.EMPTY;
		calling = true;

		int arrayIndex = findInventory(slot);
		int invSlot = slot - offsets[arrayIndex];

		ItemStack s = getHandler(arrayIndex, invSlot).extractItem(invSlot, amount, simulate);
		calling = false;
		return s;
	}

	@Override
	public void clear() {
		super.clear();
		invSize = 0;
		offsetsSize = 0;
	}

	@Override
	public void refresh() {
		if(offsets.length != connected.size()) {
			offsets = new int[connected.size()];
			inventoryIndexes = new int[connected.size()];
		}
		invSize = 0;
		offsetsSize = 0;
		for (int i = 0; i < connected.size(); i++) {
			IItemHandler ih = getConnectedHandler(i);
			int s = ih.getSlots();
			if (s > 0) {
				offsets[offsetsSize] = invSize;
				inventoryIndexes[offsetsSize] = i;
				invSize += s;
				offsetsSize++;
			}
		}
	}

	private IItemHandler getHandler(int i, int invSlot) {
		if (i < 0 || i >= offsetsSize)return EmptyItemHandler.INSTANCE;
		IItemHandler h = getConnectedHandler(inventoryIndexes[i]);
		if (h == null)return EmptyItemHandler.INSTANCE;
		if (invSlot < h.getSlots())
			return h;
		return EmptyItemHandler.INSTANCE;
	}

	private IItemHandler getConnectedHandler(int i) {
		IItemHandler h = connected.get(i).getPlatformHandler();
		return h != null ? h : EmptyItemHandler.INSTANCE;
	}
}
