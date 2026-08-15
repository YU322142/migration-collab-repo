package com.tom.storagemod.inventory;

import java.util.Set;
import java.util.stream.Stream;

import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;

import com.tom.storagemod.inventory.filter.ItemPredicate;

public interface IInventoryAccess extends IChangeTrackerAccess, IProxy {

	default ItemStack pullMatchingStack(ItemStack st, long max) {
		InventorySlot slot = null;
		var tr = tracker();
		StoredItemStack s = new StoredItemStack(st, 1);
		ItemPredicate ip = s::equalItem;
		ItemStack ext = null;
		long ex = 0;
		while (ex < max && (slot = tr.findSlotAfter(slot, ip, false, false)) != null) {
			ItemStack e = slot.extract((int) (max - ex));
			if (e.isEmpty())continue;
			if (ext == null)ext = e;
			else ext.grow(e.getCount());
			ex += e.getCount();
		}
		return ext != null ? ext : ItemStack.EMPTY;
	}

	default ItemStack pushStack(ItemStack stack) {
		var tr = tracker();
		StoredItemStack s = new StoredItemStack(stack);
		InventorySlot slot = null;
		while (!stack.isEmpty() && (slot = tr.findSlotDestAfter(slot, s, false)) != null) {
			stack = slot.insert(stack);
			s.setCount(stack.getCount());
		}
		return stack;
	}

	int getFreeSlotCount();
	int getSlotCount();

	@Deprecated
	Object get();

	@Override
	IInventoryAccess getRootHandler(Set<IProxy> dejaVu);

	default Object getTrackingKey() {
		return this;
	}

	/**
	 * Cheap topology token. It may include a dynamic proxy root while
	 * getTrackingKey remains the logical de-duplication key.
	 */
	default Object getTopologyKey() {
		return getTrackingKey();
	}

	/**
	 * Second-stage de-duplication key after proxy resolution. Implementations may
	 * return a canonical physical key when several access objects expose the same
	 * inventory; the default preserves the original root-based algorithm.
	 */
	default Object getRootDeduplicationKey(IInventoryAccess root) {
		return root;
	}

	@SuppressWarnings("unchecked")
	default <T> T getPlatformHandler() {
		T t = (T) get();
		return t != null ? t : (T) PlatformInventoryAccess.EMPTY.get();
	}

	default void markInvalid() {}

	public static interface IMultiThreadedTracker<A, B> {
		A prepForOffThread(Level level);
		B processOffThread(A array);
		long finishOffThreadProcess(Level level, B ct);
	}

	public static interface IChangeNotifier {
		void onSlotChanged(InventorySlot slot);
	}

	public static interface IInventoryChangeTracker {
		public static record TrackedStack(Object source, StoredItemStack stack) {}

		long getChangeTracker(Level level);
		default long refreshNow(Level level) {
			invalidateForImmediateRefresh();
			return getChangeTracker(level);
		}
		default void invalidateForImmediateRefresh() {
		}

		Stream<StoredItemStack> streamWrappedStacks(boolean parallel);
		default Stream<TrackedStack> streamTrackedStacks(boolean parallel) {
			return streamWrappedStacks(parallel).map(s -> new TrackedStack(null, s));
		}
		long countItems(StoredItemStack filter);
		InventorySlot findSlot(ItemPredicate filter, boolean findEmpty);
		InventorySlot findSlotAfter(InventorySlot slot, ItemPredicate filter, boolean findEmpty, boolean loop);
		InventorySlot findSlotDest(StoredItemStack forStack);
		InventorySlot findSlotDestAfter(InventorySlot slot, StoredItemStack forStack, boolean loop);

		public static class Delegate implements IInventoryChangeTracker, IMultiThreadedTracker<Object, Object> {
			private IInventoryChangeTracker delegate;

			private static record DelegateImage(IInventoryChangeTracker owner,
					IMultiThreadedTracker<Object, Object> tracker, Object image) {}

			private static record DelegateResult(DelegateImage image, Object result) {}

			@Override
			public Stream<StoredItemStack> streamWrappedStacks(boolean parallel) {
				return delegate.streamWrappedStacks(parallel);
			}

			@Override
			public Stream<TrackedStack> streamTrackedStacks(boolean parallel) {
				return delegate.streamTrackedStacks(parallel);
			}

			@Override
			public long countItems(StoredItemStack filter) {
				return delegate.countItems(filter);
			}

			@Override
			public long getChangeTracker(Level level) {
				return delegate.getChangeTracker(level);
			}

			@Override
			public long refreshNow(Level level) {
				return delegate.refreshNow(level);
			}

			@Override
			public void invalidateForImmediateRefresh() {
				delegate.invalidateForImmediateRefresh();
			}

			public void setDelegate(IInventoryChangeTracker delegate) {
				this.delegate = delegate;
			}

			@Override
			public InventorySlot findSlot(ItemPredicate filter, boolean findEmpty) {
				return delegate.findSlot(filter, findEmpty);
			}

			@Override
			public Object prepForOffThread(Level level) {
				IInventoryChangeTracker owner = delegate;
				if (!(owner instanceof IMultiThreadedTracker<?, ?> raw))return null;
				@SuppressWarnings("unchecked")
				IMultiThreadedTracker<Object, Object> tracker = (IMultiThreadedTracker<Object, Object>) raw;
				Object image = tracker.prepForOffThread(level);
				return image == null ? null : new DelegateImage(owner, tracker, image);
			}

			@Override
			public Object processOffThread(Object value) {
				DelegateImage image = (DelegateImage) value;
				return new DelegateResult(image, image.tracker().processOffThread(image.image()));
			}

			@Override
			public long finishOffThreadProcess(Level level, Object value) {
				DelegateResult result = (DelegateResult) value;
				if (delegate != result.image().owner()) {
					// The capability/root was replaced while the worker was running.
					// Never submit the old image to the new delegate.
					delegate.invalidateForImmediateRefresh();
					return delegate.getChangeTracker(level);
				}
				return result.image().tracker().finishOffThreadProcess(level, result.result());
			}

			@Override
			public InventorySlot findSlotDest(StoredItemStack forStack) {
				return delegate.findSlotDest(forStack);
			}

			@Override
			public InventorySlot findSlotAfter(InventorySlot slot, ItemPredicate filter, boolean findEmpty, boolean loop) {
				return delegate.findSlotAfter(slot, filter, findEmpty, loop);
			}

			@Override
			public InventorySlot findSlotDestAfter(InventorySlot slot, StoredItemStack forStack, boolean loop) {
				return delegate.findSlotDestAfter(slot, forStack, loop);
			}
		}
	}

	public static interface IInventory {
		IInventoryAccess getInventoryAccess();
	}
}
