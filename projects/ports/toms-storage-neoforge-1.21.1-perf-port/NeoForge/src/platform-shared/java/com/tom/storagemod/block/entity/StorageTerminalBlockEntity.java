package com.tom.storagemod.block.entity;

import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.WeakHashMap;
import java.util.stream.Collectors;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.world.Containers;
import net.minecraft.world.MenuProvider;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;

import com.tom.storagemod.Config;
import com.tom.storagemod.Content;
import com.tom.storagemod.StorageMod;
import com.tom.storagemod.block.AbstractStorageTerminalBlock;
import com.tom.storagemod.block.AbstractStorageTerminalBlock.TerminalPos;
import com.tom.storagemod.inventory.IInventoryAccess;
import com.tom.storagemod.inventory.IInventoryAccess.IInventoryChangeTracker;
import com.tom.storagemod.inventory.NetworkInventory;
import com.tom.storagemod.inventory.StoredItemStack;
import com.tom.storagemod.inventory.TerminalItemStack;
import com.tom.storagemod.item.WirelessTerminal;
import com.tom.storagemod.menu.StorageTerminalMenu;
import com.tom.storagemod.platform.PlatformBlockEntity;
import com.tom.storagemod.util.BeaconLevelCalc;
import com.tom.storagemod.util.PlayerInvUtil;
import com.tom.storagemod.util.TickerUtil.TickableServer;
import com.tom.storagemod.util.Util;

public class StorageTerminalBlockEntity extends PlatformBlockEntity implements MenuProvider, TickableServer {
	private static final Set<StorageTerminalBlockEntity> LOADED_TERMINALS = Collections.newSetFromMap(new WeakHashMap<>());
	private NetworkInventory itemCache = new NetworkInventory();
	private Map<StoredItemStack, TerminalItemStack> items = new HashMap<>();
	private int sort;
	private int searchType;
	private int modes;
	private String lastSearch = "";
	private boolean updateItems;
	private int changeCount;
	private int beaconLevel;
	private long changeTracker;
	private long lastRecalculateGameTime = Long.MIN_VALUE;
	private int slotCount, freeCount;

	public StorageTerminalBlockEntity(BlockPos pos, BlockState state) {
		super(Content.terminalBE.get(), pos, state);
	}

	public StorageTerminalBlockEntity(BlockEntityType<?> tileEntityTypeIn, BlockPos pos, BlockState state) {
		super(tileEntityTypeIn, pos, state);
	}

	@Override
	public void onLoad() {
		super.onLoad();
		if (!level.isClientSide) {
			LOADED_TERMINALS.add(this);
			BlockState st = level.getBlockState(worldPosition);
			Direction d = st.getValue(AbstractStorageTerminalBlock.FACING);
			TerminalPos p = st.getValue(AbstractStorageTerminalBlock.TERMINAL_POS);
			if(p == TerminalPos.UP)d = Direction.UP;
			if(p == TerminalPos.DOWN)d = Direction.DOWN;
			itemCache.onLoad(level, worldPosition.relative(d), d.getOpposite(), this);
		}
	}

	@Override
	public void setRemoved() {
		LOADED_TERMINALS.remove(this);
		super.setRemoved();
	}

	@Override
	public AbstractContainerMenu createMenu(int id, Inventory plInv, Player arg2) {
		return new StorageTerminalMenu(id, plInv, this);
	}

	@Override
	public Component getDisplayName() {
		return Component.translatable("menu.toms_storage.storage_terminal");
	}

	public Map<StoredItemStack, TerminalItemStack> getStacks() {
		updateItems = true;
		return items;
	}

	public StoredItemStack pullStack(StoredItemStack stack, long max) {
		if (stack == null)return null;
		IInventoryAccess ii = itemCache.getAccess(level, worldPosition);
		ItemStack ex = ii.pullMatchingStack(stack.getStack(), max);
		if (ex.isEmpty())return null;
		return new StoredItemStack(ex);
	}

	public Iterable<StoredItemStack> getFreshCraftingStacks() {
		IInventoryAccess ii = itemCache.getAccess(level, worldPosition);
		IInventoryChangeTracker tracker = ii.tracker();
		tracker.refreshNow(level);
		return () -> tracker.streamWrappedStacks(false).iterator();
	}

	public Iterable<StoredItemStack> getCachedCraftingStacks() {
		return () -> items.values().stream()
				.map(stack -> (StoredItemStack) stack)
				.iterator();
	}

	public StoredItemStack pushStack(StoredItemStack stack) {
		if (stack == null)return null;
		IInventoryAccess ii = itemCache.getAccess(level, worldPosition);
		ItemStack r = ii.pushStack(stack.getActualStack());
		if (r.isEmpty())return null;
		return new StoredItemStack(r);
	}

	public ItemStack pushStack(ItemStack itemstack) {
		StoredItemStack is = pushStack(new StoredItemStack(itemstack));
		return is == null ? ItemStack.EMPTY : is.getActualStack();
	}

	public void pushOrDrop(ItemStack st) {
		if(st.isEmpty())return;
		StoredItemStack st0 = pushStack(new StoredItemStack(st));
		if(st0 != null) {
			dropItem(st0.getActualStack());
		}
	}

	public void dropItem(ItemStack stack) {
		Containers.dropItemStack(level, worldPosition.getX() + .5f, worldPosition.getY() + .5f, worldPosition.getZ() + .5f, stack);
	}

	@Override
	public void updateServer() {
		if(updateItems) {
			recalculateItems(false);
			updateItems = false;
		}
		if(level.getGameTime() % 40 == Math.abs(worldPosition.hashCode()) % 40) {
			beaconLevel = BlockPos.betweenClosedStream(new AABB(worldPosition).inflate(8)).mapToInt(p -> {
				if(level.isLoaded(p)) {
					BlockState st = level.getBlockState(p);
					if(st.is(Blocks.BEACON)) {
						return BeaconLevelCalc.calcBeaconLevel(level, p.getX(), p.getY(), p.getZ());
					}
				}
				return -1;
			}).max().orElse(-1);
		}
	}

	private boolean recalculateItems(boolean force) {
		long start = System.nanoTime();
		long gameTime = level.getGameTime();
		int cooldown = Config.get().terminalRecalcCooldownTicks;
		if (!force && cooldown > 0 && lastRecalculateGameTime != Long.MIN_VALUE && gameTime - lastRecalculateGameTime < cooldown) {
			if (Config.get().terminalScanDebug) {
				int logInterval = Math.max(20, cooldown);
				if (Math.floorMod(gameTime, logInterval) == Math.floorMod(worldPosition.hashCode(), logInterval)) {
					StorageMod.LOGGER.info("Tom's Storage terminal recalc throttled: pos={}, cooldownTicks={}, nextInTicks={}", worldPosition, cooldown, cooldown - (gameTime - lastRecalculateGameTime));
				}
			}
			return false;
		}
		lastRecalculateGameTime = gameTime;
		IInventoryAccess ii = itemCache.getAccess(level, worldPosition);
		IInventoryChangeTracker tr = ii.tracker();
		long ct = tr.getChangeTracker(level);
		if (force || changeTracker != ct) {
			changeTracker = ct;

			List<TerminalItemStack> rawItems = tr.streamWrappedStacks(Config.get().runMultithreaded)
					.map(TerminalItemStack::new)
					.toList();
			long rawEntries = rawItems.size();
			if (Config.get().runMultithreaded) {
				items = rawItems.parallelStream().collect(Collectors.groupingByConcurrent(
						s -> (StoredItemStack) s,
						Util.reducingWithCopy(null, TerminalItemStack::merge, TerminalItemStack::new)));
			} else {
				items = new HashMap<>();
				rawItems.forEach(s -> items.merge(s, s, TerminalItemStack::merge));
				items.replaceAll((k, v) -> new TerminalItemStack(v));
			}
			slotCount = Math.max(0, ii.getSlotCount());
			freeCount = Math.max(0, ii.getFreeSlotCount());
			changeCount++;
			long elapsedMs = (System.nanoTime() - start) / 1_000_000L;
			if (Config.get().terminalScanDebug || elapsedMs > 250L) {
				StorageMod.LOGGER.info("Tom's Storage terminal recalc: pos={}, force={}, rawEntries={}, mergedEntries={}, slots={}, freeSlots={}, elapsed={}ms", worldPosition, force, rawEntries, items.size(), slotCount, freeCount, elapsedMs);
			}
			return true;
		}
		if (Config.get().terminalScanDebug) {
			long elapsedMs = (System.nanoTime() - start) / 1_000_000L;
			StorageMod.LOGGER.info("Tom's Storage terminal recalc skipped: pos={}, force={}, unchanged=true, elapsed={}ms", worldPosition, force, elapsedMs);
		}
		return false;
	}

	public boolean forceRecalculateStorage() {
		if (level == null || level.isClientSide)return false;
		itemCache.markDirty();
		updateItems = true;
		return recalculateItems(true);
	}

	public static int forceRecalculateLoadedTerminals() {
		int count = 0;
		Iterator<StorageTerminalBlockEntity> itr = LOADED_TERMINALS.iterator();
		while (itr.hasNext()) {
			StorageTerminalBlockEntity terminal = itr.next();
			if (terminal == null || terminal.isRemoved() || terminal.level == null || terminal.level.isClientSide) {
				itr.remove();
				continue;
			}
			if (terminal.forceRecalculateStorage())count++;
		}
		return count;
	}

	public static void clearLoadedTerminals() {
		LOADED_TERMINALS.clear();
	}

	public boolean canInteractWith(Player player, boolean menuCheck) {
		if(level.getBlockEntity(worldPosition) != this)return false;
		int d = 6;
		int termReach = PlayerInvUtil.findItem(player, i -> i.getItem() instanceof WirelessTerminal, 0, i -> ((WirelessTerminal)i.getItem()).getRange(player, i));
		if(Config.get().wirelessTermBeaconLvl != -1 && beaconLevel >= Config.get().wirelessTermBeaconLvl && termReach > 0) {
			if(Config.get().wirelessTermBeaconLvlCrossDim != -1 && beaconLevel >= Config.get().wirelessTermBeaconLvlCrossDim)return true;
			else return player.level() == level;
		}
		d = Math.max(d, termReach);
		if (menuCheck)d += (d / 4);
		return player.level() == level && !(player.distanceToSqr(this.worldPosition.getX() + 0.5D, this.worldPosition.getY() + 0.5D, this.worldPosition.getZ() + 0.5D) > d*d);
	}

	public int getSorting() {
		return sort;
	}

	public int getModes() {
		return modes;
	}

	public int getSearchType() {
		return searchType;
	}

	public void setSorting(int newC) {
		sort = newC;
		setChanged();
	}

	public void setModes(int modes) {
		this.modes = modes;
		setChanged();
	}

	public void setSearchType(int searchType) {
		this.searchType = searchType;
		setChanged();
	}

	@Override
	public void saveAdditional(CompoundTag compound, HolderLookup.Provider provider) {
		super.saveAdditional(compound, provider);
		compound.putInt("sorting", sort);
		compound.putInt("modes", modes);
		compound.putInt("searchType", searchType);
	}

	@Override
	public void loadAdditional(CompoundTag compound, HolderLookup.Provider provider) {
		if (compound.contains("sort")) {
			// Convert old format
			int s = compound.getInt("sort");
			int controllMode = (s & 0b000_00_0_11);
			boolean rev = (s & 0b000_00_1_00) > 0;
			int type = (s & 0b000_11_0_00) >> 3;
			searchType = (s & 0b111_00_0_00) >> 5;
			boolean ghostItems = (s & 0b1_0_000_00_0_00) != 0;
			boolean tallMode  =  (s & 0b1_0_0_000_00_0_00) != 0;
			boolean pullFromInv = (s & (1 << 8)) != 0;//Crafting Terminal

			modes = controllMode | (tallMode ? 0x10 : 0) | (pullFromInv ? 0x20 : 0);
			sort = type | (rev ? 0x100 : 0) | (ghostItems ? 0x200 : 0);
		} else {
			sort = compound.getInt("sorting");
			modes = compound.getInt("modes");
			searchType = compound.getInt("searchType");
		}
		super.loadAdditional(compound, provider);
	}

	public String getLastSearch() {
		return lastSearch;
	}

	public void setLastSearch(String string) {
		lastSearch = string;
	}

	public int getBeaconLevel() {
		return beaconLevel;
	}

	public int getChangeCount() {
		return changeCount;
	}

	public int getFreeCount() {
		return freeCount;
	}

	public int getSlotCount() {
		return slotCount;
	}
}
