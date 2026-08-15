package com.bmt.happyghast_equivalence;

public final class RideStatSemanticsTest {
    private RideStatSemanticsTest() {
    }

    public static void main(String[] args) {
        assertEquals(0, RideStatSemantics.distanceInCentimeters(0.0D, 0.0D, 0.0D));
        assertEquals(100, RideStatSemantics.distanceInCentimeters(1.0D, 0.0D, 0.0D));
        assertEquals(500, RideStatSemantics.distanceInCentimeters(3.0D, 4.0D, 0.0D));
        assertEquals(0, RideStatSemantics.distanceInCentimeters(0.004D, 0.0D, 0.0D));
        assertEquals(1, RideStatSemantics.distanceInCentimeters(0.005D, 0.0D, 0.0D));

        assertFalse(RideStatSemantics.hasMovement(0.0D, -0.0D, 0.0D));
        assertTrue(RideStatSemantics.hasMovement(0.0D, 0.0D, Double.MIN_VALUE));

        assertEquals(RideStatSemantics.HAPPY_GHAST_STAT,
                RideStatSemantics.statisticForVehicle(RideStatSemantics.HAPPY_GHAST_ENTITY));
        assertEquals(RideStatSemantics.NAUTILUS_STAT,
                RideStatSemantics.statisticForVehicle(RideStatSemantics.NAUTILUS_ENTITY));
        assertEquals(RideStatSemantics.NAUTILUS_STAT,
                RideStatSemantics.statisticForVehicle(RideStatSemantics.ZOMBIE_NAUTILUS_ENTITY));
        assertEquals(null, RideStatSemantics.statisticForVehicle("minecraft:boat"));
    }

    private static void assertTrue(boolean value) {
        if (!value) {
            throw new AssertionError("Expected true");
        }
    }

    private static void assertFalse(boolean value) {
        if (value) {
            throw new AssertionError("Expected false");
        }
    }

    private static void assertEquals(Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError("Expected " + expected + " but got " + actual);
        }
    }
}
