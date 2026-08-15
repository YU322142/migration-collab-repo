package com.tom.storagemod.inventory;

import java.lang.reflect.Method;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Optional;
import java.util.Set;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.capabilities.BlockCapabilityCache;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.items.IItemHandler;
import net.neoforged.neoforge.items.wrapper.EmptyItemHandler;

import com.tom.storagemod.block.entity.BlockFilterAttachment;
import com.tom.storagemod.components.WorldPos;
import com.tom.storagemod.platform.Platform;
import com.tom.storagemod.util.IValidInfo;
import com.tom.storagemod.util.WorldStates;

public interface PlatformInventoryAccess extends IInventoryAccess {
	public static final PlatformInventoryAccess EMPTY = new PlatformInventoryAccess() {

		@Override
		public IInventoryChangeTracker tracker() {
			return InventoryChangeTracker.NULL;
		}

		@Override
		public IItemHandler get() {
			return EmptyItemHandler.INSTANCE;
		}

		@Override
		public ItemStack pullMatchingStack(ItemStack st, long max) {
			return ItemStack.EMPTY;
		}

		@Override
		public ItemStack pushStack(ItemStack stack) {
			return stack;
		}

		@Override
		public int getFreeSlotCount() {
			return 0;
		}

		@Override
		public IInventoryAccess getRootHandler(Set<IProxy> dejaVu) {
			return this;
		}
	};

	public static class BlockInventoryAccess implements PlatformInventoryAccess {
		private static final ClassValue<Optional<Method>> CONTROLLER_METHOD = new ClassValue<>() {
			@Override
			protected Optional<Method> computeValue(Class<?> type) {
				Class<?> current = type;
				while (current != null && !current.getSimpleName().equals("ItemVaultBlockEntity")) {
					current = current.getSuperclass();
				}
				if (current == null)return Optional.empty();
				try {
					return Optional.of(type.getMethod("getController"));
				} catch (ReflectiveOperationException e) {
					return Optional.empty();
				}
			}
		};
		private boolean valid;
		private BlockCapabilityCache<IItemHandler, Direction> itemCache;
		private WorldPos trackingPos;
		private Level trackingLevel;
		private BlockPos inventoryPos;
		private Direction side;
		private IValidInfo validityInfo;
		private boolean createItemVault;
		private long lastTrackingCheck = Long.MIN_VALUE;
		private WorldPos dynamicTrackingPos;
		private IInventoryChangeTracker.Delegate tracker = new IInventoryChangeTracker.Delegate();

		public void onLoad(Level level, BlockPos worldPosition, Direction side, IValidInfo isValid) {
			valid = true;
			itemCache = null;
			trackingLevel = level;
			inventoryPos = worldPosition.immutable();
			this.side = side;
			validityInfo = isValid;
			createItemVault = isCreateItemVault(level, worldPosition);
			trackingPos = new WorldPos(level.dimension(), inventoryPos);
			dynamicTrackingPos = trackingPos;
			lastTrackingCheck = Long.MIN_VALUE;
		}

		protected void onInvalid() {
		}

		@Override
		public IInventoryChangeTracker tracker() {
			IItemHandler itemHandler = get();
			if (itemHandler != null)
				tracker.setDelegate(WorldStates.getTracker(itemHandler));
			else
				tracker.setDelegate(InventoryChangeTracker.NULL);
			return tracker;
		}

		@Override
		public IItemHandler get() {
			refreshInventoryKind();
			BlockCapabilityCache<IItemHandler, Direction> cache = getOrCreateCache();
			return cache == null ? null : cache.getCapability();
		}

		private BlockCapabilityCache<IItemHandler, Direction> getOrCreateCache() {
			if (!valid)return null;
			if (itemCache == null && trackingLevel instanceof ServerLevel serverLevel && inventoryPos != null) {
				itemCache = BlockCapabilityCache.create(Capabilities.ItemHandler.BLOCK, serverLevel, inventoryPos, side,
						() -> valid && validityInfo != null && validityInfo.isObjectValid(), this::onInvalid);
			}
			return itemCache;
		}

		public static boolean hasInventoryAt(Level level, BlockPos pos, BlockState state, Direction direction) {
			if (isCreateItemVault(level, pos)) {
				BlockEntity blockEntity = level.getBlockEntity(pos);
				if (blockEntity != null)return true;
			}
			return level.getCapability(Capabilities.ItemHandler.BLOCK, pos, state, null, direction) != null;
		}

		@Override
		public void markInvalid() {
			valid = false;
			itemCache = null;
			trackingPos = null;
			trackingLevel = null;
			inventoryPos = null;
			side = null;
			validityInfo = null;
			createItemVault = false;
			dynamicTrackingPos = null;
		}

		public boolean exists() {
			return get() != null;
		}

		@Override
		public IInventoryAccess getRootHandler(Set<IProxy> dejaVu) {
			// Create item vaults are known physical inventories, not Tom's Storage
			// proxies. Avoid materializing their capability during de-duplication.
			if (refreshInventoryKind())return this;
			if (get() instanceof IProxy p) {
				if (dejaVu.add(p)) {
					return p.getRootHandler(dejaVu);
				} else {
					return this;
				}
			}
			return this;
		}

		@Override
		public Object getTrackingKey() {
			boolean vault = refreshInventoryKind();
			if (trackingPos != null)return new BlockInventoryTrackingKey(getDynamicTrackingPos(), vault ? null : side);
			IItemHandler handler = get();
			return handler != null ? handler : this;
		}

		@Override
		public Object getTopologyKey() {
			Object trackingKey = getTrackingKey();
			if (createItemVault || trackingLevel == null || inventoryPos == null
					|| !trackingLevel.isLoaded(inventoryPos))return trackingKey;
			BlockEntity blockEntity = trackingLevel.getBlockEntity(inventoryPos);
			if (blockEntity instanceof IInventoryAccess.IInventory inventory) {
				IInventoryAccess access = inventory.getInventoryAccess();
				Set<IProxy> dejaVu = Collections.newSetFromMap(new IdentityHashMap<>());
				IInventoryAccess root = access.getRootHandler(dejaVu);
				return new BlockInventoryTopologyKey(trackingKey, root, root.getTrackingKey());
			}
			return trackingKey;
		}

		@Override
		public Object getRootDeduplicationKey(IInventoryAccess root) {
			if (refreshInventoryKind() && trackingPos != null) {
				return new BlockInventoryTrackingKey(getDynamicTrackingPos(), null);
			}
			return root;
		}

		private static record BlockInventoryTrackingKey(WorldPos pos, Direction side) {}
		private static record BlockInventoryTopologyKey(Object access, IInventoryAccess root, Object rootTrackingKey) {}

		private boolean refreshInventoryKind() {
			if (trackingLevel == null || inventoryPos == null)return createItemVault;
			if (!trackingLevel.isLoaded(inventoryPos))return createItemVault;
			boolean vault = isCreateItemVault(trackingLevel, inventoryPos);
			if (vault != createItemVault) {
				createItemVault = vault;
				lastTrackingCheck = Long.MIN_VALUE;
				dynamicTrackingPos = trackingPos;
				itemCache = null;
			}
			return vault;
		}

		private WorldPos getDynamicTrackingPos() {
			if (!createItemVault || trackingLevel == null || inventoryPos == null)return trackingPos;
			if (!trackingLevel.isLoaded(inventoryPos))return dynamicTrackingPos;
			long gameTime = trackingLevel.getGameTime();
			if (lastTrackingCheck == gameTime)return dynamicTrackingPos;
			lastTrackingCheck = gameTime;
			dynamicTrackingPos = new WorldPos(trackingLevel.dimension(),
					getCreateController(trackingLevel, inventoryPos, dynamicTrackingPos.pos()));
			return dynamicTrackingPos;
		}

		private static BlockPos getCreateController(Level level, BlockPos pos, BlockPos fallback) {
			if (!level.isLoaded(pos))return fallback;
			BlockEntity blockEntity = level.getBlockEntity(pos);
			if (blockEntity == null)return fallback;
			Optional<Method> method = CONTROLLER_METHOD.get(blockEntity.getClass());
			if (method.isEmpty())return pos;
			try {
				Object controller = method.get().invoke(blockEntity);
				if (controller instanceof BlockPos controllerPos)return controllerPos.immutable();
			} catch (ReflectiveOperationException e) {
				return fallback;
			}
			return fallback;
		}

		private static boolean isCreateItemVault(Level level, BlockPos pos) {
			if (!level.isLoaded(pos))return false;
			BlockEntity blockEntity = level.getBlockEntity(pos);
			return blockEntity != null && CONTROLLER_METHOD.get(blockEntity.getClass()).isPresent();
		}

		@Override
		public String toString() {
			return "BlockInventoryAccess at " + inventoryPos;
		}
	}

	@Override
	IItemHandler get();

	@Override
	public default int getFreeSlotCount() {
		IItemHandler itemHandler = get();
		if (itemHandler == null)return 0;
		int empty = 0;
		for(int i = 0;i<itemHandler.getSlots();i++) {
			if(itemHandler.getStackInSlot(i).isEmpty())empty++;
		}
		return empty;
	}

	@Override
	public default int getSlotCount() {
		IItemHandler itemHandler = get();
		if (itemHandler == null)return 0;
		return itemHandler.getSlots();
	}

	public static BlockFilter getBlockFilterAt(Level level, BlockPos p, boolean make) {
		BlockEntity be = level.getBlockEntity(p);
		if (be == null || (!make && !be.hasData(Platform.BLOCK_FILTER)))return null;
		return be.getData(Platform.BLOCK_FILTER).getFilter();
	}

	public static void removeBlockFilterAt(Level level, BlockPos pos) {
		BlockEntity be = level.getBlockEntity(pos);
		if (be == null || !be.hasData(Platform.BLOCK_FILTER))return;
		BlockFilterAttachment f = be.getData(Platform.BLOCK_FILTER);
		f.getFilter().dropContents(level, pos);
		be.removeData(Platform.BLOCK_FILTER);
	}
}
