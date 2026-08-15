package com.tom.storagemod.inventory;

import java.util.stream.Stream;

import net.minecraft.world.level.Level;

import com.tom.storagemod.inventory.IInventoryAccess.IInventoryChangeTracker;
import com.tom.storagemod.inventory.IInventoryAccess.IMultiThreadedTracker;
import com.tom.storagemod.inventory.filter.ItemPredicate;

/** Pure worker-side regression checks; no Level or capability is touched. */
public final class InventoryChangeTrackerRegression {
    public static void main(String[] args) {
        testWorkerDoesNotMutateBaseline();
        testWorkerBuildsIndependentDelta();
        testDelegateSwapRejectsOldResult();
        System.out.println("Inventory change tracker regression checks passed");
    }

    private static void testDelegateSwapRejectsOldResult() {
        IInventoryChangeTracker.Delegate delegate = new IInventoryChangeTracker.Delegate();
        FakeTracker first = new FakeTracker(10L);
        FakeTracker second = new FakeTracker(20L);
        delegate.setDelegate(first);
        Object image = delegate.prepForOffThread(null);
        delegate.setDelegate(second);
        Object result = delegate.processOffThread(image);
        check(first.processed == 1 && second.processed == 0, "worker used a replacement delegate");
        long value = delegate.finishOffThreadProcess(null, result);
        check(first.finished == 0, "old delegate result was partially committed");
        check(second.invalidated == 1 && second.scanned == 1, "replacement delegate was not refreshed");
        check(value == 20L, "replacement delegate tracker value was not returned");
    }

    private static void testWorkerDoesNotMutateBaseline() {
        InventoryChangeTracker tracker = new InventoryChangeTracker(null);
        InventoryChangeTracker.SnapshotSlot[] slots = {
                new InventoryChangeTracker.SnapshotSlot(null, 0, false)
        };
        StoredItemStack[] baseline = {null};
        InventoryChangeTracker.InventoryImage image = new InventoryChangeTracker.InventoryImage(
                null, 7L, 11L, 42L, false, 5L, slots, copy(baseline));
        InventoryChangeTracker.ScanResult result = tracker.processOffThread(image);
        check(!result.changed, "unchanged empty slot reported as changed");
        check(baseline[0] == null, "worker changed baseline");
    }

    private static void testWorkerBuildsIndependentDelta() {
        InventoryChangeTracker tracker = new InventoryChangeTracker(null);
        InventoryChangeTracker.SnapshotSlot[] slots = {
                new InventoryChangeTracker.SnapshotSlot(null, 0, false)
        };
        StoredItemStack[] baseline = {null};
        InventoryChangeTracker.InventoryImage image = new InventoryChangeTracker.InventoryImage(
                null, 1L, 0L, 1L, true, 9L, slots, baseline);
        InventoryChangeTracker.ScanResult result = tracker.processOffThread(image);
        check(result.changed, "slot-shape delta was not reported as changed");
        check(result.nextItems[0] == null, "empty slot unexpectedly gained a stack");
        check(slots[0].stack == null, "worker changed immutable input");
    }

    private static StoredItemStack[] copy(StoredItemStack[] source) {
        StoredItemStack[] result = new StoredItemStack[source.length];
        for (int i = 0; i < source.length; i++) {
            if (source[i] != null)result[i] = new StoredItemStack(source[i].getStack().copy(), source[i].getQuantity());
        }
        return result;
    }

    private static void check(boolean condition, String message) {
        if (!condition)throw new AssertionError(message);
    }

    private static final class FakeTracker implements IInventoryChangeTracker, IMultiThreadedTracker<Object, Object> {
        private final long value;
        int processed, finished, invalidated, scanned;

        FakeTracker(long value) {
            this.value = value;
        }

        @Override
        public long getChangeTracker(Level level) {
            scanned++;
            return value;
        }

        @Override
        public void invalidateForImmediateRefresh() {
            invalidated++;
        }

        @Override
        public Object prepForOffThread(Level level) {
            return new Object();
        }

        @Override
        public Object processOffThread(Object image) {
            processed++;
            return image;
        }

        @Override
        public long finishOffThreadProcess(Level level, Object result) {
            finished++;
            return value;
        }

        @Override
        public Stream<StoredItemStack> streamWrappedStacks(boolean parallel) {
            return Stream.empty();
        }

        @Override
        public long countItems(StoredItemStack filter) {
            return 0L;
        }

        @Override
        public InventorySlot findSlot(ItemPredicate filter, boolean findEmpty) {
            return null;
        }

        @Override
        public InventorySlot findSlotAfter(InventorySlot slot, ItemPredicate filter, boolean findEmpty, boolean loop) {
            return null;
        }

        @Override
        public InventorySlot findSlotDest(StoredItemStack forStack) {
            return null;
        }

        @Override
        public InventorySlot findSlotDestAfter(InventorySlot slot, StoredItemStack forStack, boolean loop) {
            return null;
        }
    }
}
