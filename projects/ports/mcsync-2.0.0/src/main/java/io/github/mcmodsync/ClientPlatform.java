package io.github.mcmodsync;

import java.util.Locale;

enum ClientPlatform {
    WINDOWS("Windows"),
    MAC("Mac"),
    LINUX("Linux"),
    MOBILE("手机端");

    private final String displayName;

    ClientPlatform(String displayName) {
        this.displayName = displayName;
    }

    String id() {
        return name().toLowerCase(Locale.ROOT);
    }

    String displayName() {
        return displayName;
    }

    String displayName(DisplayLanguage language) {
        return this == MOBILE ? language.text("手机端", "Mobile") : displayName;
    }

    static ClientPlatform current(RuntimeEnvironment environment) {
        if (environment.mobile()) {
            return MOBILE;
        }
        String osName = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        if (osName.contains("win")) {
            return WINDOWS;
        }
        if (osName.contains("mac") || osName.contains("darwin")) {
            return MAC;
        }
        return LINUX;
    }

    static ClientPlatform parse(String value) {
        if (value == null) {
            throw new IllegalArgumentException("平台不能为空");
        }
        return switch (value.strip().toLowerCase(Locale.ROOT)) {
            case "windows", "win" -> WINDOWS;
            case "mac", "macos", "osx" -> MAC;
            case "linux" -> LINUX;
            case "mobile", "android", "phone" -> MOBILE;
            default -> throw new IllegalArgumentException("未知平台: " + value);
        };
    }
}
