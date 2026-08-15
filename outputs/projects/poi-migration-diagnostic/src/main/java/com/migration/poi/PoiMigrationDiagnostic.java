package com.migration.poi;

import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.logging.LogUtils;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.UuidArgument;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtIo;
import net.minecraft.nbt.NbtAccounter;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.ai.village.poi.PoiManager;
import net.minecraft.world.entity.ai.village.poi.PoiType;
import net.minecraft.world.entity.npc.Villager;
import net.minecraft.world.level.ChunkPos;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.entity.EntityJoinLevelEvent;
import net.neoforged.neoforge.event.entity.EntityLeaveLevelEvent;
import net.neoforged.neoforge.event.entity.living.LivingDeathEvent;
import org.slf4j.Logger;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

@Mod(PoiMigrationDiagnostic.MOD_ID)
public final class PoiMigrationDiagnostic {
    public static final String MOD_ID = "poi_migration_diagnostic";
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final Set<UUID> WATCHED_VILLAGERS = loadWatchedVillagers();

    private static Set<UUID> loadWatchedVillagers() {
        String configured = System.getProperty(
                "migration.poi.watchedVillagers",
                "00000000-0000-4000-8000-000000000101,"
                        + "00000000-0000-4000-8000-000000000102,"
                        + "00000000-0000-4000-8000-000000000103,"
                        + "00000000-0000-4000-8000-000000000104"
        );
        Set<UUID> result = new HashSet<>();
        for (String token : configured.split(",")) {
            String value = token.trim();
            if (!value.isEmpty()) {
                result.add(UUID.fromString(value));
            }
        }
        if (result.size() != 4) {
            throw new IllegalArgumentException(
                    "migration.poi.watchedVillagers must contain exactly four UUIDs"
            );
        }
        return Set.copyOf(result);
    }
    private static final List<String> EXPECTED_POI_TYPES = List.of(
            "minecraft:armorer",
            "minecraft:bee_nest",
            "minecraft:beehive",
            "minecraft:butcher",
            "minecraft:cartographer",
            "minecraft:cleric",
            "minecraft:farmer",
            "minecraft:fisherman",
            "minecraft:fletcher",
            "minecraft:home",
            "minecraft:leatherworker",
            "minecraft:librarian",
            "minecraft:lightning_rod",
            "minecraft:mason",
            "minecraft:meeting",
            "minecraft:nether_portal",
            "minecraft:shepherd",
            "minecraft:toolsmith",
            "minecraft:weaponsmith",
            "kaleidoscope_cookery:chopping_board",
            "kaleidoscope_cookery:pot",
            "kaleidoscope_cookery:stockpot",
            "kaleidoscope_cookery:stove"
    );

    public PoiMigrationDiagnostic() {
        NeoForge.EVENT_BUS.addListener(this::registerCommands);
        NeoForge.EVENT_BUS.addListener(this::onEntityJoin);
        NeoForge.EVENT_BUS.addListener(this::onEntityLeave);
        NeoForge.EVENT_BUS.addListener(this::onLivingDeath);
    }

    private void onEntityJoin(EntityJoinLevelEvent event) {
        Entity entity = event.getEntity();
        if (!WATCHED_VILLAGERS.contains(entity.getUUID())) {
            return;
        }
        LOGGER.warn("VILLAGER_JOIN_RESULT uuid={} loaded_from_disk={} removed={} should_save={} passenger={} pos={},{},{}",
                entity.getUUID(), event.loadedFromDisk(), entity.isRemoved(), entity.shouldBeSaved(),
                entity.isPassenger(), entity.getX(), entity.getY(), entity.getZ());
    }

    private void onEntityLeave(EntityLeaveLevelEvent event) {
        Entity entity = event.getEntity();
        if (!WATCHED_VILLAGERS.contains(entity.getUUID())) {
            return;
        }
        LOGGER.warn("VILLAGER_LEAVE_RESULT uuid={} reason={} removed={} should_save={} passenger={} pos={},{},{}",
                entity.getUUID(), entity.getRemovalReason(), entity.isRemoved(), entity.shouldBeSaved(),
                entity.isPassenger(), entity.getX(), entity.getY(), entity.getZ());
        LOGGER.warn("VILLAGER_LEAVE_STACK uuid={}", entity.getUUID(),
                new IllegalStateException("watched villager removal call stack"));
    }

    private void onLivingDeath(LivingDeathEvent event) {
        if (!WATCHED_VILLAGERS.contains(event.getEntity().getUUID())) {
            return;
        }
        LOGGER.warn("VILLAGER_DEATH_RESULT uuid={} source={} pos={},{},{}",
                event.getEntity().getUUID(), event.getSource().getMsgId(),
                event.getEntity().getX(), event.getEntity().getY(), event.getEntity().getZ());
    }

    private void registerCommands(RegisterCommandsEvent event) {
        event.getDispatcher().register(Commands.literal("poi_migration")
                .requires(source -> source.hasPermission(4))
                .then(Commands.literal("registry").executes(context -> auditRegistry(context.getSource())))
                .then(Commands.literal("inspect")
                        .then(Commands.argument("x", IntegerArgumentType.integer())
                                .then(Commands.argument("y", IntegerArgumentType.integer())
                                        .then(Commands.argument("z", IntegerArgumentType.integer())
                                                .executes(context -> inspectPoi(
                                                        context.getSource(),
                                                        IntegerArgumentType.getInteger(context, "x"),
                                                        IntegerArgumentType.getInteger(context, "y"),
                                                        IntegerArgumentType.getInteger(context, "z")
                                                ))))))
                .then(Commands.literal("load")
                        .then(Commands.argument("x", IntegerArgumentType.integer())
                                .then(Commands.argument("z", IntegerArgumentType.integer())
                                        .executes(context -> loadChunk(
                                                context.getSource(),
                                                IntegerArgumentType.getInteger(context, "x"),
                                                IntegerArgumentType.getInteger(context, "z")
                                        )))))
                .then(Commands.literal("villager")
                        .then(Commands.argument("uuid", UuidArgument.uuid())
                                .executes(context -> dumpVillager(
                                        context.getSource(),
                                        UuidArgument.getUuid(context, "uuid")
                                ))))
                .then(Commands.literal("load_raw")
                        .then(Commands.argument("path", StringArgumentType.greedyString())
                                .executes(context -> loadRawEntity(
                                        context.getSource(),
                                        StringArgumentType.getString(context, "path"),
                                        false
                                ))))
                .then(Commands.literal("spawn_raw")
                        .then(Commands.argument("path", StringArgumentType.greedyString())
                                .executes(context -> loadRawEntity(
                                        context.getSource(),
                                        StringArgumentType.getString(context, "path"),
                                        true
                                )))));
    }

    private static int auditRegistry(CommandSourceStack source) {
        List<String> missing = EXPECTED_POI_TYPES.stream()
                .filter(id -> !BuiltInRegistries.POINT_OF_INTEREST_TYPE.containsKey(ResourceLocation.parse(id)))
                .toList();
        boolean chefPresent = BuiltInRegistries.VILLAGER_PROFESSION.containsKey(
                ResourceLocation.parse("kaleidoscope_cookery:chef"));
        String result = "POI_REGISTRY_RESULT expected=" + EXPECTED_POI_TYPES.size()
                + " missing=" + missing + " chef=" + chefPresent;
        LOGGER.info(result);
        source.sendSuccess(() -> Component.literal(result), false);
        return missing.isEmpty() && chefPresent ? 1 : 0;
    }

    private static int inspectPoi(CommandSourceStack source, int x, int y, int z) {
        ServerLevel level = source.getLevel();
        BlockPos pos = new BlockPos(x, y, z);
        PoiManager manager = level.getPoiManager();
        Optional<Holder<PoiType>> type = manager.getType(pos);
        String id = type.flatMap(Holder::unwrapKey)
                .map(key -> key.location().toString())
                .orElse("<missing>");
        int freeTickets = manager.getFreeTickets(pos);
        manager.flush(new ChunkPos(pos));
        String result = "POI_INSPECT_RESULT dimension=" + level.dimension().location()
                + " pos=" + x + "," + y + "," + z
                + " type=" + id + " free_tickets=" + freeTickets;
        LOGGER.info(result);
        source.sendSuccess(() -> Component.literal(result), false);
        return type.isPresent() ? 1 : 0;
    }

    private static int loadChunk(CommandSourceStack source, int blockX, int blockZ) {
        ServerLevel level = source.getLevel();
        ChunkPos chunk = new ChunkPos(new BlockPos(blockX, level.getMinBuildHeight(), blockZ));
        level.getChunk(chunk.x, chunk.z);
        String result = "POI_LOAD_RESULT dimension=" + level.dimension().location()
                + " chunk=" + chunk.x + "," + chunk.z
                + " entities_loaded=" + level.areEntitiesLoaded(chunk.toLong());
        LOGGER.info(result);
        source.sendSuccess(() -> Component.literal(result), false);
        return 1;
    }

    private static int dumpVillager(CommandSourceStack source, UUID uuid) {
        Entity entity = source.getLevel().getEntity(uuid);
        if (!(entity instanceof Villager villager)) {
            String result = "VILLAGER_DUMP_RESULT uuid=" + uuid + " status=missing";
            LOGGER.info(result);
            source.sendFailure(Component.literal(result));
            return 0;
        }

        CompoundTag tag = new CompoundTag();
        villager.saveWithoutId(tag);
        Path outputRoot = Path.of(System.getProperty("poiDiagnostic.output", "poi-diagnostic"));
        Path output = outputRoot.resolve(uuid + ".nbt");
        Path temporary = output.resolveSibling(output.getFileName() + ".tmp");
        try {
            Files.createDirectories(outputRoot);
            NbtIo.writeCompressed(tag, temporary);
            try {
                Files.move(temporary, output, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (IOException ignored) {
                Files.move(temporary, output, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot write villager diagnostic NBT " + output, exception);
        }

        String profession = BuiltInRegistries.VILLAGER_PROFESSION.getKey(
                villager.getVillagerData().getProfession()).toString();
        String result = "VILLAGER_DUMP_RESULT uuid=" + uuid
                + " status=present profession=" + profession
                + " level=" + villager.getVillagerData().getLevel()
                + " xp=" + villager.getVillagerXp()
                + " offers=" + villager.getOffers().size()
                + " pos=" + villager.getX() + "," + villager.getY() + "," + villager.getZ()
                + " removed=" + villager.isRemoved()
                + " should_save=" + villager.shouldBeSaved()
                + " passenger=" + villager.isPassenger()
                + " entities_loaded=" + source.getLevel().areEntitiesLoaded(villager.chunkPosition().toLong())
                + " output=" + output.toAbsolutePath();
        LOGGER.info(result);
        source.sendSuccess(() -> Component.literal(result), false);
        return 1;
    }

    private static int loadRawEntity(CommandSourceStack source, String rawPath, boolean spawn) {
        Path path = Path.of(rawPath);
        try {
            CompoundTag tag = NbtIo.readCompressed(path, NbtAccounter.unlimitedHeap());
            String rawId = tag.getString("id");
            Optional<Entity> loaded = EntityType.create(tag, source.getLevel());
            if (loaded.isEmpty()) {
                String result = "RAW_ENTITY_RESULT status=missing id=" + rawId + " path=" + path;
                LOGGER.warn(result);
                source.sendFailure(Component.literal(result));
                return 0;
            }
            Entity entity = loaded.get();
            if (spawn && !source.getLevel().addFreshEntity(entity)) {
                String result = "RAW_ENTITY_RESULT status=add_failed id=" + rawId
                        + " uuid=" + entity.getUUID() + " path=" + path;
                LOGGER.warn(result);
                source.sendFailure(Component.literal(result));
                return 0;
            }
            String type = BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString();
            String profession = "-";
            int offers = -1;
            if (entity instanceof Villager villager) {
                profession = BuiltInRegistries.VILLAGER_PROFESSION
                        .getKey(villager.getVillagerData().getProfession()).toString();
                offers = villager.getOffers().size();
            }
            String result = "RAW_ENTITY_RESULT status=present spawned=" + spawn + " id=" + rawId
                    + " type=" + type + " profession=" + profession
                    + " offers=" + offers + " uuid=" + entity.getUUID()
                    + " path=" + path;
            LOGGER.info(result);
            source.sendSuccess(() -> Component.literal(result), false);
            return 1;
        } catch (Exception exception) {
            String result = "RAW_ENTITY_RESULT status=error path=" + path
                    + " error=" + exception.getClass().getSimpleName() + ":" + exception.getMessage();
            LOGGER.error(result, exception);
            source.sendFailure(Component.literal(result));
            return 0;
        }
    }
}
