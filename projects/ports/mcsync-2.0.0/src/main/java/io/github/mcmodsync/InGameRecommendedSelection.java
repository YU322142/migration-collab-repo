package io.github.mcmodsync;

import java.nio.file.Path;

/** Loader-neutral availability check; the actual screen is linked only on NeoForge clients. */
final class InGameRecommendedSelection {
    private InGameRecommendedSelection() {
    }

    static boolean supported() {
        if (Boolean.getBoolean("modsync.forceInGameSelection")) return true;
        try {
            Class.forName("net.neoforged.fml.loading.FMLPaths", false,
                    InGameRecommendedSelection.class.getClassLoader());
            return true;
        } catch (Throwable unavailable) {
            return false;
        }
    }

    static boolean pending(Path gameDirectory) {
        return java.nio.file.Files.isRegularFile(V5RecommendedSelectionStore.pendingPath(gameDirectory));
    }
}
