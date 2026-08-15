package com.tom.storagemod.migration;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.IntArrayTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.NumericTag;
import net.minecraft.nbt.StringTag;
import net.minecraft.nbt.Tag;

/**
 * Offline, fail-closed conversion for Tom's Fabric block-filter attachments.
 *
 * <p>Fabric 2.9 stores absolute {@code pos}/{@code connected} arrays,
 * string priorities and {@code keep_last}. NeoForge 2.4 stores relative
 * compound coordinates, an ordinal priority and {@code keepLast}. This class
 * converts only the attachment payload; callers are responsible for the
 * global ItemStack/component downgrade before passing the filter stack here.
 * No source tag is mutated.</p>
 */
public final class BlockFilterAttachmentMigration {
    public static final String FABRIC_ATTACHMENTS = "fabric:attachments";
    public static final String NEOFORGE_ATTACHMENTS = "neoforge:attachments";
    public static final String BLOCK_FILTER_ID = "toms_storage:block_filter";

    private BlockFilterAttachmentMigration() {
    }

    public enum Status {
        NO_LEGACY,
        CONVERTED,
        ALREADY_NEOFORGE,
        NEOFORGE_WINS_CONFLICT
    }

    public record Result(Status status, CompoundTag blockEntity, List<String> warnings) {
        public Result {
            Objects.requireNonNull(status, "status");
            Objects.requireNonNull(blockEntity, "blockEntity");
            warnings = List.copyOf(warnings);
        }

        public boolean changed() {
            return status == Status.CONVERTED;
        }
    }

    /**
     * Convert a block-entity compound in memory. The returned compound is a
     * deep copy and can be written to a temporary world/region. If both
     * attachment namespaces exist, the NeoForge payload is retained and the
     * legacy payload is left untouched for backup/audit purposes.
     */
    public static Result migrateBlockEntity(CompoundTag source, BlockPos holderPos) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(holderPos, "holderPos");
        CompoundTag result = source.copy();
        List<String> warnings = new ArrayList<>();

        Tag fabricRoot = result.get(FABRIC_ATTACHMENTS);
        Tag neoRoot = result.get(NEOFORGE_ATTACHMENTS);
        if (fabricRoot != null && !(fabricRoot instanceof CompoundTag)) {
            throw new MigrationException(FABRIC_ATTACHMENTS + " is not a compound at " + holderPos);
        }
        if (neoRoot != null && !(neoRoot instanceof CompoundTag)) {
            throw new MigrationException(NEOFORGE_ATTACHMENTS + " is not a compound at " + holderPos);
        }
        CompoundTag fabric = compoundOrNull(fabricRoot);
        CompoundTag neo = compoundOrNull(neoRoot);
        Tag legacyTag = fabric == null ? null : fabric.get(BLOCK_FILTER_ID);
        Tag targetTag = neo == null ? null : neo.get(BLOCK_FILTER_ID);

        if (targetTag != null) {
            if (!(targetTag instanceof CompoundTag)) {
                throw new MigrationException("NeoForge block_filter attachment is not a compound at " + holderPos);
            }
            if (legacyTag != null)warnings.add("NeoForge attachment wins; legacy Fabric payload was retained");
            return new Result(legacyTag == null ? Status.ALREADY_NEOFORGE : Status.NEOFORGE_WINS_CONFLICT,
                    result, warnings);
        }
        if (legacyTag == null)return new Result(Status.NO_LEGACY, result, warnings);
        if (!(legacyTag instanceof CompoundTag legacy)) {
            throw new MigrationException("Legacy block_filter attachment is not a compound at " + holderPos);
        }

        CompoundTag converted = convertPayload(legacy, holderPos);
        if (neo == null) {
            neo = new CompoundTag();
            result.put(NEOFORGE_ATTACHMENTS, neo);
        }
        neo.put(BLOCK_FILTER_ID, converted);
        // Remove only the converted key. Other Fabric attachments are outside
        // this migration and must remain available to their own converters.
        fabric.remove(BLOCK_FILTER_ID);
        if (fabric.isEmpty())result.remove(FABRIC_ATTACHMENTS);
        warnings.add("ItemStack filter payload copied verbatim; run the global 1.21.11 -> 1.21.1 component converter before deployment");
        return new Result(Status.CONVERTED, result, warnings);
    }

    /** Convert one legacy payload, without touching attachment namespaces. */
    public static CompoundTag convertPayload(CompoundTag legacy, BlockPos holderPos) {
        Objects.requireNonNull(legacy, "legacy");
        Objects.requireNonNull(holderPos, "holderPos");
        int[] sourcePos = coordinates(legacy.get("pos"), "pos");
        if (sourcePos[0] != holderPos.getX() || sourcePos[1] != holderPos.getY() || sourcePos[2] != holderPos.getZ()) {
            throw new MigrationException("Legacy block_filter pos " + format(sourcePos)
                    + " does not match block entity " + holderPos);
        }

        CompoundTag out = new CompoundTag();
        ListTag connected = new ListTag();
        Tag connectedTag = legacy.get("connected");
        if (connectedTag == null || !(connectedTag instanceof ListTag list)) {
            throw new MigrationException("Legacy block_filter connected must be a list at " + holderPos);
        }
        Set<BlockPos> seen = new LinkedHashSet<>();
        for (int i = 0; i < list.size(); i++) {
            int[] absolute = coordinates(list.get(i), "connected[" + i + "]");
            BlockPos absolutePos = new BlockPos(absolute[0], absolute[1], absolute[2]);
            if (!seen.add(absolutePos))continue;
            CompoundTag relative = new CompoundTag();
            relative.putInt("x", absolute[0] - holderPos.getX());
            relative.putInt("y", absolute[1] - holderPos.getY());
            relative.putInt("z", absolute[2] - holderPos.getZ());
            connected.add(relative);
        }
        out.put("connected", connected);

        out.putBoolean("skip", readBoolean(legacy.get("skip"), "skip"));
        String side = readString(legacy.get("side"), "side").toLowerCase(Locale.ROOT);
        if (Direction.byName(side) == null)throw new MigrationException("Unknown block_filter side: " + side);
        out.putString("side", side);
        Tag filter = legacy.get("filter");
        if (filter != null && !(filter instanceof CompoundTag)) {
            throw new MigrationException("Legacy block_filter filter is not a compound at " + holderPos);
        }
        if (filter instanceof CompoundTag filterTag && !filterTag.isEmpty())out.put("filter", filterTag.copy());
        out.putInt("priority", priorityOrdinal(legacy.get("priority")));
        out.putBoolean("keepLast", readBoolean(legacy.get("keep_last"), "keep_last"));
        return out;
    }

    /** Returns true for the target 2.4 attachment shape (used by fixtures). */
    public static boolean isNeoForgePayload(CompoundTag payload) {
        return payload != null && payload.contains("connected") && payload.contains("priority")
                && payload.contains("keepLast") && !payload.contains("pos") && !payload.contains("keep_last");
    }

    private static CompoundTag compoundOrNull(Tag tag) {
        return tag instanceof CompoundTag compound ? compound : null;
    }

    private static int[] coordinates(Tag tag, String field) {
        if (tag instanceof IntArrayTag ints) {
            int[] value = ints.getAsIntArray();
            if (value.length == 3)return value.clone();
        } else if (tag instanceof ListTag list) {
            if (list.size() == 3) {
                int[] value = new int[3];
                for (int i = 0; i < 3; i++) {
                    Tag element = list.get(i);
                    if (!(element instanceof NumericTag numeric))throw badCoordinates(field);
                    value[i] = numeric.getAsInt();
                }
                return value;
            }
        } else if (tag instanceof CompoundTag compound
                && compound.contains("x") && compound.contains("y") && compound.contains("z")) {
            return new int[] {compound.getInt("x"), compound.getInt("y"), compound.getInt("z")};
        }
        throw badCoordinates(field);
    }

    private static MigrationException badCoordinates(String field) {
        return new MigrationException("Legacy block_filter " + field + " must contain exactly three integer coordinates");
    }

    private static boolean readBoolean(Tag tag, String field) {
        if (tag == null)return false;
        if (tag instanceof NumericTag numeric)return numeric.getAsInt() != 0;
        if (tag instanceof StringTag) {
            String value = tag.getAsString();
            if ("true".equalsIgnoreCase(value))return true;
            if ("false".equalsIgnoreCase(value))return false;
        }
        throw new MigrationException("Legacy block_filter " + field + " must be boolean/numeric");
    }

    private static String readString(Tag tag, String field) {
        if (!(tag instanceof StringTag))
            throw new MigrationException("Legacy block_filter " + field + " must be a string");
        return tag.getAsString();
    }

    private static int priorityOrdinal(Tag tag) {
        if (tag instanceof NumericTag numeric) {
            int value = numeric.getAsInt();
            if (value >= 0 && value <= 4)return value;
            throw new MigrationException("NeoForge priority ordinal out of range: " + value);
        }
        String value = readString(tag, "priority").toLowerCase(Locale.ROOT);
        return switch (value) {
            case "lowest" -> 0;
            case "low" -> 1;
            case "normal" -> 2;
            case "high" -> 3;
            case "highest" -> 4;
            default -> throw new MigrationException("Unknown legacy block_filter priority: " + value);
        };
    }

    private static String format(int[] pos) {
        return "[" + pos[0] + ", " + pos[1] + ", " + pos[2] + "]";
    }

    public static final class MigrationException extends IllegalArgumentException {
        private static final long serialVersionUID = 1L;

        public MigrationException(String message) {
            super(message);
        }
    }
}
