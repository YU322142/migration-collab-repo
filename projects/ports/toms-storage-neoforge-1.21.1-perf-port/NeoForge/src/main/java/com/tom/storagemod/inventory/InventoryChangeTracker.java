package com.tom.storagemod.inventory;

import java.lang.ref.WeakReference;
import java.util.Arrays;
import java.util.stream.Stream;

import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.neoforged.neoforge.items.IItemHandler;

import com.tom.storagemod.inventory.IInventoryAccess.IChangeNotifier;
import com.tom.storagemod.inventory.IInventoryAccess.IInventoryChangeTracker;
import com.tom.storagemod.inventory.IInventoryAccess.IMultiThreadedTracker;
import com.tom.storagemod.inventory.filter.ItemPredicate;

/**
 * Main-thread inventory state with an optional pure off-thread comparison pass.
 *
 * <p>The handler is deliberately never touched by {@link #processOffThread}
 * (or by any object reachable from its argument).  A scan is committed only if
 * the handler, slot shape, filter revision, generation and all live slot
 * contents still match the captured image.  A stale result is discarded and a
 * fresh scan is requested on the next tick.</p>
 */
public class InventoryChangeTracker implements IInventoryChangeTracker,
        IMultiThreadedTracker<InventoryChangeTracker.InventoryImage, InventoryChangeTracker.ScanResult>,
        IChangeNotifier {
    public static final InventoryChangeTracker NULL = new InventoryChangeTracker(null);

    private WeakReference<IItemHandler> itemHandler;
    /** All fields below are owned by the server/main thread. */
    private long lastUpdate = Long.MIN_VALUE;
    private long lastChange;
    private long generation;
    private StoredItemStack[] lastItems = new StoredItemStack[0];

    public InventoryChangeTracker(IItemHandler itemHandler) {
        this.itemHandler = new WeakReference<>(itemHandler);
    }

    @Override
    public long getChangeTracker(Level level) {
        IItemHandler h = itemHandler.get();
        if (h == null)return 0L;
        long gameTime = level.getGameTime();
        if (lastUpdate != gameTime) {
            refreshFilterState(level);
            int slots = h.getSlots();
            boolean change = ensureSlotShape(slots);
            for (int i = 0; i < slots; i++) {
                change |= updateChange(i, h.getStackInSlot(i));
            }
            if (change) {
                lastChange = System.nanoTime();
                generation++;
            }
            lastUpdate = gameTime;
        }
        return lastChange;
    }

    /** Hook for filters which need a world/capability refresh. Main thread only. */
    protected void refreshFilterState(Level level) {
    }

    /** Stable filter token captured and checked around an asynchronous scan. */
    protected long getFilterRevision() {
        return 0L;
    }

    protected boolean checkFilter(ItemStack stack) {
        return checkFilter(new StoredItemStack(stack, stack.getCount()));
    }

    protected boolean checkFilter(StoredItemStack stack) {
        return true;
    }

    protected int getCount(ItemStack is) {
        return is.getCount();
    }

    protected IItemHandler getSlotHandler(IItemHandler def) {
        return def;
    }

    private boolean ensureSlotShape(int slots) {
        if (slots == lastItems.length)return false;
        lastItems = Arrays.copyOf(lastItems, slots);
        generation++;
        return true;
    }

    /** Main-thread-only state update used by synchronous scans and callbacks. */
    private boolean updateChange(int i, ItemStack is) {
        if (!is.isEmpty() && checkFilter(is)) {
            int cnt = getCount(is);
            if (lastItems[i] == null || !ItemStack.isSameItemSameComponents(lastItems[i].getStack(), is)) {
                lastItems[i] = new StoredItemStack(is);
                lastItems[i].setCount(cnt);
                return true;
            } else if (lastItems[i].getQuantity() != cnt) {
                lastItems[i].setCount(cnt);
                return true;
            }
        } else if (lastItems[i] != null) {
            lastItems[i] = null;
            return true;
        }
        return false;
    }

    @Override
    public Stream<StoredItemStack> streamWrappedStacks(boolean parallel) {
        if (itemHandler.get() == null)return Stream.empty();
        return Arrays.stream(lastItems).filter(e -> e != null);
    }

    @Override
    public Stream<IInventoryChangeTracker.TrackedStack> streamTrackedStacks(boolean parallel) {
        IItemHandler h = itemHandler.get();
        if (h == null)return Stream.empty();
        return java.util.stream.IntStream.range(0, lastItems.length)
                .filter(i -> lastItems[i] != null)
                .mapToObj(i -> new IInventoryChangeTracker.TrackedStack(new SlotTrackingKey(h, i), lastItems[i]));
    }

    private static record SlotTrackingKey(IItemHandler handler, int slot) {
    }

    @Override
    public long countItems(StoredItemStack filter) {
        if (itemHandler.get() == null)return 0L;
        long c = 0L;
        for (StoredItemStack is : lastItems) {
            if (is != null && is.equalItem(filter))c += is.getQuantity();
        }
        return c;
    }

    @Override
    public InventorySlot findSlot(ItemPredicate filter, boolean findEmpty) {
        IItemHandler h = itemHandler.get();
        if (h == null)return null;
        for (int i = 0; i < lastItems.length; i++) {
            StoredItemStack is = lastItems[i];
            if (is == null) {
                if (findEmpty && isLiveEmpty(h, i))return new InventorySlot(getSlotHandler(h), this, i);
                continue;
            }
            if (filter.test(is) && isLiveMatch(h, i, filter))
                return new InventorySlot(getSlotHandler(h), this, i);
        }
        return null;
    }

    private boolean isLiveEmpty(IItemHandler handler, int slot) {
        ItemStack live = handler.getStackInSlot(slot);
        return live.isEmpty() || !checkFilter(live) || getCount(live) <= 0;
    }

    private boolean isLiveMatch(IItemHandler handler, int slot, ItemPredicate filter) {
        ItemStack live = handler.getStackInSlot(slot);
        if (live.isEmpty() || !checkFilter(live))return false;
        int count = getCount(live);
        return count > 0 && filter.test(new StoredItemStack(live, count));
    }

    /**
     * Capture every value needed by the worker on the main thread.  ItemStack
     * instances returned by a capability are copied before leaving this method;
     * the worker therefore cannot mutate a live handler or a shared stack.
     */
    @Override
    public InventoryImage prepForOffThread(Level level) {
        long gameTime = level.getGameTime();
        if (lastUpdate == gameTime)return null;
        refreshFilterState(level);
        IItemHandler h = itemHandler.get();
        if (h == null)return null;
        int slots = h.getSlots();
        boolean shapeChanged = ensureSlotShape(slots);
        SnapshotSlot[] snapshot = new SnapshotSlot[slots];
        for (int i = 0; i < slots; i++) {
            ItemStack live = h.getStackInSlot(i);
            ItemStack copy = live == null ? ItemStack.EMPTY : live.copy();
            boolean accepted = !copy.isEmpty() && checkFilter(copy);
            int count = accepted ? getCount(copy) : 0;
            snapshot[i] = new SnapshotSlot(copy, count, accepted);
        }
        return new InventoryImage(h, generation, getFilterRevision(), gameTime,
                shapeChanged, lastChange, snapshot, copyArray(lastItems));
    }

    /**
     * Pure worker operation. It compares copied slot images only and returns a
     * delta; no handler, level, filter, or mutable tracker state is accessed.
     */
    @Override
    public ScanResult processOffThread(InventoryImage image) {
        if (image == null)return null;
        StoredItemStack[] next = new StoredItemStack[image.slots.length];
        boolean changed = image.shapeChanged;
        for (int i = 0; i < image.slots.length; i++) {
            SnapshotSlot slot = image.slots[i];
            StoredItemStack value = null;
            if (slot.accepted && !slot.stack.isEmpty()) {
                ItemStack normalized = slot.stack.copy();
                normalized.setCount(1);
                value = new StoredItemStack(normalized, slot.count);
            }
            next[i] = value;
            if (!sameTracked(image.baseline[i], value))changed = true;
        }
        long change = changed ? System.nanoTime() : image.previousChange;
        return new ScanResult(image, next, changed, change);
    }

    /**
     * Main-thread commit with optimistic validation. Any mismatch leaves the
     * previous state intact and forces a retry on the next tick.
     */
    @Override
    public long finishOffThreadProcess(Level level, ScanResult result) {
        if (result == null)return lastChange;
        InventoryImage image = result.image;
        IItemHandler h = itemHandler.get();
        refreshFilterState(level);
        boolean valid = h != null
                && h == image.handler
                && generation == image.generation
                && level.getGameTime() == image.gameTime
                && getFilterRevision() == image.filterRevision
                && h.getSlots() == image.slots.length
                && liveMatchesSnapshot(h, image.slots);
        if (!valid) {
            lastUpdate = Long.MIN_VALUE;
            generation++;
            return lastChange;
        }
        lastItems = copyArray(result.nextItems);
        if (result.changed) {
            lastChange = result.change;
            generation++;
        }
        lastUpdate = level.getGameTime();
        return lastChange;
    }

    private boolean liveMatchesSnapshot(IItemHandler handler, SnapshotSlot[] snapshot) {
        for (int i = 0; i < snapshot.length; i++) {
            ItemStack live = handler.getStackInSlot(i);
            ItemStack expected = snapshot[i].stack;
            if (live == null || expected == null)return false;
            if (live.isEmpty() != expected.isEmpty())return false;
            if (live.isEmpty())continue;
            if (live.getCount() != expected.getCount()
                    || !ItemStack.isSameItemSameComponents(live, expected))return false;
        }
        return true;
    }

    private static boolean sameTracked(StoredItemStack a, StoredItemStack b) {
        if (a == b)return true;
        if (a == null || b == null)return false;
        return a.getQuantity() == b.getQuantity()
                && ItemStack.isSameItemSameComponents(a.getStack(), b.getStack());
    }

    private static StoredItemStack copyTracked(StoredItemStack value) {
        if (value == null)return null;
        ItemStack stack = value.getStack().copy();
        stack.setCount(1);
        return new StoredItemStack(stack, value.getQuantity());
    }

    private static StoredItemStack[] copyArray(StoredItemStack[] values) {
        StoredItemStack[] copy = new StoredItemStack[values.length];
        for (int i = 0; i < values.length; i++)copy[i] = copyTracked(values[i]);
        return copy;
    }

    @Override
    public void onSlotChanged(InventorySlot slot) {
        if (slot == null || slot.getId() < 0)return;
        if (!slot.belongsTo(this))return;
        IItemHandler h = itemHandler.get();
        if (h == null)return;
        int id = slot.getId();
        if (id < lastItems.length && updateChange(id, slot.getStack())) {
            lastChange = System.nanoTime();
            generation++;
        }
    }

    public void refresh(IItemHandler handler) {
        if (itemHandler.get() == handler)return;
        itemHandler = new WeakReference<>(handler);
        invalidate();
    }

    @Override
    public void invalidateForImmediateRefresh() {
        lastUpdate = Long.MIN_VALUE;
        generation++;
    }

    public void invalidate() {
        lastUpdate = Long.MIN_VALUE;
        lastChange = System.nanoTime();
        lastItems = new StoredItemStack[0];
        generation++;
    }

    @Override
    public InventorySlot findSlotDest(StoredItemStack forStack) {
        IItemHandler h = itemHandler.get();
        if (h == null)return null;
        if (!checkFilter(forStack))return null;
        for (int i = 0; i < lastItems.length; i++) {
            StoredItemStack is = lastItems[i];
            if (is == null && !h.isItemValid(i, forStack.getStack()))continue;
            if (is == null || is.equalItem(forStack)) {
                int rem = h.insertItem(i, forStack.getActualStack(), true).getCount();
                if (rem < forStack.getQuantity())return new InventorySlot(getSlotHandler(h), this, i);
            }
        }
        return null;
    }

    @Override
    public InventorySlot findSlotAfter(InventorySlot slot, ItemPredicate filter, boolean findEmpty, boolean loop) {
        if (slot == null)return findSlot(filter, findEmpty);
        IItemHandler h = itemHandler.get();
        if (h == null)return null;
        if (h.getSlots() <= slot.getId() + 1)return loop ? findSlot(filter, findEmpty) : null;
        for (int i = slot.getId() + 1; i < lastItems.length; i++) {
            StoredItemStack is = lastItems[i];
            if (is == null) {
                if (findEmpty && isLiveEmpty(h, i))return new InventorySlot(getSlotHandler(h), this, i);
                continue;
            }
            if (filter.test(is) && isLiveMatch(h, i, filter))return new InventorySlot(getSlotHandler(h), this, i);
        }
        return null;
    }

    @Override
    public InventorySlot findSlotDestAfter(InventorySlot slot, StoredItemStack forStack, boolean loop) {
        if (slot == null)return findSlotDest(forStack);
        IItemHandler h = itemHandler.get();
        if (h == null)return null;
        if (!checkFilter(forStack))return null;
        if (h.getSlots() <= slot.getId() + 1)return loop ? findSlotDest(forStack) : null;
        for (int i = slot.getId() + 1; i < lastItems.length; i++) {
            StoredItemStack is = lastItems[i];
            if (is == null && !h.isItemValid(i, forStack.getStack()))continue;
            if (is == null || is.equalItem(forStack)) {
                int rem = h.insertItem(i, forStack.getActualStack(), true).getCount();
                if (rem < forStack.getQuantity())return new InventorySlot(getSlotHandler(h), this, i);
            }
        }
        return null;
    }

    /** Immutable copied slot image consumed by workers. */
    static final class InventoryImage {
        final IItemHandler handler;
        final long generation;
        final long filterRevision;
        final long gameTime;
        final boolean shapeChanged;
        final long previousChange;
        final SnapshotSlot[] slots;
        final StoredItemStack[] baseline;

        InventoryImage(IItemHandler handler, long generation, long filterRevision, long gameTime,
                boolean shapeChanged, long previousChange, SnapshotSlot[] slots, StoredItemStack[] baseline) {
            this.handler = handler;
            this.generation = generation;
            this.filterRevision = filterRevision;
            this.gameTime = gameTime;
            this.shapeChanged = shapeChanged;
            this.previousChange = previousChange;
            this.slots = slots;
            this.baseline = baseline;
        }
    }

    static final class SnapshotSlot {
        final ItemStack stack;
        final int count;
        final boolean accepted;

        SnapshotSlot(ItemStack stack, int count, boolean accepted) {
            this.stack = stack;
            this.count = count;
            this.accepted = accepted;
        }
    }

    /** Worker result. It contains no live handler calls or mutable tracker refs. */
    static final class ScanResult {
        final InventoryImage image;
        final StoredItemStack[] nextItems;
        final boolean changed;
        final long change;

        ScanResult(InventoryImage image, StoredItemStack[] nextItems, boolean changed, long change) {
            this.image = image;
            this.nextItems = nextItems;
            this.changed = changed;
            this.change = change;
        }
    }
}
