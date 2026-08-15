package com.tom.storagemod.util;

import java.util.EnumSet;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Random;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;

import com.tom.storagemod.util.CraftingIngredientPlanner.Available;

public class CraftingIngredientPlannerRegression {
	private static enum ItemToken {
		A, B, C, UNUSED
	}

	public static void main(String[] args) {
		overlappingAlternativesAreReassigned();
		repeatedIngredientRespectsQuantity();
		threeWayOverlapFindsCompletePlan();
		capacityCandidateCanBeReassigned();
		manyRelevantVariantsRemainBounded();
		completePrefixSkipsLargeTail();
		hallConditionFailureIsRejected();
		expiredDeadlineSkipsPredicates();
		randomPlansMatchBruteForce();
		irrelevantLargeSupplyIsIgnored();
		emptyRecipeHasEmptyPlan();
		System.out.println("Crafting ingredient planner regression checks passed");
	}

	private static void overlappingAlternativesAreReassigned() {
		List<Predicate<ItemToken>> ingredients = List.of(accepts(ItemToken.A, ItemToken.B), accepts(ItemToken.A));
		var plan = CraftingIngredientPlanner.findPlan(ingredients,
				List.of(new Available<>(ItemToken.A, 1), new Available<>(ItemToken.B, 1)));
		check(plan.isPresent(), "overlapping alternatives should have a complete plan");
		check(plan.get().equals(List.of(ItemToken.B, ItemToken.A)), "planner must reserve A for the A-only ingredient");
	}

	private static void repeatedIngredientRespectsQuantity() {
		List<Predicate<ItemToken>> ingredients = List.of(accepts(ItemToken.A), accepts(ItemToken.A));
		Optional<List<ItemToken>> missing = CraftingIngredientPlanner.findPlan(ingredients,
				List.of(new Available<>(ItemToken.A, 1)));
		check(missing.isEmpty(), "one A must not satisfy two recipe slots");

		Optional<List<ItemToken>> enough = CraftingIngredientPlanner.findPlan(ingredients,
				List.of(new Available<>(ItemToken.A, 2)));
		check(enough.isPresent(), "two A items should satisfy two recipe slots");
		check(enough.get().equals(List.of(ItemToken.A, ItemToken.A)), "both repeated slots should receive A");
	}

	private static void threeWayOverlapFindsCompletePlan() {
		List<Predicate<ItemToken>> ingredients = List.of(accepts(ItemToken.A, ItemToken.B),
				accepts(ItemToken.B, ItemToken.C), accepts(ItemToken.A));
		List<Available<ItemToken>> available = List.of(new Available<>(ItemToken.A, 1),
				new Available<>(ItemToken.B, 1), new Available<>(ItemToken.C, 1));
		var plan = CraftingIngredientPlanner.findPlan(ingredients, available);
		check(plan.isPresent(), "three-way overlap should have a complete plan");
		for (int i = 0;i < ingredients.size();i++) {
			check(ingredients.get(i).test(plan.get().get(i)), "selected item does not satisfy ingredient " + i);
		}
		for (ItemToken item : ItemToken.values()) {
			long used = plan.get().stream().filter(item::equals).count();
			long supplied = available.stream().filter(a -> a.item() == item).mapToLong(Available::count).sum();
			check(used <= supplied, "planner exceeded supply for " + item);
		}
	}

	private static void capacityCandidateCanBeReassigned() {
		List<Predicate<ItemToken>> ingredients = List.of(accepts(ItemToken.A, ItemToken.B),
				accepts(ItemToken.A), accepts(ItemToken.A));
		var plan = CraftingIngredientPlanner.findPlan(ingredients,
				List.of(new Available<>(ItemToken.A, 2), new Available<>(ItemToken.B, 1)));
		check(plan.isPresent(), "a counted candidate must participate in augmenting-path reassignment");
		check(plan.get().equals(List.of(ItemToken.B, ItemToken.A, ItemToken.A)),
				"the flexible slot must move to B while both A units stay available");
	}

	private static void manyRelevantVariantsRemainBounded() {
		List<Available<Integer>> available = new ArrayList<>();
		for (int i = 0;i < 100_000;i++)available.add(new Available<>(i, 9));
		List<Predicate<Integer>> ingredients = new ArrayList<>();
		for (int i = 0;i < 9;i++)ingredients.add(value -> true);
		var plan = CraftingIngredientPlanner.findPlan(ingredients, available);
		check(plan.isPresent() && plan.get().size() == 9,
				"large relevant candidate sets must retain counted capacity without unit expansion");
	}

	private static void completePrefixSkipsLargeTail() {
		List<Predicate<ItemToken>> ingredients = new ArrayList<>();
		for (int i = 0;i < 9;i++) {
			ingredients.add(item -> {
				if (item == ItemToken.UNUSED)throw new AssertionError("complete plan must stop candidate materialization");
				return item == ItemToken.A;
			});
		}
		var plan = CraftingIngredientPlanner.findPlan(ingredients,
				List.of(new Available<>(ItemToken.A, 9),
						new Available<>(ItemToken.UNUSED, Integer.MAX_VALUE)));
		check(plan.isPresent() && plan.get().equals(java.util.Collections.nCopies(9, ItemToken.A)),
				"a complete prefix must return without materializing the remaining warehouse");
	}

	private static void hallConditionFailureIsRejected() {
		List<Predicate<ItemToken>> ingredients = List.of(accepts(ItemToken.A),
				accepts(ItemToken.A), accepts(ItemToken.B, ItemToken.C));
		var plan = CraftingIngredientPlanner.findPlan(ingredients,
				List.of(new Available<>(ItemToken.A, 1), new Available<>(ItemToken.B, 1),
						new Available<>(ItemToken.C, 1)));
		check(plan.isEmpty(), "insufficient capacity for an ingredient subset must be rejected");
	}

	private static void expiredDeadlineSkipsPredicates() {
		AtomicInteger calls = new AtomicInteger();
		Predicate<ItemToken> predicate = item -> {
			calls.incrementAndGet();
			return true;
		};
		var result = CraftingIngredientPlanner.findPlanResult(List.of(predicate),
				List.of(new Available<>(ItemToken.A, 1)), System.nanoTime() - 1);
		check(result.status() == CraftingIngredientPlanner.PlanningStatus.TIMEOUT,
				"an expired planning budget must be reported as a timeout");
		check(calls.get() == 0, "an expired planning budget must not invoke predicates");
	}

	private static void randomPlansMatchBruteForce() {
		Random random = new Random(0x544f4d53L);
		for (int trial = 0;trial < 4_000;trial++) {
			int ingredientCount = 1 + random.nextInt(7);
			int candidateCount = 1 + random.nextInt(7);
			boolean[][] matches = new boolean[candidateCount][ingredientCount];
			int[] capacities = new int[candidateCount];
			List<Available<Integer>> available = new ArrayList<>(candidateCount);
			for (int candidate = 0;candidate < candidateCount;candidate++) {
				capacities[candidate] = random.nextInt(4);
				available.add(new Available<>(candidate, capacities[candidate]));
				for (int ingredient = 0;ingredient < ingredientCount;ingredient++) {
					matches[candidate][ingredient] = random.nextBoolean();
				}
			}
			List<Predicate<Integer>> ingredients = new ArrayList<>(ingredientCount);
			for (int ingredient = 0;ingredient < ingredientCount;ingredient++) {
				int ingredientIndex = ingredient;
				ingredients.add(candidate -> matches[candidate][ingredientIndex]);
			}

			var plan = CraftingIngredientPlanner.findPlan(ingredients, available);
			boolean solvable = bruteForceSolvable(0, matches, capacities.clone());
			check(plan.isPresent() == solvable, "planner disagrees with brute force on trial " + trial);
			if (plan.isPresent())validatePlan(plan.get(), matches, capacities);
		}
	}

	private static boolean bruteForceSolvable(int ingredient, boolean[][] matches, int[] remaining) {
		if (ingredient == matches[0].length)return true;
		for (int candidate = 0;candidate < matches.length;candidate++) {
			if (!matches[candidate][ingredient] || remaining[candidate] == 0)continue;
			remaining[candidate]--;
			if (bruteForceSolvable(ingredient + 1, matches, remaining))return true;
			remaining[candidate]++;
		}
		return false;
	}

	private static void validatePlan(List<Integer> plan, boolean[][] matches, int[] capacities) {
		int[] used = new int[capacities.length];
		for (int ingredient = 0;ingredient < plan.size();ingredient++) {
			int candidate = plan.get(ingredient);
			check(matches[candidate][ingredient], "selected candidate does not match ingredient");
			used[candidate]++;
		}
		for (int candidate = 0;candidate < capacities.length;candidate++) {
			check(used[candidate] <= capacities[candidate], "selected candidate exceeds capacity");
		}
	}

	private static void irrelevantLargeSupplyIsIgnored() {
		var plan = CraftingIngredientPlanner.findPlan(List.of(accepts(ItemToken.A)),
				List.of(new Available<>(ItemToken.UNUSED, Integer.MAX_VALUE), new Available<>(ItemToken.A, 1)));
		check(plan.isPresent() && plan.get().equals(List.of(ItemToken.A)),
				"an irrelevant large count must not be expanded or selected");
	}

	private static void emptyRecipeHasEmptyPlan() {
		var plan = CraftingIngredientPlanner.<ItemToken>findPlan(List.of(),
				List.of(new Available<>(ItemToken.A, Integer.MAX_VALUE)));
		check(plan.isPresent() && plan.get().isEmpty(), "an empty recipe should have an empty plan");
	}

	private static Predicate<ItemToken> accepts(ItemToken first, ItemToken... rest) {
		EnumSet<ItemToken> accepted = EnumSet.of(first, rest);
		return accepted::contains;
	}

	private static void check(boolean condition, String message) {
		if (!condition)throw new AssertionError(message);
	}
}
