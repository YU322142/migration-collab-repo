package com.tom.storagemod.inventory;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;

/**
 * Two-stage inventory candidate selection. The inexpensive logical key is
 * evaluated before resolving a platform handler; the resolved physical-root key
 * keeps the original de-duplication semantics as a second line of defence.
 */
final class InventoryDeduplicator {
	private InventoryDeduplicator() {}

	static <A, R> Result<A> select(Iterable<A> candidates,
			Object selfTrackingKey, Object selfRootKey,
			Function<A, Object> trackingKeyGetter,
			Function<A, R> rootResolver,
			BiFunction<A, R, Object> rootKeyGetter,
			Predicate<R> skipRoot) {
		Set<Object> trackingKeys = new HashSet<>();
		trackingKeys.add(selfTrackingKey);
		Set<Object> rootKeys = new HashSet<>();
		rootKeys.add(selfRootKey);
		List<A> selected = new ArrayList<>();
		int candidatesSeen = 0;
		int trackingDuplicates = 0;
		int rootDuplicates = 0;
		int skippedRoots = 0;

		for (A candidate : candidates) {
			candidatesSeen++;
			Object trackingKey = trackingKeyGetter.apply(candidate);
			if (trackingKeys.contains(trackingKey)) {
				trackingDuplicates++;
				continue;
			}

			R root = rootResolver.apply(candidate);
			trackingKeys.add(trackingKey);
			if (skipRoot.test(root)) {
				skippedRoots++;
				continue;
			}

			Object rootKey = rootKeyGetter.apply(candidate, root);
			if (!rootKeys.add(rootKey)) {
				rootDuplicates++;
				continue;
			}
			selected.add(candidate);
		}

		return new Result<>(List.copyOf(selected), candidatesSeen,
				trackingDuplicates, rootDuplicates, skippedRoots);
	}

	static record Result<A>(List<A> selected, int candidateCount,
			int trackingDuplicateCount, int rootDuplicateCount, int skippedRootCount) {}
}
