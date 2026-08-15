package org.xiyu.yee.xiyuslogin;

import com.mojang.logging.LogUtils;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.config.ModConfig;
import net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent;
import net.neoforged.neoforge.common.NeoForge;
import org.slf4j.Logger;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginConfig;
import org.xiyu.yee.xiyuslogin.config.XiyusLoginLanguageConfig;
import org.xiyu.yee.xiyuslogin.event.PlayerEventHandler;
import org.xiyu.yee.xiyuslogin.event.ServerEventHandler;

// The value here should match an entry in the META-INF/neoforge.mods.toml file
@Mod(Xiyuslogin.MODID)
public class Xiyuslogin {
    // Define mod id in a common place for everything to reference
    public static final String MODID = "xiyuslogin";
    // Directly reference a slf4j logger
    public static final Logger LOGGER = LogUtils.getLogger();

    // The constructor for the mod class is the first code that is run when your mod is loaded.
    // FML will recognize some parameter types like IEventBus or ModContainer and pass them in automatically.
    public Xiyuslogin(IEventBus modEventBus, ModContainer modContainer) {
        // Register the commonSetup method for modloading
        modEventBus.addListener(this::commonSetup);

        // Register config
        modContainer.registerConfig(ModConfig.Type.COMMON, XiyusLoginConfig.SPEC);
        modContainer.registerConfig(ModConfig.Type.COMMON, XiyusLoginLanguageConfig.SPEC, "xiyuslogin-language.toml");
        
        // Register event handlers
        NeoForge.EVENT_BUS.register(ServerEventHandler.class);
        NeoForge.EVENT_BUS.register(PlayerEventHandler.class);
        
        LOGGER.info("XiyusLogin mod initialized");
    }

    private void commonSetup(final FMLCommonSetupEvent event) {
        LOGGER.info("XiyusLogin common setup complete");
    }
}
