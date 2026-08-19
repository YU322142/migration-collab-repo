package io.github.mcmodsync;

import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.common.Mod;

import java.lang.reflect.InvocationTargetException;
import java.nio.file.Path;

/** Official NeoForge 1.21.1 client-side mod entrypoint. */
@Mod(value = "mcmodsync", dist = Dist.CLIENT)
public final class NeoForgeModEntrypoint {
    public NeoForgeModEntrypoint() {
        System.setProperty("modsync.inGameWindow", "true");
        System.setProperty("modsync.disableDialogs", "true");
        Path gameDirectory = locateGameDirectory();
        PortablePreLaunchEntrypoint.run("NeoForge", () -> gameDirectory);
        RecommendedSelectionScreen.start(gameDirectory);
    }

    static Path locateGameDirectory() {
        try {
            Class<?> pathsClass = Class.forName("net.neoforged.fml.loading.FMLPaths");
            @SuppressWarnings("unchecked")
            Object gamePath = Enum.valueOf((Class<? extends Enum>) pathsClass.asSubclass(Enum.class), "GAMEDIR");
            Object gameDirectory = pathsClass.getMethod("get").invoke(gamePath);
            if (gameDirectory instanceof Path path) {
                return path.toAbsolutePath().normalize();
            }
            throw new IllegalStateException("FMLPaths.GAMEDIR.get() 未返回 Path");
        } catch (ClassNotFoundException
                | NoSuchMethodException
                | IllegalAccessException
                | InvocationTargetException
                | ClassCastException exception) {
            throw new IllegalStateException("无法从 NeoForge FMLPaths 取得游戏目录", exception);
        }
    }
}
