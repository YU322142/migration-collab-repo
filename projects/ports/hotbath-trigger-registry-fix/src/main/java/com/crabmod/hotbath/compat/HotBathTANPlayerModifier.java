package com.crabmod.hotbath.compat;

import com.crabmod.hotbath.util.CustomFluidHandler;
import net.minecraft.world.entity.player.Player;
import toughasnails.api.temperature.IPlayerTemperatureModifier;
import toughasnails.api.temperature.TemperatureLevel;

/**
 * Player temperature modifier for Tough As Nails integration.
 * When a player is inside a hot bath block, their temperature is set to WARM.
 * This corresponds to the 37°C (body temperature) that the hot bath provides.
 */
public class HotBathTANPlayerModifier implements IPlayerTemperatureModifier {

    @Override
    public TemperatureLevel modify(Player player, TemperatureLevel current) {
        // Check if the player is inside any hot bath block using the existing utility method
        if (CustomFluidHandler.isPlayerInHotBathBlock(player)) {
            // Return WARM temperature level (corresponding to comfortable 37°C body temperature)
            // This provides a comfortable warming effect without being too hot
            return TemperatureLevel.WARM;
        }

        // If not inside a hot bath, return current temperature unchanged
        return current;
    }
}
