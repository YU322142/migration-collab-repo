package net.fabricmc.loader.api;

import java.nio.file.Path;

/** Test double shared by portable-entrypoint and legacy-upgrade integration tests. */
public final class FabricLoader {
    private static final FabricLoader INSTANCE = new FabricLoader();
    private static Path gameDirectory;

    private FabricLoader() {
    }

    public static FabricLoader getInstance() {
        return INSTANCE;
    }

    public static void setGameDir(Path gameDirectory) {
        FabricLoader.gameDirectory = gameDirectory;
    }

    public Path getGameDir() {
        if (gameDirectory != null) {
            return gameDirectory;
        }
        String legacyGameDirectory = System.getProperty("legacy.gameDir");
        return legacyGameDirectory == null
                ? null
                : Path.of(legacyGameDirectory).toAbsolutePath().normalize();
    }
}
