package com.tom.storagemod.inventory;

import java.util.ArrayList;
import java.util.List;

public final class InventoryDeduplicatorRegression {
	private record Candidate(String name, Object trackingKey, Object rootKey, boolean nested) {}

	public static void main(String[] args) {
		testCreateMemberFlood();
		testResolvedRootFallback();
		testPriorityAndDistinctInventories();
		testNestedNetworkSkip();
		System.out.println("InventoryDeduplicator regression checks passed");
	}

	private static void testCreateMemberFlood() {
		List<Candidate> candidates = new ArrayList<>();
		for (int i = 0;i < 2068;i++) {
			candidates.add(new Candidate("vault-member-" + i, "controller-A", "root-" + i, false));
		}
		int[] rootResolutions = {0};
		var result = InventoryDeduplicator.select(candidates, "self", "self-root",
				Candidate::trackingKey, candidate -> {
					rootResolutions[0]++;
					return candidate;
				}, (candidate, root) -> candidate.rootKey(), Candidate::nested);
		check(result.selected().size() == 1, "2,068 Create members must select one inventory");
		check(rootResolutions[0] == 1, "expensive root resolution must run once per controller key");
		check(result.trackingDuplicateCount() == 2067, "all duplicate members must be counted");
	}

	private static void testResolvedRootFallback() {
		Object sharedRoot = new Object();
		List<Candidate> candidates = List.of(
				new Candidate("direct", "direct-key", sharedRoot, false),
				new Candidate("proxy", "proxy-key", sharedRoot, false));
		int[] rootResolutions = {0};
		var result = InventoryDeduplicator.select(candidates, "self", "self-root",
				Candidate::trackingKey, candidate -> {
					rootResolutions[0]++;
					return candidate.rootKey();
				}, (candidate, root) -> root, root -> false);
		check(result.selected().size() == 1,
				"different logical keys with one physical root must stay deduplicated");
		check(result.rootDuplicateCount() == 1,
				"physical-root fallback must reject the proxy alias");
		check(rootResolutions[0] == 2,
				"physical-root fallback must inspect both unique logical keys");
	}

	private static void testPriorityAndDistinctInventories() {
		Candidate high = new Candidate("high", "same-key", "root-high", false);
		Candidate low = new Candidate("low", "same-key", "root-low", false);
		Candidate other = new Candidate("other", "other-key", "root-other", false);
		var result = InventoryDeduplicator.select(List.of(high, low, other),
				"self", "self-root", Candidate::trackingKey, Candidate::rootKey,
				(candidate, root) -> root, root -> false);
		check(result.selected().equals(List.of(high, other)),
				"first/high-priority representative and distinct inventory must survive");
	}

	private static void testNestedNetworkSkip() {
		Candidate nested = new Candidate("nested", "nested-key", "nested-root", true);
		var result = InventoryDeduplicator.select(List.of(nested), "self", "self-root",
				Candidate::trackingKey, candidate -> candidate,
				(candidate, root) -> candidate.rootKey(), Candidate::nested);
		check(result.selected().isEmpty() && result.skippedRootCount() == 1,
				"nested multi-inventory networks must still be rejected");
	}

	private static void check(boolean condition, String message) {
		if (!condition)throw new AssertionError(message);
	}
}
