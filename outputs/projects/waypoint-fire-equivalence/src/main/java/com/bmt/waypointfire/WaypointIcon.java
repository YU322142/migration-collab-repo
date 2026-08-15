package com.bmt.waypointfire;

import java.util.OptionalInt;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.resources.ResourceLocation;

public record WaypointIcon(ResourceLocation style, OptionalInt color) {
    public static final ResourceLocation DEFAULT_STYLE = ResourceLocation.withDefaultNamespace("default");
    public static final ResourceLocation BOWTIE_STYLE = ResourceLocation.withDefaultNamespace("bowtie");
    public static final WaypointIcon DEFAULT = new WaypointIcon(DEFAULT_STYLE, OptionalInt.empty());

    public WaypointIcon {
        if (style == null) {
            throw new IllegalArgumentException("style");
        }
        if (color == null) {
            color = OptionalInt.empty();
        }
    }

    public boolean isDefault() {
        return style.equals(DEFAULT_STYLE) && color.isEmpty();
    }

    public CompoundTag save() {
        CompoundTag tag = new CompoundTag();
        tag.putString("style", style.toString());
        color.ifPresent(value -> tag.putInt("color", value));
        return tag;
    }

    public static WaypointIcon load(CompoundTag tag) {
        ResourceLocation style = ResourceLocation.tryParse(tag.getString("style"));
        if (style == null) {
            style = DEFAULT_STYLE;
        }
        OptionalInt color = tag.contains("color") ? OptionalInt.of(tag.getInt("color")) : OptionalInt.empty();
        return new WaypointIcon(style, color);
    }
}
