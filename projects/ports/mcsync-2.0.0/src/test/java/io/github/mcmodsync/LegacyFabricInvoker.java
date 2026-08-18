package io.github.mcmodsync;

/** Invokes a historical Fabric preLaunch entrypoint without shipping Fabric itself. */
public final class LegacyFabricInvoker {
    private LegacyFabricInvoker() {
    }

    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 1) {
            throw new IllegalArgumentException("Expected legacy preLaunch class name");
        }
        Class<?> entrypointClass = Class.forName(arguments[0]);
        Object entrypoint = entrypointClass.getConstructor().newInstance();
        entrypointClass.getMethod("onPreLaunch").invoke(entrypoint);
        System.out.println("LEGACY_GAME_MAIN_WOULD_CONTINUE");
    }
}
