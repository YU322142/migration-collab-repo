package com.tom.storagemod.menu;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.WeakHashMap;

import net.minecraft.recipebook.PlaceRecipe;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.CraftingRecipe;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.level.Level;

import com.tom.storagemod.block.entity.CraftingTerminalBlockEntity;
import com.tom.storagemod.inventory.StoredItemStack;
import com.tom.storagemod.util.CraftingIngredientPlanner;

public class TerminalCraftingFiller {
	private static final long MAX_PLANNING_NANOS_PER_LEVEL_TICK = 20_000_000L;
	private static final Map<Level, TickPlanningBudget> PLANNING_BUDGETS = new WeakHashMap<>();
	private final CraftingTerminalBlockEntity te;
	private final Player player;

	public TerminalCraftingFiller(CraftingTerminalBlockEntity te, Player player) {
		this.te = te;
		this.player = player;
	}

	public boolean placeRecipe(RecipeHolder<CraftingRecipe> recipe) {
		te.clear(player);
		List<Ingredient> layout = recipe.value().getIngredients();
		List<Ingredient> ingredients = layout.stream().filter(ingredient -> !ingredient.isEmpty()).toList();
		if (layout.size() > 9 || ingredients.isEmpty())return false;

		Map<StoredItemStack, Integer> capacityLimits = new HashMap<>();
		PlacementAttempt attempt;
		try (PlanningWindow window = openPlanningWindow(player.level())) {
			attempt = tryPlaceRecipe(recipe, layout, ingredients,
					te.getCachedCraftingStacks(), capacityLimits, window.deadlineNanos());
		}
		if (attempt.placed())return true;
		if (!hasPlanningBudget(player.level()))return planningTimedOut();

		// A cached miss may only mean that the terminal snapshot is stale. Start
		// capacity reductions from the forced live refresh below.
		Iterable<StoredItemStack> freshStacks = te.getFreshCraftingStacks();
		try (PlanningWindow window = openPlanningWindow(player.level())) {
			while (!window.expired()) {
				attempt = tryPlaceRecipe(recipe, layout, ingredients, freshStacks,
						capacityLimits, window.deadlineNanos());
				if (attempt.placed())return true;
				if (attempt.timedOut())return planningTimedOut();
				if (attempt.failedVariant() == null
						|| !tightenCapacity(capacityLimits, attempt.failedVariant()))return false;
			}
		}
		return planningTimedOut();
	}

	private PlacementAttempt tryPlaceRecipe(RecipeHolder<CraftingRecipe> recipe,
			List<Ingredient> layout, List<Ingredient> ingredients, Iterable<StoredItemStack> stored,
			Map<StoredItemStack, Integer> capacityLimits, long deadlineNanos) {
		var plan = CraftingIngredientPlanner.findItemPlanResult(ingredients, stored,
				player.getInventory().items, capacityLimits, deadlineNanos);
		if (plan.status() == CraftingIngredientPlanner.PlanningStatus.TIMEOUT)return PlacementAttempt.TIMEOUT;
		if (plan.status() != CraftingIngredientPlanner.PlanningStatus.FOUND)return PlacementAttempt.NO_PLAN;

		List<ItemStack> selected = plan.selected();
		List<ItemStack> selectedLayout = new ArrayList<>(layout.size());
		int selectedIndex = 0;
		for (Ingredient ingredient : layout) {
			selectedLayout.add(ingredient.isEmpty() ? ItemStack.EMPTY : selected.get(selectedIndex++));
		}

		ItemStack[] plannedSlots = new ItemStack[9];
		PlaceRecipe<ItemStack> placer = (stack, slotId, count, x, y) -> {
			int gridSlot = x + y * 3;
			if (gridSlot >= 0 && gridSlot < plannedSlots.length)plannedSlots[gridSlot] = stack;
		};
		placer.placeRecipe(3, 3, 0, recipe, selectedLayout.iterator(), 1);

		ItemStack[] extractedSlots = new ItemStack[9];
		List<ExtractedStack> extracted = new ArrayList<>(selected.size());
		Map<StoredItemStack, Integer> extractedCounts = new HashMap<>();
		for (int slotId = 0;slotId < plannedSlots.length;slotId++) {
			ItemStack wanted = plannedSlots[slotId];
			if (wanted == null || wanted.isEmpty())continue;
			StoredItemStack wantedKey = new StoredItemStack(wanted.copyWithCount(1));

			StoredItemStack fromStorage = te.pullStack(new StoredItemStack(wanted), 1);
			if (fromStorage != null) {
				extractedSlots[slotId] = fromStorage.getActualStack();
				extracted.add(new ExtractedStack(extractedSlots[slotId], true));
				if (!ItemStack.isSameItemSameComponents(wanted, extractedSlots[slotId])) {
					rollback(extracted);
					return failed(wantedKey, extractedCounts);
				}
				extractedCounts.merge(wantedKey, 1, Integer::sum);
				continue;
			}

			int playerSlot = player.getInventory().findSlotMatchingUnusedItem(wanted);
			if (playerSlot != -1) {
				extractedSlots[slotId] = player.getInventory().removeItem(playerSlot, 1);
				if (!extractedSlots[slotId].isEmpty()) {
					extracted.add(new ExtractedStack(extractedSlots[slotId], false));
					if (ItemStack.isSameItemSameComponents(wanted, extractedSlots[slotId])) {
						extractedCounts.merge(wantedKey, 1, Integer::sum);
						continue;
					}
				} else {
					extractedSlots[slotId] = null;
				}
			}

			rollback(extracted);
			return failed(wantedKey, extractedCounts);
		}

		for (int slotId = 0;slotId < extractedSlots.length;slotId++) {
			ItemStack stack = extractedSlots[slotId];
			if (stack != null && !stack.isEmpty())te.setCraftSlot(slotId % 3, slotId / 3, stack);
		}
		return PlacementAttempt.SUCCESS;
	}

	private static PlacementAttempt failed(StoredItemStack wanted,
			Map<StoredItemStack, Integer> extractedCounts) {
		return new PlacementAttempt(false,
				new FailedVariant(wanted, extractedCounts.getOrDefault(wanted, 0)), false);
	}

	private static boolean tightenCapacity(Map<StoredItemStack, Integer> capacityLimits,
			FailedVariant failed) {
		Integer previous = capacityLimits.get(failed.stack());
		if (previous != null && previous <= failed.successfulExtractions())return false;
		capacityLimits.put(failed.stack(), failed.successfulExtractions());
		return true;
	}

	private boolean planningTimedOut() {
		player.displayClientMessage(Component.translatable(
				"tooltip.toms_storage.recipe_search_timeout"), true);
		return false;
	}

	private static PlanningWindow openPlanningWindow(Level level) {
		synchronized (PLANNING_BUDGETS) {
			long gameTime = level.getGameTime();
			TickPlanningBudget budget = PLANNING_BUDGETS.computeIfAbsent(level,
					unused -> new TickPlanningBudget(gameTime));
			if (budget.gameTime != gameTime) {
				budget.gameTime = gameTime;
				budget.usedNanos = 0;
			}
			long now = System.nanoTime();
			long remaining = Math.max(0, MAX_PLANNING_NANOS_PER_LEVEL_TICK - budget.usedNanos);
			long allowance = Math.min(CraftingIngredientPlanner.DEFAULT_PLANNING_NANOS, remaining);
			return new PlanningWindow(budget, now, now + allowance);
		}
	}

	private static boolean hasPlanningBudget(Level level) {
		synchronized (PLANNING_BUDGETS) {
			TickPlanningBudget budget = PLANNING_BUDGETS.get(level);
			return budget == null || budget.gameTime != level.getGameTime()
					|| budget.usedNanos < MAX_PLANNING_NANOS_PER_LEVEL_TICK;
		}
	}

	private void rollback(List<ExtractedStack> extracted) {
		for (int i = extracted.size() - 1;i >= 0;i--) {
			ExtractedStack entry = extracted.get(i);
			ItemStack remainder = entry.fromStorage() ? te.pushStack(entry.stack()) : entry.stack();
			if (!remainder.isEmpty())player.getInventory().placeItemBackInInventory(remainder);
		}
	}

	private static record ExtractedStack(ItemStack stack, boolean fromStorage) {
	}

	private static record FailedVariant(StoredItemStack stack, int successfulExtractions) {
	}

	private static record PlacementAttempt(boolean placed, FailedVariant failedVariant, boolean timedOut) {
		private static final PlacementAttempt SUCCESS = new PlacementAttempt(true, null, false);
		private static final PlacementAttempt NO_PLAN = new PlacementAttempt(false, null, false);
		private static final PlacementAttempt TIMEOUT = new PlacementAttempt(false, null, true);
	}

	private static final class TickPlanningBudget {
		private long gameTime;
		private long usedNanos;

		private TickPlanningBudget(long gameTime) {
			this.gameTime = gameTime;
		}
	}

	private static final class PlanningWindow implements AutoCloseable {
		private final TickPlanningBudget budget;
		private final long startedNanos;
		private final long deadlineNanos;
		private boolean closed;

		private PlanningWindow(TickPlanningBudget budget, long startedNanos, long deadlineNanos) {
			this.budget = budget;
			this.startedNanos = startedNanos;
			this.deadlineNanos = deadlineNanos;
		}

		private long deadlineNanos() {
			return deadlineNanos;
		}

		private boolean expired() {
			return System.nanoTime() - deadlineNanos >= 0;
		}

		@Override
		public void close() {
			synchronized (PLANNING_BUDGETS) {
				if (closed)return;
				closed = true;
				long elapsed = Math.max(0, System.nanoTime() - startedNanos);
				budget.usedNanos = Math.min(MAX_PLANNING_NANOS_PER_LEVEL_TICK,
						budget.usedNanos + elapsed);
			}
		}
	}
}
