package com.bmt.waypointfire;

import com.bmt.waypointfire.mixin.GameRulesIntegerValueAccessor;
import com.mojang.serialization.DynamicLike;
import java.util.Collections;
import java.util.Map;
import java.util.WeakHashMap;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.GameRules;

public final class CompatGameRules {
    public static final String FIRE_RADIUS_ID = "minecraft:fire_spread_radius_around_player";
    public static final String LOCATOR_BAR_ID = "minecraft:locator_bar";
    private static final String MIGRATION_MARKER_ID = "waypoint_fire_equivalence:migrated";

    public static final GameRules.Key<GameRules.IntegerValue> FIRE_RADIUS = GameRules.register(
        FIRE_RADIUS_ID,
        GameRules.Category.UPDATES,
        GameRulesIntegerValueAccessor.waypointFire$create(128, -1, Integer.MAX_VALUE, (server, value) -> {})
    );
    public static final GameRules.Key<GameRules.BooleanValue> LOCATOR_BAR = GameRules.register(
        LOCATOR_BAR_ID,
        GameRules.Category.PLAYER,
        GameRules.BooleanValue.create(true, (server, value) -> {})
    );
    public static final GameRules.Key<GameRules.BooleanValue> MIGRATION_MARKER = GameRules.register(
        MIGRATION_MARKER_ID,
        GameRules.Category.MISC,
        GameRules.BooleanValue.create(false, (server, value) -> {})
    );

    private static final Map<GameRules, LoadProbe> LOAD_PROBES = Collections.synchronizedMap(new WeakHashMap<>());

    private CompatGameRules() {}

    /** Forces registration before the first world GameRules instance is constructed. */
    public static void bootstrap() {
    }

    public static void captureLoad(GameRules rules, DynamicLike<?> source) {
        LOAD_PROBES.put(rules, new LoadProbe(hasString(source, FIRE_RADIUS_ID), hasString(source, LOCATOR_BAR_ID)));
    }

    public static void migrateLoadedRules(MinecraftServer server) {
        GameRules rules = server.getGameRules();
        if (rules.getBoolean(MIGRATION_MARKER)) {
            return;
        }

        LoadProbe probe = LOAD_PROBES.remove(rules);
        if (probe != null) {
            if (!probe.hadFireRadius()) {
                int legacyEquivalent = ParitySemantics.legacyFireRadius(rules.getBoolean(GameRules.RULE_DOFIRETICK));
                rules.getRule(FIRE_RADIUS).set(legacyEquivalent, server);
            }
            if (!probe.hadLocatorBar()) {
                rules.getRule(LOCATOR_BAR).set(false, server);
            }
        }
        // The canonical radius now owns fire ticking; retain the old value in the migrated radius.
        rules.getRule(GameRules.RULE_DOFIRETICK).set(true, server);
        rules.getRule(MIGRATION_MARKER).set(true, server);
    }

    private static boolean hasString(DynamicLike<?> source, String key) {
        return source.get(key).asString().result().isPresent();
    }

    private record LoadProbe(boolean hadFireRadius, boolean hadLocatorBar) {}
}
