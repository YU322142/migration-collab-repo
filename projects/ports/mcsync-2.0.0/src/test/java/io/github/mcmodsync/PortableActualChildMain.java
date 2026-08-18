package io.github.mcmodsync;

import java.nio.file.Path;

public final class PortableActualChildMain {
    private PortableActualChildMain() {
    }

    public static void main(String[] arguments) {
        if (arguments.length != 1) {
            throw new IllegalArgumentException("Expected game directory argument");
        }
        net.fabricmc.loader.api.FabricLoader.setGameDir(Path.of(arguments[0]));
        new FabricPreLaunchEntrypoint().onPreLaunch();
        throw new AssertionError("A scheduled portable update must exit before returning from preLaunch");
    }
}
