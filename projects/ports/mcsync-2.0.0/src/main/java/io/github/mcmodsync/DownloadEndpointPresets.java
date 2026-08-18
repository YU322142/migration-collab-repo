package io.github.mcmodsync;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;

/** Publisher-facing endpoint presets. They are transport candidates, never integrity authorities. */
final class DownloadEndpointPresets {
    static final URI MODRINTH_OFFICIAL = URI.create("https://api.modrinth.com/v2/");
    static final URI MODRINTH_MCIMIRROR = URI.create("https://mod.mcimirror.top/modrinth/v2/");
    static final URI CURSEFORGE_OFFICIAL = URI.create("https://api.curseforge.com/v1/");
    static final URI CURSEFORGE_MCIMIRROR = URI.create("https://mod.mcimirror.top/curseforge/v1/");

    private DownloadEndpointPresets() {
    }

    static List<ReleaseManifestV5.DownloadEndpoint> forPlatform(String platform, boolean includeChinaMirror) {
        URI official;
        URI mirror;
        switch (platform == null ? "" : platform.strip().toLowerCase(java.util.Locale.ROOT)) {
            case "modrinth" -> {
                official = MODRINTH_OFFICIAL;
                mirror = MODRINTH_MCIMIRROR;
            }
            case "curseforge" -> {
                official = CURSEFORGE_OFFICIAL;
                mirror = CURSEFORGE_MCIMIRROR;
            }
            default -> throw new IllegalArgumentException("不支持的平台端点预设: " + platform);
        }
        List<ReleaseManifestV5.DownloadEndpoint> endpoints = new ArrayList<>();
        if (includeChinaMirror) {
            endpoints.add(new ReleaseManifestV5.DownloadEndpoint(
                    mirror, "mirror", "api", "cn", 10, true));
        }
        endpoints.add(new ReleaseManifestV5.DownloadEndpoint(
                official, "official", "api", "global", 100, false));
        return List.copyOf(endpoints);
    }
}
