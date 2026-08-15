package com.crabmod.hotbath.compat;

import com.mojang.logging.LogUtils;
import org.slf4j.Logger;
import toughasnails.api.temperature.TemperatureHelper;

/**
 * ToughAsNails registration handler
 */
public class ToughAsNailsRegistration {
    private static final Logger LOGGER = LogUtils.getLogger();

    public static void init() {
        try {
            LOGGER.info("Registering Hot Bath temperature modifiers with Tough As Nails...");
            TemperatureHelper.registerPlayerTemperatureModifier(new HotBathTANPlayerModifier());
            TemperatureHelper.registerPlayerTemperatureModifier(new BathWaterBottleTANModifier());
            LOGGER.info("Successfully registered Hot Bath temperature modifiers with Tough As Nails!");
        } catch (Exception e) {
            LOGGER.error("Failed to register Hot Bath modifiers with Tough As Nails: {}", e.getMessage(), e);
        }
    }
}
