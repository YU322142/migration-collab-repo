package com.github.ysbbbbbb.kaleidoscopecookery.inventory.tooltip;

import net.minecraft.world.inventory.tooltip.TooltipComponent;
import net.minecraftforge.items.IItemHandler;

public record ItemContainerTooltip(IItemHandler handler) implements TooltipComponent {
}
