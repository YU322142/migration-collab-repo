package dev.migration.kaleidoscope_cookery_scarecrow_compat;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.Tag;

/** Pure, idempotent normalisation of the two cross-version inventory fields. */
public final class LegacyScarecrowNbt {
    public static final String HAND_ITEMS = "HandItems";
    public static final String ARMOR_ITEMS = "ArmorItems";
    public static final int HAND_SIZE = 2;
    public static final int ARMOR_SIZE = 4;

    private LegacyScarecrowNbt() {
    }

    public static int normalize(CompoundTag entityTag) {
        int converted = 0;
        if (normalizeList(entityTag, HAND_ITEMS, HAND_SIZE)) {
            converted++;
        }
        if (normalizeList(entityTag, ARMOR_ITEMS, ARMOR_SIZE)) {
            converted++;
        }
        return converted;
    }

    static boolean normalizeList(CompoundTag entityTag, String key, int size) {
        if (!entityTag.contains(key, Tag.TAG_LIST)) {
            return false;
        }
        ListTag legacyItems = entityTag.getList(key, Tag.TAG_COMPOUND).copy();
        CompoundTag handler = new CompoundTag();
        handler.put("Items", legacyItems);
        handler.putInt("Size", size);
        entityTag.put(key, handler);
        return true;
    }
}

