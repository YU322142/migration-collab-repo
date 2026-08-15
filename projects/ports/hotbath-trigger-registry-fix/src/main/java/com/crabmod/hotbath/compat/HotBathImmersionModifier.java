package com.crabmod.hotbath.compat;

import com.crabmod.hotbath.util.CustomFluidHandler;
import com.momosoftworks.coldsweat.api.temperature.modifier.TempModifier;
import com.momosoftworks.coldsweat.api.util.Temperature;
import com.momosoftworks.coldsweat.util.world.WorldHelper;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;

import java.util.function.Function;

/**
 * Temperature modifier that applies a fixed temperature when the player is inside a Hot Bath block.
 */
public class HotBathImmersionModifier extends TempModifier {

    private static final double TARGET_TEMP_C = 37.0;

    public HotBathImmersionModifier() {
        super();
    }

    @Override
    protected Function<Double, Double> calculate(LivingEntity entity, Temperature.Trait trait) {
        // We only modify the WORLD temperature trait
        if (trait != Temperature.Trait.WORLD) {
            return temp -> temp;
        }

        // Only apply to players (CustomFluidHandler methods expect Player type)
        if (!(entity instanceof Player player)) {
            return temp -> temp;
        }

        Level level = entity.level();
        BlockPos pos = entity.blockPosition();

        // Check if the entity is inside any hot bath block using the existing utility method
        if (CustomFluidHandler.isPlayerInHotBathBlock(player)) {
            // Calculate target temperature in Minecraft units
            double targetTempMC = Temperature.convert(TARGET_TEMP_C, Temperature.Units.C, Temperature.Units.MC, true);

            // Get the natural biome temperature at this position
            double worldTempMC = WorldHelper.getBiomeTemperature(level, level.getBiome(pos));

            // Use the higher of the two temperatures
            // If the world is hotter (e.g. desert at noon), use that.
            // Otherwise, use the fixed hot bath temperature.
            double finalTemp = Math.max(targetTempMC, worldTempMC);

            // Return a function that ignores the input temperature and returns our fixed value
            return temp -> finalTemp;
        }

        // If not inside a hot bath, return identity function (no change)
        return temp -> temp;
    }
}
