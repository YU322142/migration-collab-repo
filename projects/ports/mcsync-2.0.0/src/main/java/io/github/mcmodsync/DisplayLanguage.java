package io.github.mcmodsync;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Properties;

enum DisplayLanguage {
    ZH_CN,
    EN_US;

    static DisplayLanguage detect(Path gameDirectory) {
        String configured = System.getProperty("modsync.language", "").strip();
        if (configured.isBlank() && gameDirectory != null) {
            configured = readConfiguredLanguage(gameDirectory);
        }
        if (!configured.isBlank() && !configured.equalsIgnoreCase("auto")) {
            return parse(configured);
        }
        // auto deliberately follows the operating-system/JVM display locale.
        // Minecraft's options.txt may use a different in-game language and must
        // not unexpectedly change updater dialogs or operational logs.
        return fromLocale(Locale.getDefault(Locale.Category.DISPLAY));
    }

    static DisplayLanguage fromLocale(Locale locale) {
        return locale != null && locale.getLanguage().equalsIgnoreCase("zh") ? ZH_CN : EN_US;
    }

    static DisplayLanguage parse(String value) {
        if (value == null) {
            return EN_US;
        }
        return switch (value.strip().toLowerCase(Locale.ROOT).replace('-', '_')) {
            case "zh", "zh_cn", "zh_hans", "chinese", "中文" -> ZH_CN;
            case "en", "en_us", "en_gb", "english" -> EN_US;
            default -> fromLocale(Locale.getDefault());
        };
    }

    boolean chinese() {
        return this == ZH_CN;
    }

    String text(String chinese, String english) {
        return this == ZH_CN ? chinese : english;
    }

    private static String readConfiguredLanguage(Path gameDirectory) {
        Path propertiesPath = gameDirectory.resolve("modsync.properties");
        if (!Files.isRegularFile(propertiesPath)) {
            return "";
        }
        Properties properties = new Properties();
        try (InputStream input = Files.newInputStream(propertiesPath)) {
            properties.load(input);
            return properties.getProperty("language", "").strip();
        } catch (IOException exception) {
            return "";
        }
    }

}
