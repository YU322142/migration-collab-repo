package io.github.mcmodsync;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

final class BakaXLLayout {
    private BakaXLLayout() {
    }

    static List<Target> syncTargets(Path detectedGameDirectory) {
        Path current = detectedGameDirectory.toAbsolutePath().normalize();
        Path parent = current.getParent();
        Path minecraftRoot = parent == null ? null : parent.getParent();
        if (parent == null || minecraftRoot == null || current.getFileName() == null) {
            return List.of(new Target(current, "游戏目录"));
        }

        String container = parent.getFileName().toString().toLowerCase(Locale.ROOT);
        String companionContainer;
        String currentLabel;
        String companionLabel;
        if (container.equals("versions")) {
            companionContainer = "instances";
            currentLabel = "BakaXL 运行副本";
            companionLabel = "BakaXL 持久实例";
        } else if (container.equals("instances")) {
            companionContainer = "versions";
            currentLabel = "BakaXL 持久实例";
            companionLabel = "BakaXL 运行副本";
        } else {
            return List.of(new Target(current, "游戏目录"));
        }

        Path companion = minecraftRoot
                .resolve(companionContainer)
                .resolve(current.getFileName().toString())
                .toAbsolutePath()
                .normalize();
        if (!isMatchingInstance(current, companion)) {
            return List.of(new Target(current, "游戏目录"));
        }

        List<Target> result = new ArrayList<>(2);
        if (container.equals("versions")) {
            result.add(new Target(companion, companionLabel));
            result.add(new Target(current, currentLabel));
        } else {
            result.add(new Target(current, currentLabel));
            result.add(new Target(companion, companionLabel));
        }
        return List.copyOf(result);
    }

    private static boolean isMatchingInstance(Path first, Path second) {
        if (!Files.isDirectory(first) || !Files.isDirectory(second)) {
            return false;
        }
        Path firstPackage = first.resolve("package.info");
        Path secondPackage = second.resolve("package.info");
        if (!Files.isRegularFile(firstPackage) || !Files.isRegularFile(secondPackage)) {
            return false;
        }
        try {
            return Files.mismatch(firstPackage, secondPackage) == -1;
        } catch (IOException exception) {
            return false;
        }
    }

    record Target(Path gameDirectory, String label) {
    }
}
