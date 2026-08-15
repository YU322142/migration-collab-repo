package io.github.mcmodsync;

import java.util.Locale;

enum ModKind {
    REQUIRED,
    RECOMMENDED;

    String id() {
        return name().toLowerCase(Locale.ROOT);
    }

    static ModKind parse(String value) {
        if (value == null) {
            throw new IllegalArgumentException("Mod 类型不能为空");
        }
        return switch (value.strip().toLowerCase(Locale.ROOT)) {
            case "required", "must" -> REQUIRED;
            case "recommended", "optional" -> RECOMMENDED;
            default -> throw new IllegalArgumentException("未知 Mod 类型: " + value);
        };
    }
}
