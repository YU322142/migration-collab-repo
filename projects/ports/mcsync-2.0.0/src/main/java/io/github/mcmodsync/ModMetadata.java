package io.github.mcmodsync;

import java.nio.file.Path;

/** Loader-neutral metadata facade used by catalog generation and replacement. */
final class ModMetadata {
    private ModMetadata() {
    }

    static String readModId(Path jar) {
        String fabric = FabricModMetadata.readModId(jar);
        return !fabric.isBlank() ? fabric : validNeoForgeId(NeoForgeModMetadata.readModId(jar));
    }

    static String readVersion(Path jar) {
        String fabric = FabricModMetadata.readVersion(jar);
        return !fabric.isBlank() ? fabric : NeoForgeModMetadata.readVersion(jar);
    }

    static String readName(Path jar) {
        String fabric = FabricModMetadata.readName(jar);
        return !fabric.isBlank() ? fabric : NeoForgeModMetadata.readName(jar);
    }

    static String readDescription(Path jar) {
        String fabric = FabricModMetadata.readDescription(jar);
        return !fabric.isBlank() ? fabric : NeoForgeModMetadata.readDescription(jar);
    }

    static boolean isValidModId(String value) {
        return FabricModMetadata.isValidModId(value);
    }

    private static String validNeoForgeId(String value) {
        return isValidModId(value) ? value : "";
    }
}
