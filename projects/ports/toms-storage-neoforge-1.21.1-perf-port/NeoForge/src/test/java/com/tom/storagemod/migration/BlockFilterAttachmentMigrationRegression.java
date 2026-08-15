package com.tom.storagemod.migration;

import java.util.List;

import net.minecraft.core.BlockPos;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.IntArrayTag;
import net.minecraft.nbt.ListTag;

/** Small offline fixture for the seven audited Fabric block-filter records. */
public final class BlockFilterAttachmentMigrationRegression {
    public static void main(String[] args) {
        testPayloadConversionWithFilters();
        testSevenAuditedLocations();
        testAllPriorities();
        testIdempotentBlockEntityConversion();
        testTargetWinsConflict();
        testMalformedPositionFailsClosed();
        System.out.println("Block-filter attachment migration regression checks passed");
    }

    private static void testSevenAuditedLocations() {
        List<Fixture> fixtures = List.of(
                new Fixture(new BlockPos(-221, 62, -113), "lowest"),
                new Fixture(new BlockPos(-190, 65, -74), "normal"),
                new Fixture(new BlockPos(-190, 63, -79), "highest"),
                new Fixture(new BlockPos(-190, 65, -79), "normal"),
                new Fixture(new BlockPos(-83, 48, -48), "normal"),
                new Fixture(new BlockPos(27356, 62, -12900), "highest"),
                new Fixture(new BlockPos(27356, 62, -12902), "highest"));
        for (Fixture fixture : fixtures) {
            CompoundTag target = BlockFilterAttachmentMigration.convertPayload(
                    source(fixture.pos(), fixture.priority(), false, false), fixture.pos());
            CompoundTag self = target.getList("connected", 10).getCompound(0);
            check(self.getInt("x") == 0 && self.getInt("y") == 0 && self.getInt("z") == 0,
                    "audited self coordinate at " + fixture.pos());
        }
        check(fixtures.size() == 7, "audited attachment count changed");
    }

    private static void testPayloadConversionWithFilters() {
        BlockPos pos = new BlockPos(27356, 62, -12900);
        CompoundTag source = source(pos, "highest", true, true);
        CompoundTag filter = new CompoundTag();
        filter.putString("id", "toms_storage:item_filter");
        filter.putInt("count", 1);
        source.put("filter", filter);
        CompoundTag target = BlockFilterAttachmentMigration.convertPayload(source, pos);
        check(BlockFilterAttachmentMigration.isNeoForgePayload(target), "converted payload shape");
        check(target.getInt("priority") == 4, "highest priority ordinal");
        check(target.getBoolean("skip"), "skip conversion");
        check(target.getBoolean("keepLast"), "keepLast conversion");
        check(!target.contains("pos") && !target.contains("keep_last"), "legacy keys removed");
        check(target.getList("connected", 10).getCompound(0).getInt("x") == 0, "relative x");
        check(target.getCompound("filter").getString("id").equals("toms_storage:item_filter"), "filter retained");
        check(source.contains("pos") && source.contains("keep_last"), "source not mutated");
    }

    private static void testAllPriorities() {
        List<String> names = List.of("lowest", "low", "normal", "high", "highest");
        BlockPos pos = new BlockPos(-190, 63, -79);
        for (int i = 0; i < names.size(); i++) {
            CompoundTag target = BlockFilterAttachmentMigration.convertPayload(source(pos, names.get(i), false, false), pos);
            check(target.getInt("priority") == i, "priority mapping for " + names.get(i));
        }
    }

    private static void testIdempotentBlockEntityConversion() {
        BlockPos pos = new BlockPos(-221, 62, -113);
        CompoundTag be = new CompoundTag();
        CompoundTag fabric = new CompoundTag();
        fabric.put(BlockFilterAttachmentMigration.BLOCK_FILTER_ID, source(pos, "lowest", false, false));
        be.put(BlockFilterAttachmentMigration.FABRIC_ATTACHMENTS, fabric);
        var once = BlockFilterAttachmentMigration.migrateBlockEntity(be, pos);
        check(once.status() == BlockFilterAttachmentMigration.Status.CONVERTED, "first conversion status");
        var twice = BlockFilterAttachmentMigration.migrateBlockEntity(once.blockEntity(), pos);
        check(twice.status() == BlockFilterAttachmentMigration.Status.ALREADY_NEOFORGE, "second conversion is a no-op");
        check(twice.blockEntity().equals(once.blockEntity()), "second conversion preserves bytes");
    }

    private static void testTargetWinsConflict() {
        BlockPos pos = new BlockPos(-190, 65, -74);
        CompoundTag be = new CompoundTag();
        CompoundTag fabric = new CompoundTag();
        fabric.put(BlockFilterAttachmentMigration.BLOCK_FILTER_ID, source(pos, "lowest", false, false));
        CompoundTag neo = new CompoundTag();
        CompoundTag target = BlockFilterAttachmentMigration.convertPayload(source(pos, "highest", false, false), pos);
        neo.put(BlockFilterAttachmentMigration.BLOCK_FILTER_ID, target);
        be.put(BlockFilterAttachmentMigration.FABRIC_ATTACHMENTS, fabric);
        be.put(BlockFilterAttachmentMigration.NEOFORGE_ATTACHMENTS, neo);
        var result = BlockFilterAttachmentMigration.migrateBlockEntity(be, pos);
        check(result.status() == BlockFilterAttachmentMigration.Status.NEOFORGE_WINS_CONFLICT, "target wins conflict");
        check(result.blockEntity().getCompound(BlockFilterAttachmentMigration.NEOFORGE_ATTACHMENTS)
                .getCompound(BlockFilterAttachmentMigration.BLOCK_FILTER_ID).getInt("priority") == 4,
                "target payload was not overwritten");
        check(!result.warnings().isEmpty(), "conflict is reported");
    }

    private static void testMalformedPositionFailsClosed() {
        BlockPos actual = new BlockPos(1, 2, 3);
        boolean failed = false;
        try {
            BlockFilterAttachmentMigration.convertPayload(source(new BlockPos(4, 2, 3), "normal", false, false), actual);
        } catch (BlockFilterAttachmentMigration.MigrationException expected) {
            failed = true;
        }
        check(failed, "position mismatch must fail closed");
    }

    private static CompoundTag source(BlockPos pos, String priority, boolean skip, boolean keepLast) {
        CompoundTag source = new CompoundTag();
        source.put("pos", new IntArrayTag(new int[] {pos.getX(), pos.getY(), pos.getZ()}));
        ListTag connected = new ListTag();
        connected.add(new IntArrayTag(new int[] {pos.getX(), pos.getY(), pos.getZ()}));
        connected.add(new IntArrayTag(new int[] {pos.getX() + 1, pos.getY(), pos.getZ()}));
        connected.add(new IntArrayTag(new int[] {pos.getX() + 1, pos.getY(), pos.getZ()}));
        source.put("connected", connected);
        source.putInt("skip", skip ? 1 : 0);
        source.putString("side", "down");
        source.putString("priority", priority);
        source.putInt("keep_last", keepLast ? 1 : 0);
        return source;
    }

    private static void check(boolean condition, String message) {
        if (!condition)throw new AssertionError(message);
    }

    private record Fixture(BlockPos pos, String priority) {
    }
}
