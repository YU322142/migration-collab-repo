package com.antigravity.create_dynamic_blocking;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.mojang.logging.LogUtils;
import net.neoforged.fml.loading.FMLPaths;
import org.slf4j.Logger;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DynamicBlockingConfig {
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Path CONFIG_FILE = FMLPaths.CONFIGDIR.get().resolve("create_dynamic_blocking.json");

    public static boolean enabled = true;
    public static double maxScanDistance = 128.0;
    public static double slowdownDistance = 60.0;
    public static double emergencyStopDistance = 30.0;
    public static double finalStopDistance = 5.0;
    public static boolean debugLogging = false;

    private DynamicBlockingConfig() {
    }

    public static void load() {
        if (Files.isRegularFile(CONFIG_FILE)) {
            try (Reader reader = Files.newBufferedReader(CONFIG_FILE, StandardCharsets.UTF_8)) {
                ConfigData data = GSON.fromJson(reader, ConfigData.class);
                if (data != null) {
                    enabled = data.enabled;
                    maxScanDistance = data.maxScanDistance;
                    slowdownDistance = data.slowdownDistance;
                    emergencyStopDistance = data.emergencyStopDistance;
                    finalStopDistance = data.finalStopDistance;
                    debugLogging = data.debugLogging;
                }
            } catch (Exception exception) {
                LOGGER.error("[动态闭塞] 读取配置文件失败，将使用当前值", exception);
            }
        }
        validate();
        save();
    }

    private static void validate() {
        finalStopDistance = finiteOrDefault(finalStopDistance, 5.0);
        emergencyStopDistance = finiteOrDefault(emergencyStopDistance, 30.0);
        slowdownDistance = finiteOrDefault(slowdownDistance, 60.0);
        maxScanDistance = finiteOrDefault(maxScanDistance, 128.0);
        finalStopDistance = Math.max(0.5, finalStopDistance);
        emergencyStopDistance = Math.max(finalStopDistance, emergencyStopDistance);
        slowdownDistance = Math.max(emergencyStopDistance, slowdownDistance);
        maxScanDistance = Math.max(slowdownDistance, maxScanDistance);
    }

    private static double finiteOrDefault(double value, double fallback) {
        return Double.isFinite(value) ? value : fallback;
    }

    public static void save() {
        try (Writer writer = Files.newBufferedWriter(CONFIG_FILE, StandardCharsets.UTF_8)) {
            GSON.toJson(new ConfigData(), writer);
        } catch (IOException exception) {
            LOGGER.error("[动态闭塞] 保存配置文件失败", exception);
        }
    }

    private static final class ConfigData {
        public boolean enabled = DynamicBlockingConfig.enabled;
        public double maxScanDistance = DynamicBlockingConfig.maxScanDistance;
        public double slowdownDistance = DynamicBlockingConfig.slowdownDistance;
        public double emergencyStopDistance = DynamicBlockingConfig.emergencyStopDistance;
        public double finalStopDistance = DynamicBlockingConfig.finalStopDistance;
        public boolean debugLogging = DynamicBlockingConfig.debugLogging;
    }
}
