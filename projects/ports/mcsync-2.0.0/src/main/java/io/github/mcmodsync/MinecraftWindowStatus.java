package io.github.mcmodsync;

import java.lang.reflect.Method;

/** Best-effort early-loading status inside the existing Minecraft window title. */
final class MinecraftWindowStatus {
    private MinecraftWindowStatus() {
    }

    static void update(String status) {
        if (!Boolean.getBoolean("modsync.inGameWindow") || Boolean.getBoolean("modsync.helperProcess")) return;
        try {
            Class<?> minecraftClass = Class.forName(
                    "net.minecraft.client.Minecraft", false, MinecraftWindowStatus.class.getClassLoader());
            Object minecraft = minecraftClass.getMethod("getInstance").invoke(null);
            if (minecraft == null) return;
            Object window = minecraftClass.getMethod("getWindow").invoke(minecraft);
            if (window == null) return;
            Method setTitle = java.util.Arrays.stream(window.getClass().getMethods())
                    .filter(method -> method.getName().equals("setTitle")
                            && method.getParameterCount() == 1
                            && method.getParameterTypes()[0] == String.class)
                    .findFirst().orElse(null);
            if (setTitle != null) setTitle.invoke(window, "MCSync — " + status);
        } catch (Throwable ignored) {
            // The Minecraft singleton/window may not exist during the first loading phase.
        }
    }
}
