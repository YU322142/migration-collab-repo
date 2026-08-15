package com.tom.storagemod.jei;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.jetbrains.annotations.Nullable;

import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.MenuType;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.CraftingRecipe;
import net.minecraft.world.item.crafting.RecipeHolder;

import com.tom.storagemod.Content;
import com.tom.storagemod.inventory.StoredItemStack;
import com.tom.storagemod.menu.CraftingTerminalMenu;
import com.tom.storagemod.util.CraftingIngredientPlanner;
import com.tom.storagemod.util.IAutoFillTerminal;

import mezz.jei.api.constants.RecipeTypes;
import mezz.jei.api.gui.builder.ITooltipBuilder;
import mezz.jei.api.gui.ingredient.IRecipeSlotsView;
import mezz.jei.api.recipe.RecipeType;
import mezz.jei.api.recipe.transfer.IRecipeTransferError;
import mezz.jei.api.recipe.transfer.IRecipeTransferHandler;
import mezz.jei.api.recipe.transfer.IRecipeTransferHandlerHelper;
import mezz.jei.api.registration.IRecipeTransferRegistration;

public class CraftingTerminalTransferHandler<C extends AbstractContainerMenu & IAutoFillTerminal>
		implements IRecipeTransferHandler<C, RecipeHolder<CraftingRecipe>> {
	private final Class<C> containerClass;
	private final IRecipeTransferHandlerHelper helper;
	private static final IRecipeTransferError ERROR_INSTANCE = new IRecipeTransferError() {
		@Override public IRecipeTransferError.Type getType() { return IRecipeTransferError.Type.INTERNAL; }
	};

	public CraftingTerminalTransferHandler(Class<C> containerClass, IRecipeTransferHandlerHelper helper) {
		this.containerClass = containerClass;
		this.helper = helper;
	}

	@Override
	public Class<C> getContainerClass() {
		return containerClass;
	}

	@Override
	public @Nullable IRecipeTransferError transferRecipe(C container, RecipeHolder<CraftingRecipe> recipe,
			IRecipeSlotsView recipeSlots, Player player, boolean maxTransfer, boolean doTransfer) {
		if (!(container instanceof IAutoFillTerminal term))return ERROR_INSTANCE;
		if (!term.isSmartSearch() && !doTransfer)return null;

		Map<StoredItemStack, StoredItemStack> visibleStorage = new HashMap<>();
		term.getStoredItems().forEach(stack -> {
			StoredItemStack copy = new StoredItemStack(stack);
			visibleStorage.put(copy, copy);
		});
		if (container instanceof CraftingTerminalMenu craftingTerminal) {
			Map<StoredItemStack, StoredItemStack> gridCounts = new HashMap<>();
			craftingTerminal.getInputGridSlots().forEach(slot -> {
				ItemStack stack = slot.getItem();
				if (stack.isEmpty())return;
				StoredItemStack gridStack = new StoredItemStack(stack);
				gridCounts.merge(gridStack, gridStack, (total, added) -> {
					total.grow(added.getQuantity());
					return total;
				});
			});
			gridCounts.forEach((stack, grid) -> visibleStorage.merge(stack, grid,
					(stored, countedGrid) -> {
						stored.grow(countedGrid.getQuantity());
						return stored;
					}));
		}

		var ingredients = recipe.value().getIngredients().stream()
				.filter(ingredient -> !ingredient.isEmpty()).toList();
		CraftingIngredientPlanner.PlanningStatus planningStatus = ingredients.isEmpty()
				|| ingredients.size() > 9 ? CraftingIngredientPlanner.PlanningStatus.NO_PLAN
						: CraftingIngredientPlanner.findItemPlanResult(ingredients,
								visibleStorage.values(), player.getInventory().items, Map.of(),
								CraftingIngredientPlanner.defaultPlanningDeadline()).status();
		boolean missing = planningStatus == CraftingIngredientPlanner.PlanningStatus.NO_PLAN;

		if (doTransfer) {
			CompoundTag compound = new CompoundTag();
			compound.putString("fill", recipe.id().toString());
			term.sendMessage(compound);
		}

		if (missing) {
			return new TransferWarning(helper.createUserErrorWithTooltip(
					Component.translatable("tooltip.toms_storage.items_missing")));
		}
		if (planningStatus == CraftingIngredientPlanner.PlanningStatus.TIMEOUT) {
			return new TransferWarning(helper.createUserErrorWithTooltip(
					Component.translatable("tooltip.toms_storage.recipe_search_timeout")));
		}
		return null;
	}

	public static void registerTransferHandlers(IRecipeTransferRegistration recipeTransferRegistry) {
		recipeTransferRegistry.addRecipeTransferHandler(new CraftingTerminalTransferHandler<>(
				CraftingTerminalMenu.class, recipeTransferRegistry.getTransferHelper()), RecipeTypes.CRAFTING);
	}

	private static class TransferWarning implements IRecipeTransferError {
		private final IRecipeTransferError parent;

		public TransferWarning(IRecipeTransferError parent) {
			this.parent = parent;
		}

		@Override
		public Type getType() {
			return Type.COSMETIC;
		}

		@Override
		public int getButtonHighlightColor() {
			return parent.getButtonHighlightColor();
		}

		@Override
		public void showError(GuiGraphics guiGraphics, int mouseX, int mouseY,
				IRecipeSlotsView recipeSlotsView, int recipeX, int recipeY) {
			parent.showError(guiGraphics, mouseX, mouseY, recipeSlotsView, recipeX, recipeY);
		}

		@Override
		public List<Component> getTooltip() {
			return parent.getTooltip();
		}

		@Override
		public void getTooltip(ITooltipBuilder tooltip) {
			parent.getTooltip(tooltip);
		}

		@Override
		public int getMissingCountHint() {
			return parent.getMissingCountHint();
		}
	}

	@SuppressWarnings("unchecked")
	@Override
	public Optional<MenuType<C>> getMenuType() {
		return Optional.<MenuType<C>>ofNullable((MenuType<C>) Content.craftingTerminalMenu.get());
	}

	@Override
	public RecipeType<RecipeHolder<CraftingRecipe>> getRecipeType() {
		return RecipeTypes.CRAFTING;
	}
}
