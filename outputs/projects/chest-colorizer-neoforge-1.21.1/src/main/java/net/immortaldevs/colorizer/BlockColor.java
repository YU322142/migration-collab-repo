package net.immortaldevs.colorizer;

import java.util.Locale;
import javax.annotation.Nullable;
import net.minecraft.util.StringRepresentable;
import net.minecraft.world.item.DyeColor;

public enum BlockColor implements StringRepresentable {
    DEFAULT("default"),
    WHITE("white"),
    LIGHT_GRAY("light_gray"),
    GRAY("gray"),
    BLACK("black"),
    BROWN("brown"),
    RED("red"),
    ORANGE("orange"),
    YELLOW("yellow"),
    LIME("lime"),
    GREEN("green"),
    CYAN("cyan"),
    LIGHT_BLUE("light_blue"),
    BLUE("blue"),
    PURPLE("purple"),
    MAGENTA("magenta"),
    PINK("pink");

    private final String name;

    BlockColor(String name) {
        this.name = name;
    }

    @Nullable
    public static BlockColor fromName(String name) {
        for (BlockColor color : values()) {
            if (color.name.equals(name)) {
                return color;
            }
        }
        return null;
    }

    public static BlockColor fromDyeColor(DyeColor color) {
        return valueOf(color.name().toUpperCase(Locale.ROOT));
    }

    public static boolean isExplicit(@Nullable BlockColor color) {
        return color != null && color != DEFAULT;
    }

    public String getName() {
        return name;
    }

    @Override
    public String getSerializedName() {
        return name;
    }
}
