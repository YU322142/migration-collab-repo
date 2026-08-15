package com.tom.storagemod.util;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Predicate;

import net.minecraft.core.component.DataComponents;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.Ingredient;

import com.tom.storagemod.inventory.StoredItemStack;

/**
 * Allocates counted candidates to ingredient predicates with a global matching
 * pass. This avoids the false negatives produced by choosing the first match for
 * each ingredient independently.
 */
public final class CraftingIngredientPlanner {
	public static final long DEFAULT_PLANNING_NANOS = 10_000_000L;

	private CraftingIngredientPlanner() {
	}

	public static record Available<T>(T item, int count) {
	}

	public static enum PlanningStatus {
		FOUND, NO_PLAN, TIMEOUT
	}

	public static record PlanningResult<T>(PlanningStatus status, List<T> selected) {
		public Optional<List<T>> asOptional() {
			return status == PlanningStatus.FOUND ? Optional.of(selected) : Optional.empty();
		}
	}

	public static <T> Optional<List<T>> findPlan(List<? extends Predicate<T>> ingredients,
			List<Available<T>> available) {
		return findPlanResult(ingredients, available, Long.MAX_VALUE).asOptional();
	}

	public static <T> Optional<List<T>> findPlan(List<? extends Predicate<T>> ingredients,
			List<Available<T>> available, long deadlineNanos) {
		return findPlanResult(ingredients, available, deadlineNanos).asOptional();
	}

	public static <T> PlanningResult<T> findPlanResult(List<? extends Predicate<T>> ingredients,
			List<Available<T>> available, long deadlineNanos) {
		Objects.requireNonNull(ingredients, "ingredients");
		Objects.requireNonNull(available, "available");
		if (ingredients.isEmpty())return found(List.of());

		Budget budget = new Budget(deadlineNanos);
		if (budget.expired())return timeout();
		Matcher<T> matcher = new Matcher<>(ingredients, budget);
		for (Available<T> entry : available) {
			if (budget.expired())return timeout();
			Objects.requireNonNull(entry, "available entry");
			SearchResult result = matcher.add(entry.item(), entry.count());
			if (result == SearchResult.TIMEOUT)return timeout();
			if (result == SearchResult.FOUND)return found(matcher.selected());
		}
		return noPlan();
	}

	public static Optional<List<ItemStack>> findItemPlan(List<Ingredient> ingredients,
			Iterable<StoredItemStack> stored, Iterable<ItemStack> playerItems) {
		return findItemPlanResult(ingredients, stored, playerItems, Map.of(),
				defaultPlanningDeadline()).asOptional();
	}

	public static Optional<List<ItemStack>> findItemPlan(List<Ingredient> ingredients,
			Iterable<StoredItemStack> stored, Iterable<ItemStack> playerItems,
			Map<StoredItemStack, Integer> capacityLimits) {
		return findItemPlanResult(ingredients, stored, playerItems, capacityLimits,
				defaultPlanningDeadline()).asOptional();
	}

	public static Optional<List<ItemStack>> findItemPlan(List<Ingredient> ingredients,
			Iterable<StoredItemStack> stored, Iterable<ItemStack> playerItems,
			Map<StoredItemStack, Integer> capacityLimits, long deadlineNanos) {
		return findItemPlanResult(ingredients, stored, playerItems, capacityLimits,
				deadlineNanos).asOptional();
	}

	public static PlanningResult<ItemStack> findItemPlanResult(List<Ingredient> ingredients,
			Iterable<StoredItemStack> stored, Iterable<ItemStack> playerItems,
			Map<StoredItemStack, Integer> capacityLimits, long deadlineNanos) {
		Objects.requireNonNull(ingredients, "ingredients");
		Objects.requireNonNull(stored, "stored");
		Objects.requireNonNull(playerItems, "playerItems");
		Objects.requireNonNull(capacityLimits, "capacityLimits");
		if (ingredients.isEmpty())return found(List.of());

		Budget budget = new Budget(deadlineNanos);
		if (budget.expired())return timeout();
		List<Predicate<ItemStack>> tests = new ArrayList<>(ingredients.size());
		for (Ingredient ingredient : ingredients) {
			if (budget.expired())return timeout();
			tests.add(Objects.requireNonNull(ingredient, "ingredient")::test);
		}

		int needed = ingredients.size();
		Matcher<ItemStack> matcher = new Matcher<>(tests, budget);
		Map<StoredItemStack, Integer> admittedCounts = new HashMap<>();
		for (StoredItemStack stack : stored) {
			if (budget.expired())return timeout();
			SearchResult result = account(matcher, admittedCounts, capacityLimits,
					stack.getStack(), stack.getQuantity(), needed, budget);
			if (result == SearchResult.TIMEOUT)return timeout();
			if (result == SearchResult.FOUND)return found(matcher.selected());
		}
		for (ItemStack stack : playerItems) {
			if (budget.expired())return timeout();
			SearchResult result = account(matcher, admittedCounts, capacityLimits,
					stack, stack.getCount(), needed, budget);
			if (result == SearchResult.TIMEOUT)return timeout();
			if (result == SearchResult.FOUND)return found(matcher.selected());
		}
		return noPlan();
	}

	private static SearchResult account(Matcher<ItemStack> matcher,
			Map<StoredItemStack, Integer> admittedCounts,
			Map<StoredItemStack, Integer> capacityLimits, ItemStack stack, long count,
			int needed, Budget budget) {
		if (budget.expired())return SearchResult.TIMEOUT;
		if (!isUsableForCrafting(stack) || count <= 0)return SearchResult.NO_PLAN;

		StoredItemStack key = new StoredItemStack(stack.copyWithCount(1));
		int limit = Math.min(needed, Math.max(0, capacityLimits.getOrDefault(key, needed)));
		int admitted = admittedCounts.getOrDefault(key, 0);
		int addition = (int) Math.min(count, Math.max(0, limit - admitted));
		if (addition <= 0)return SearchResult.NO_PLAN;
		admittedCounts.put(key, admitted + addition);
		return matcher.add(key.getStack().copyWithCount(1), addition);
	}

	public static long defaultPlanningDeadline() {
		return System.nanoTime() + DEFAULT_PLANNING_NANOS;
	}

	private static boolean isUsableForCrafting(ItemStack stack) {
		return !stack.isEmpty() && !stack.isDamaged() && !stack.isEnchanted()
				&& !stack.has(DataComponents.CUSTOM_NAME);
	}

	private static <T> PlanningResult<T> found(List<T> selected) {
		return new PlanningResult<>(PlanningStatus.FOUND, List.copyOf(selected));
	}

	private static <T> PlanningResult<T> noPlan() {
		return new PlanningResult<>(PlanningStatus.NO_PLAN, List.of());
	}

	private static <T> PlanningResult<T> timeout() {
		return new PlanningResult<>(PlanningStatus.TIMEOUT, List.of());
	}

	private static final class Matcher<T> {
		private final List<Predicate<T>> ingredients;
		private final Budget budget;
		private final List<Candidate<T>> candidates = new ArrayList<>();
		private final int[] candidateForIngredient;
		private int assignedCount;

		private Matcher(List<? extends Predicate<T>> ingredients, Budget budget) {
			this.ingredients = new ArrayList<>(ingredients.size());
			for (Predicate<T> ingredient : ingredients) {
				this.ingredients.add(Objects.requireNonNull(ingredient, "ingredient predicate"));
			}
			this.budget = budget;
			candidateForIngredient = new int[ingredients.size()];
			Arrays.fill(candidateForIngredient, -1);
		}

		private SearchResult add(T item, int count) {
			if (count <= 0)return SearchResult.NO_PLAN;
			if (budget.expired())return SearchResult.TIMEOUT;

			boolean[] matches = new boolean[ingredients.size()];
			int matchingIngredients = 0;
			for (int ingredient = 0;ingredient < ingredients.size();ingredient++) {
				if (budget.expired())return SearchResult.TIMEOUT;
				if (ingredients.get(ingredient).test(item)) {
					matches[ingredient] = true;
					matchingIngredients++;
				}
			}
			if (budget.expired())return SearchResult.TIMEOUT;
			if (matchingIngredients == 0)return SearchResult.NO_PLAN;

			candidates.add(new Candidate<>(item, matches,
					Math.min(count, matchingIngredients)));
			for (int ingredient = 0;ingredient < candidateForIngredient.length;ingredient++) {
				if (candidateForIngredient[ingredient] >= 0)continue;
				SearchResult result = assign(ingredient, new boolean[candidates.size()]);
				if (result == SearchResult.TIMEOUT)return SearchResult.TIMEOUT;
				if (result == SearchResult.FOUND)assignedCount++;
			}
			return assignedCount == candidateForIngredient.length
					? SearchResult.FOUND : SearchResult.NO_PLAN;
		}

		private SearchResult assign(int ingredient, boolean[] visitedCandidates) {
			if (budget.expired())return SearchResult.TIMEOUT;
			for (int candidateIndex = 0;candidateIndex < candidates.size();candidateIndex++) {
				if (budget.expired())return SearchResult.TIMEOUT;
				Candidate<T> candidate = candidates.get(candidateIndex);
				if (visitedCandidates[candidateIndex] || !candidate.matches[ingredient])continue;
				visitedCandidates[candidateIndex] = true;
				if (candidate.used < candidate.capacity) {
					moveIngredient(ingredient, candidateIndex);
					return SearchResult.FOUND;
				}

				for (int assignedIngredient = 0;
						assignedIngredient < candidateForIngredient.length;assignedIngredient++) {
					if (budget.expired())return SearchResult.TIMEOUT;
					if (candidateForIngredient[assignedIngredient] != candidateIndex)continue;
					SearchResult result = assign(assignedIngredient, visitedCandidates);
					if (result == SearchResult.TIMEOUT)return SearchResult.TIMEOUT;
					if (result == SearchResult.FOUND) {
						moveIngredient(ingredient, candidateIndex);
						return SearchResult.FOUND;
					}
				}
			}
			return SearchResult.NO_PLAN;
		}

		private void moveIngredient(int ingredient, int candidateIndex) {
			int previous = candidateForIngredient[ingredient];
			if (previous >= 0)candidates.get(previous).used--;
			candidateForIngredient[ingredient] = candidateIndex;
			candidates.get(candidateIndex).used++;
		}

		private List<T> selected() {
			List<T> selected = new ArrayList<>(candidateForIngredient.length);
			for (int candidate : candidateForIngredient) {
				selected.add(candidates.get(candidate).item);
			}
			return selected;
		}
	}

	private static final class Candidate<T> {
		private final T item;
		private final boolean[] matches;
		private final int capacity;
		private int used;

		private Candidate(T item, boolean[] matches, int capacity) {
			this.item = item;
			this.matches = matches;
			this.capacity = capacity;
		}
	}

	private static final class Budget {
		private final long deadlineNanos;

		private Budget(long deadlineNanos) {
			this.deadlineNanos = deadlineNanos;
		}

		private boolean expired() {
			return deadlineNanos != Long.MAX_VALUE && System.nanoTime() - deadlineNanos >= 0;
		}
	}

	private static enum SearchResult {
		FOUND, NO_PLAN, TIMEOUT
	}
}
