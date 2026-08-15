package net.fabricmc.loader.api.entrypoint;

/**
 * Compile-only shape of Fabric Loader's public API. The real interface is
 * supplied by Fabric Loader at runtime and this class is never packaged.
 */
public interface PreLaunchEntrypoint {
    void onPreLaunch();
}
