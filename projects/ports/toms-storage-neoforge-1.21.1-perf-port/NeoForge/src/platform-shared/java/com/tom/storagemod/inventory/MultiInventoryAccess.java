package com.tom.storagemod.inventory;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Queue;
import java.util.Set;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;

import com.tom.storagemod.Config;
import com.tom.storagemod.StorageMod;
import com.tom.storagemod.block.entity.IInventoryConnector;
import com.tom.storagemod.inventory.IInventoryAccess.IInventoryChangeTracker.TrackedStack;
import com.tom.storagemod.inventory.filter.ItemPredicate;
import com.tom.storagemod.util.Priority;
import com.tom.storagemod.util.Priority.IPriority;
import com.tom.storagemod.util.WorldStates;

public abstract class MultiInventoryAccess implements IInventoryAccess {
	protected List<IInventoryAccess> connected = new ArrayList<>();
	protected MultiChangeTracker tracker = new MultiChangeTracker();
	private static final AtomicInteger SCAN_THREAD_ID = new AtomicInteger();
	private static volatile ExecutorService scanExecutor;
	private static volatile int scanExecutorSize;

	public MultiInventoryAccess() {
		WorldStates.trackers.put(getPlatformHandler(), tracker());
	}

	public void build(IInventoryConnector self, Collection<IInventoryConnector> connectors) {
		long buildStart = System.nanoTime();
		Queue<IInventoryConnector> q = new ArrayDeque<>();
		q.add(self);
		q.addAll(connectors);
		Set<IInventoryConnector> all = new HashSet<>();
		while (!q.isEmpty()) {
			IInventoryConnector ic = q.poll();
			if (all.add(ic)) {
				q.addAll(ic.getConnectedConnectors());
			}
		}
		var map = all.stream().flatMap(c -> c.getConnectedInventories().stream()).
				collect(Collectors.groupingBy(IPriority.GETTER, () -> new EnumMap<>(Priority.class), Collectors.toList()));
		List<IInventoryAccess> orderedCandidates = new ArrayList<>();
		for (int i = Priority.VALUES.length - 1; i >= 0; i--) {
			orderedCandidates.addAll(map.getOrDefault(Priority.VALUES[i], Collections.emptyList()));
		}
		// The canonical key is deliberately checked before getRootHandler(). Create
		// vault members share one controller key, so thousands of member blocks are
		// collapsed before Fabric/NeoForge constructs a storage wrapper for them.
		InventoryDeduplicator.Result<IInventoryAccess> dedup = InventoryDeduplicator.select(
				orderedCandidates, getTrackingKey(), getRootDeduplicationKey(this),
				IInventoryAccess::getTrackingKey, this::getResolvedRoot,
				IInventoryAccess::getRootDeduplicationKey,
				root -> root instanceof MultiInventoryAccess);
		List<IInventoryAccess> nextConnected = new ArrayList<>(dedup.selected());
		int candidateCount = dedup.candidateCount();
		int trackingDuplicateCount = dedup.trackingDuplicateCount();
		int rootDuplicateCount = dedup.rootDuplicateCount();
		int nestedNetworkCount = dedup.skippedRootCount();
		// If the connected list is identical (same instances, same order), keep the
		// objects but still refresh platform slot-shape caches.
		if (connected.size() == nextConnected.size()) {
			boolean same = true;
			for (int i = 0; i < connected.size(); i++) {
				if (connected.get(i) != nextConnected.get(i)) {
					same = false;
					break;
				}
			}
			if (same) {
				refresh();
				if (Config.get().terminalScanDebug) {
					StorageMod.LOGGER.info("Tom's Storage network build skipped (unchanged): connectors={}, candidates={}, connected={}, trackingDuplicatesSkipped={}, rootDuplicatesSkipped={}, nestedNetworksSkipped={}, elapsed={}ms", all.size(), candidateCount, connected.size(), trackingDuplicateCount, rootDuplicateCount, nestedNetworkCount, elapsedMillis(buildStart));
				}
				return;
			}
		}
		connected = nextConnected;
		Set<Object> verifyKeys = new HashSet<>();
		int verifyDups = 0;
		for (IInventoryAccess a : connected) {
			Object key = a.getTrackingKey();
			if (!verifyKeys.add(key)) verifyDups++;
		}
		if (verifyDups > 0) {
			StorageMod.LOGGER.error("Tom's Storage FATAL: build produced {} REAL tracking-key duplicates in connected list (connected={}, candidates={}, trackingDuplicatesSkipped={}, rootDuplicatesSkipped={})", verifyDups, connected.size(), candidateCount, trackingDuplicateCount, rootDuplicateCount);
		} else if (Config.get().terminalScanDebug || elapsedMillis(buildStart) > 250L) {
			StorageMod.LOGGER.info("Tom's Storage network build: connectors={}, candidates={}, connected={}, trackingDuplicatesSkipped={}, rootDuplicatesSkipped={}, nestedNetworksSkipped={}, realTrackingKeyDups=0, elapsed={}ms", all.size(), candidateCount, connected.size(), trackingDuplicateCount, rootDuplicateCount, nestedNetworkCount, elapsedMillis(buildStart));
		}
		refresh();
	}

	private static long elapsedMillis(long startNanos) {
		return (System.nanoTime() - startNanos) / 1_000_000L;
	}

	private IInventoryAccess getResolvedRoot(IInventoryAccess access) {
		Set<IProxy> dejaVu = Collections.newSetFromMap(new IdentityHashMap<>());
		return access.getRootHandler(dejaVu);
	}

	@Override
	public ItemStack pullMatchingStack(ItemStack st, long max) {
		ItemStack res = ItemStack.EMPTY;
		int c = 0;
		for (int i = 0;i<connected.size();i++) {
			ItemStack p = connected.get(i).pullMatchingStack(st, max - c);
			if (p.isEmpty())continue;
			if (res.isEmpty())res = p;
			c += p.getCount();
			if (c >= max)break;
		}
		res.setCount(c);
		return res;
	}

	@Override
	public ItemStack pushStack(ItemStack stack) {
		for (int i = 0;i<connected.size();i++) {
			stack = connected.get(i).pushStack(stack);
			if (stack.isEmpty())return ItemStack.EMPTY;
		}
		return stack;
	}

	@Override
	public IInventoryChangeTracker tracker() {
		return tracker;
	}

	@Override
	public int getFreeSlotCount() {
		long c = 0;
		for (int i = 0;i<connected.size();i++) {
			c += Math.max(0, connected.get(i).getFreeSlotCount());
			if (c >= Integer.MAX_VALUE)return Integer.MAX_VALUE;
		}
		return (int) c;
	}

	@Override
	public int getSlotCount() {
		long c = 0;
		for (int i = 0;i<connected.size();i++) {
			c += Math.max(0, connected.get(i).getSlotCount());
			if (c >= Integer.MAX_VALUE)return Integer.MAX_VALUE;
		}
		return (int) c;
	}

	public void clear() {
		connected.clear();
	}

	public int getInventoryCount() {
		return connected.size();
	}

	protected void refresh() {
	}

	/**
	 * Refresh platform-specific slot shapes without rebuilding or changing the
	 * de-duplicated connection list.
	 */
	public final void refreshShape() {
		refresh();
	}

	@Override
	public IInventoryAccess getRootHandler(Set<IProxy> dejaVu) {
		return this;
	}

	private static class ItemList extends ArrayList<TrackedStack> {
		private static final long serialVersionUID = 6690277901361998268L;
	}

	public static class TrackerInfo {
		private int id;
		private IMultiThreadedTracker<Object, Object> mt;
		private Object prep, result;
		private long tracker;

		public TrackerInfo(int id, IMultiThreadedTracker<?, ?> mt, Object prep) {
			this.id = id;
			this.mt = (IMultiThreadedTracker<Object, Object>) mt;
			this.prep = prep;
		}

		public void run() {
			result = mt.processOffThread(prep);
		}

		public void finish(Level level) {
			tracker = mt.finishOffThreadProcess(level, result);
		}
	}

	private static int getScanThreadCount() {
		int cpus = Runtime.getRuntime().availableProcessors();
		int configured = Config.get().terminalScanThreads;
		if (configured > 0)return Math.max(1, Math.min(configured, cpus));
		return Math.max(1, Math.min(6, cpus - 2));
	}

	private static ExecutorService getScanExecutor(int threads) {
		if (scanExecutor != null && scanExecutorSize == threads)return scanExecutor;
		synchronized (MultiInventoryAccess.class) {
			if (scanExecutor != null && scanExecutorSize == threads)return scanExecutor;
			ExecutorService oldExecutor = scanExecutor;
			ThreadFactory factory = r -> {
				Thread thread = new Thread(r, "TomStorage-Scanner-" + SCAN_THREAD_ID.incrementAndGet());
				thread.setDaemon(true);
				return thread;
			};
			scanExecutor = Executors.newFixedThreadPool(threads, factory);
			scanExecutorSize = threads;
			if (oldExecutor != null)oldExecutor.shutdown();
			return scanExecutor;
		}
	}

	private static boolean runScanTasks(List<TrackerInfo> infos) {
		int threads = Math.min(getScanThreadCount(), infos.size());
		if (threads <= 1) {
			infos.forEach(TrackerInfo::run);
			return true;
		}
		ExecutorService executor = getScanExecutor(threads);
		List<Future<?>> futures = new ArrayList<>(infos.size());
		for (TrackerInfo info : infos) {
			futures.add(executor.submit(info::run));
		}
		for (Future<?> future : futures) {
			try {
				future.get();
			} catch (InterruptedException e) {
				futures.forEach(pending -> pending.cancel(true));
				Thread.currentThread().interrupt();
				StorageMod.LOGGER.warn("Tom's Storage inventory scan was interrupted", e);
				return false;
			} catch (ExecutionException e) {
				futures.forEach(pending -> pending.cancel(true));
				throw new RuntimeException("Tom's Storage inventory scan failed", e.getCause());
			}
		}
		return true;
	}

	protected class MultiChangeTracker implements IInventoryChangeTracker {
		private long lastUpdate, lastChange, lastChildInvalidation = Long.MIN_VALUE;
		private long[] trackers = new long[0];
		private ItemList[] items = new ItemList[0];
		private Object[] sourceKeys = new Object[0];

		private Object[] getSourceKeys() {
			Object[] keys = new Object[connected.size()];
			for (int i = 0;i<connected.size();i++) {
				keys[i] = connected.get(i).getTrackingKey();
			}
			return keys;
		}

		private boolean connectionsChanged(Object[] keys) {
			if (sourceKeys.length != keys.length)return true;
			for (int i = 0;i<keys.length;i++) {
				if (!Objects.equals(sourceKeys[i], keys[i]))return true;
			}
			return false;
		}

		private boolean multithreadProcessing(Level level) {
			int size = connected.size();
			List<TrackerInfo> infos = new ArrayList<>(size);
			boolean ch = false;
			for (int i = 0;i<connected.size();i++) {
				IInventoryChangeTracker tr = connected.get(i).tracker();
				if (tr instanceof IMultiThreadedTracker mt) {
					Object prep = mt.prepForOffThread(level);
					if (prep != null) {
						infos.add(new TrackerInfo(i, mt, prep));
						continue;
					}
				}
				long v = tr.getChangeTracker(level);
				if (v != trackers[i]) {
					ch |= true;
					items[i] = null;
					trackers[i] = v;
				}
			}
			if (!runScanTasks(infos))return ch;
			for (TrackerInfo tr : infos) {
				tr.finish(level);

				int i = tr.id;
				long v = tr.tracker;
				if (v != trackers[i]) {
					ch |= true;
					items[i] = null;
					trackers[i] = v;
				}
			}
			return ch;
		}

		@Override
		public long getChangeTracker(Level level) {
			if (lastUpdate != level.getGameTime()) {
				long start = System.nanoTime();
				Object[] keys = getSourceKeys();
				boolean ch = false;
				if (trackers.length != connected.size() || connectionsChanged(keys)) {
					trackers = new long[connected.size()];
					items = new ItemList[connected.size()];
					sourceKeys = keys;
					ch = true;
				}
				if (Config.get().runMultithreaded) {
					ch |= multithreadProcessing(level);
				} else {
					for (int i = 0;i<connected.size();i++) {
						IInventoryAccess ia = connected.get(i);
						long v = ia.tracker().getChangeTracker(level);
						if (v != trackers[i]) {
							ch |= true;
							items[i] = null;
							trackers[i] = v;
						}
					}
				}
				if (ch)lastChange = System.nanoTime();
				lastUpdate = level.getGameTime();
				long elapsedMs = (System.nanoTime() - start) / 1_000_000L;
				if (Config.get().terminalScanDebug || elapsedMs > 250L) {
					StorageMod.LOGGER.info("Tom's Storage tracker scan: connected={}, changed={}, elapsed={}ms, mode={}", connected.size(), ch, elapsedMs, Config.get().runMultithreaded ? "threaded" : "sync");
				}
			}
			return lastChange;
		}

		@Override
		public long refreshNow(Level level) {
			long gameTime = level.getGameTime();
			if (lastChildInvalidation != gameTime) {
				lastChildInvalidation = gameTime;
				connected.forEach(access -> access.tracker().invalidateForImmediateRefresh());
			}
			lastUpdate = Long.MIN_VALUE;
			return getChangeTracker(level);
		}

		@Override
		public void invalidateForImmediateRefresh() {
			lastUpdate = Long.MIN_VALUE;
			lastChildInvalidation = Long.MIN_VALUE;
			connected.forEach(access -> access.tracker().invalidateForImmediateRefresh());
		}

		@Override
		public Stream<StoredItemStack> streamWrappedStacks(boolean parallel) {
			return streamTrackedStacks(parallel).map(TrackedStack::stack);
		}

		@Override
		public Stream<TrackedStack> streamTrackedStacks(boolean parallel) {
			var str = IntStream.range(0, items.length).mapToObj(i -> {
				if (items[i] == null) {
					items[i] = connected.get(i).tracker().streamTrackedStacks(false).collect(Collectors.toCollection(ItemList::new));
				}
				return items[i];
			});
			Set<Object> seenSources = new HashSet<>();
			return str.flatMap(List::stream).filter(s -> s.source() == null || seenSources.add(s.source()));
		}

		@Override
		public long countItems(StoredItemStack filter) {
			return streamTrackedStacks(false).
					map(TrackedStack::stack).
					filter(s -> s.equalItem(filter)).
					mapToLong(StoredItemStack::getQuantity).
					sum();
		}

		@Override
		public InventorySlot findSlot(ItemPredicate filter, boolean findEmpty) {
			for (int i = 0;i<connected.size();i++) {
				IInventoryAccess ia = connected.get(i);
				InventorySlot is = ia.tracker().findSlot(filter, findEmpty);
				if (is != null)return is;
			}
			return null;
		}

		@Override
		public InventorySlot findSlotDest(StoredItemStack forStack) {
			for (int i = 0;i<connected.size();i++) {
				IInventoryAccess ia = connected.get(i);
				InventorySlot is = ia.tracker().findSlotDest(forStack);
				if (is != null)return is;
			}
			return null;
		}

		/**
		 * Multi-inventory scan. Do not pass loop=true into each child tracker:
		 * that restarts every inventory and re-walks the whole network.
		 * Loop only after all children fail. Connected list / trackingKey dedup is unchanged.
		 */
		@Override
		public InventorySlot findSlotAfter(InventorySlot slot, ItemPredicate filter, boolean findEmpty, boolean loop) {
			if (connected.isEmpty())return null;
			if (slot == null) {
				return findSlot(filter, findEmpty);
			}
			for (int i = 0;i<connected.size();i++) {
				InventorySlot is = connected.get(i).tracker().findSlotAfter(slot, filter, findEmpty, false);
				if (is != null)return is;
			}
			if (loop) {
				return findSlot(filter, findEmpty);
			}
			return null;
		}

		@Override
		public InventorySlot findSlotDestAfter(InventorySlot slot, StoredItemStack forStack, boolean loop) {
			if (connected.isEmpty())return null;
			if (slot == null) {
				return findSlotDest(forStack);
			}
			for (int i = 0;i<connected.size();i++) {
				InventorySlot is = connected.get(i).tracker().findSlotDestAfter(slot, forStack, false);
				if (is != null)return is;
			}
			if (loop) {
				return findSlotDest(forStack);
			}
			return null;
		}
	}

	public Collection<IInventoryAccess> getConnected() {
		return connected;
	}
}
