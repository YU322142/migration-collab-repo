package com.tom.storagemod.inventory.filter;

import com.tom.storagemod.inventory.StoredItemStack;

public interface ItemPredicate {
	boolean test(StoredItemStack stack);

	default void updateState() {}

	/** Monotonic token for dynamic predicate state refreshed on the main thread. */
	default long getRevision() {
		return 0L;
	}
}
