package net.neoforged.fml.loading;

import java.nio.file.Path;

/** Test-only shape used to verify NeoForge game-directory discovery. */
public enum FMLPaths {
    GAMEDIR;

    private static Path gameDirectory = Path.of(".").toAbsolutePath().normalize();

    public static void setGameDir(Path gameDirectory) {
        FMLPaths.gameDirectory = gameDirectory;
    }

    public Path get() {
        return gameDirectory;
    }
}
