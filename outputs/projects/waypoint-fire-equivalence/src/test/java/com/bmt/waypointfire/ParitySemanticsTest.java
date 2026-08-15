package com.bmt.waypointfire;

import java.util.stream.DoubleStream;

public final class ParitySemanticsTest {
    public static void main(String[] args) {
        require(ParitySemantics.legacyFireRadius(true) == -1, "legacy doFireTick true");
        require(ParitySemantics.legacyFireRadius(false) == 0, "legacy doFireTick false");

        require(!ParitySemantics.fireSpreadAllowed(0, DoubleStream.of(0.0)), "radius 0");
        require(ParitySemantics.fireSpreadAllowed(-1, DoubleStream.empty()), "radius -1");
        require(ParitySemantics.fireSpreadAllowed(128, DoubleStream.of(127.999)), "inside radius");
        require(!ParitySemantics.fireSpreadAllowed(128, DoubleStream.of(128.0)), "exact boundary");
        require(!ParitySemantics.fireSpreadAllowed(128, DoubleStream.of(129.0)), "outside radius");
        require(!ParitySemantics.fireSpreadAllowed(128, DoubleStream.empty()), "spectator-only/empty");

        require(ParitySemantics.waypointInRange(60_000_000.0, 60_000_000.0, 59_999_999.0), "waypoint inside");
        require(!ParitySemantics.waypointInRange(60_000_000.0, 60_000_000.0, 60_000_000.0), "waypoint boundary");
        require(!ParitySemantics.waypointInRange(0.0, 60_000_000.0, 0.0), "transmit disabled");
        require(!ParitySemantics.waypointInRange(60_000_000.0, 0.0, 0.0), "receive disabled");

        require(ParitySemantics.waypointVisible(false, false, false, 64.0, 64.0, 63.999), "visible waypoint");
        require(!ParitySemantics.waypointVisible(false, true, false, 64.0, 64.0, 1.0), "spectator transmitter hidden");
        require(!ParitySemantics.waypointVisible(false, false, true, 64.0, 64.0, 1.0), "invisible transmitter hidden");
        require(ParitySemantics.waypointVisible(true, true, true, 64.0, 0.0, 1000.0), "spectator receiver bypass");
        require(!ParitySemantics.waypointVisible(true, false, false, 0.0, 64.0, 1.0), "untracked transmitter hidden");

        require(ParitySemantics.parseHexColor("F00") == 0xFF0000, "three-digit hex color");
        require(ParitySemantics.parseHexColor("12abEF") == 0x12ABEF, "six-digit hex color");
        requireHexFailure("#F00");
        requireHexFailure("FFFF");
    }

    private static void require(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void requireHexFailure(String value) {
        try {
            ParitySemantics.parseHexColor(value);
            throw new AssertionError("expected hex parse failure: " + value);
        } catch (IllegalArgumentException expected) {
        }
    }
}
