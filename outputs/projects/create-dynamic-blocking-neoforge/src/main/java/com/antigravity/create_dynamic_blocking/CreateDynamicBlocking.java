package com.antigravity.create_dynamic_blocking;

import com.mojang.logging.LogUtils;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import org.slf4j.Logger;

@Mod(CreateDynamicBlocking.MODID)
public final class CreateDynamicBlocking {
    public static final String MODID = "create_dynamic_blocking";
    private static final Logger LOGGER = LogUtils.getLogger();

    public CreateDynamicBlocking() {
        DynamicBlockingConfig.load();
        LOGGER.info(
                "[Dynamic Blocking] NeoForge equivalence port loaded. Slowdown distance: {}, final stop distance: {}",
                DynamicBlockingConfig.slowdownDistance,
                DynamicBlockingConfig.finalStopDistance
        );
        NeoForge.EVENT_BUS.addListener(this::registerCommands);
    }

    private void registerCommands(RegisterCommandsEvent event) {
        event.getDispatcher().register(Commands.literal("cdb")
                .requires(source -> source.hasPermission(2))
                .then(Commands.literal("reload").executes(context -> {
                    DynamicBlockingConfig.load();
                    context.getSource().sendSuccess(
                            () -> Component.literal(
                                    "[动态闭塞] 配置已重新加载；最终停车距离："
                                            + DynamicBlockingConfig.finalStopDistance
                            ),
                            true
                    );
                    return 1;
                })));
    }
}
