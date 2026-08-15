package net.immortaldevs.colorizer;

import com.mojang.logging.LogUtils;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import javax.annotation.Nullable;
import net.minecraft.core.BlockPos;
import net.neoforged.fml.loading.FMLPaths;
import org.slf4j.Logger;

public final class ColorizerConfig {
    private static final Logger LOGGER = LogUtils.getLogger();
    private static ColorizerCsvDocument document = ColorizerCsvDocument.empty();
    private static Path configPath;

    private ColorizerConfig() {
    }

    public static synchronized void load() {
        load(FMLPaths.CONFIGDIR.get().resolve("colorizer.csv"));
    }

    static synchronized void load(Path path) {
        configPath = path;
        try {
            Files.createDirectories(path.getParent());
            if (Files.notExists(path)) {
                Files.createFile(path);
            }
            document = ColorizerCsvDocument.parse(Files.readString(path, StandardCharsets.UTF_8));
            LOGGER.info(
                    "[Chest Colorizer] Loaded {} color records; preserved {} unrecognized lines from {}",
                    document.validRecordCount(),
                    document.preservedLineCount(),
                    path
            );
        } catch (IOException exception) {
            LOGGER.error("[Chest Colorizer] Failed to load {}; keeping the previous in-memory colors", path, exception);
        }
    }

    @Nullable
    public static synchronized BlockColor getColor(String worldName, BlockPos position) {
        if (worldName == null) {
            return null;
        }
        return document.getColor(worldName, position.getX(), position.getY(), position.getZ());
    }

    public static synchronized void setColor(String worldName, BlockPos position, BlockColor color) {
        if (worldName == null) {
            return;
        }
        document.setColor(worldName, position.getX(), position.getY(), position.getZ(), color);
        save();
    }

    public static synchronized void removeColor(String worldName, BlockPos position) {
        if (worldName == null) {
            return;
        }
        document.removeColor(worldName, position.getX(), position.getY(), position.getZ());
        save();
    }

    private static void save() {
        if (configPath == null) {
            return;
        }
        Path temporary = configPath.resolveSibling(configPath.getFileName() + ".tmp");
        try {
            Files.writeString(temporary, document.serialize(), StandardCharsets.UTF_8);
            try {
                Files.move(temporary, configPath, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(temporary, configPath, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException exception) {
            LOGGER.error("[Chest Colorizer] Failed to save {}; the previous file was left intact", configPath, exception);
            try {
                Files.deleteIfExists(temporary);
            } catch (IOException cleanupException) {
                LOGGER.warn("[Chest Colorizer] Failed to remove temporary file {}", temporary, cleanupException);
            }
        }
    }
}
