package com.bmt.waypointfire;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * Dependency-free bytecode contract for the custom argument registration.
 *
 * <p>The high-permission runtime gate proves the complete wire path. This
 * lightweight build-time check ensures a future refactor cannot silently
 * remove the registry declaration or the class-to-info binding and still pass
 * the ordinary parity tests.</p>
 */
public final class CommandArgumentRegistrationContractTest {
    public static void main(String[] args) throws IOException {
        byte[] bytes;
        try (InputStream stream = CommandArgumentRegistrationContractTest.class.getResourceAsStream(
            "/com/bmt/waypointfire/WaypointFireEquivalence.class"
        )) {
            if (stream == null) {
                throw new AssertionError("WaypointFireEquivalence.class is missing");
            }
            bytes = stream.readAllBytes();
        }

        String constants = new String(bytes, StandardCharsets.ISO_8859_1);
        require(constants.contains("COMMAND_ARGUMENT_TYPES"), "deferred argument registry");
        require(constants.contains("COMMAND_ARGUMENT_TYPE"), "Minecraft argument registry key");
        require(constants.contains("hex_color"), "hex color registry id");
        require(constants.contains("registerByClass"), "argument class-to-info binding");
        require(constants.contains("SingletonArgumentInfo"), "wire serializer info");
        require(constants.contains("HexColorArgument"), "custom argument class");
    }

    private static void require(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError("Missing command argument registration contract: " + label);
        }
    }
}
