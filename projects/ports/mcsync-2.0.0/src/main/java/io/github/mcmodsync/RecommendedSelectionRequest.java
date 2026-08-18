package io.github.mcmodsync;

import java.util.List;
import java.util.Set;

record RecommendedSelectionRequest(
        String previousCatalogVersion,
        String catalogVersion,
        ClientPlatform platform,
        List<ManifestEntry> recommendedMods,
        Set<String> initiallySelected) {

    RecommendedSelectionRequest {
        previousCatalogVersion = previousCatalogVersion == null ? "" : previousCatalogVersion;
        recommendedMods = List.copyOf(recommendedMods);
        initiallySelected = Set.copyOf(initiallySelected);
    }
}
