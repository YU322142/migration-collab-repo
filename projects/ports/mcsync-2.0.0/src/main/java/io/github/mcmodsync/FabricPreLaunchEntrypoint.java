package io.github.mcmodsync;

import net.fabricmc.loader.api.entrypoint.PreLaunchEntrypoint;

import java.lang.reflect.InvocationTargetException;
import java.nio.file.Path;

/** Fabric Loader adapter for the loader-neutral pre-launch coordinator. */
public final class FabricPreLaunchEntrypoint implements PreLaunchEntrypoint {
    @Override
    public void onPreLaunch() {
        PortablePreLaunchEntrypoint.run("Fabric", FabricPreLaunchEntrypoint::locateGameDirectory);
    }

    static void releaseGuard() {
        PortablePreLaunchEntrypoint.releaseGuard();
    }

    private static Path locateGameDirectory() {
        try {
            Class<?> loaderClass = Class.forName("net.fabricmc.loader.api.FabricLoader");
            Object loader = loaderClass.getMethod("getInstance").invoke(null);
            Object gameDirectory = loaderClass.getMethod("getGameDir").invoke(loader);
            if (gameDirectory instanceof Path path) {
                return path.toAbsolutePath().normalize();
            }
            throw new IllegalStateException("FabricLoader.getGameDir() 未返回 Path");
        } catch (ClassNotFoundException
                | NoSuchMethodException
                | IllegalAccessException
                | InvocationTargetException exception) {
            throw new IllegalStateException("无法从 Fabric Loader 取得游戏目录", exception);
        }
    }
}
