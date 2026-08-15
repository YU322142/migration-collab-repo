package com.bmt.happyghast_equivalence;

/** Pure 1.21.11 riding-stat semantics, kept independent from backport classes. */
public final class RideStatSemantics {
    public static final String HAPPY_GHAST_ENTITY = "minecraft:happy_ghast";
    public static final String NAUTILUS_ENTITY = "minecraft:nautilus";
    public static final String ZOMBIE_NAUTILUS_ENTITY = "minecraft:zombie_nautilus";
    public static final String HAPPY_GHAST_STAT = "minecraft:happy_ghast_one_cm";
    public static final String NAUTILUS_STAT = "minecraft:nautilus_one_cm";

    private RideStatSemantics() {
    }

    public static boolean hasMovement(double deltaX, double deltaY, double deltaZ) {
        return deltaX != 0.0D || deltaY != 0.0D || deltaZ != 0.0D;
    }

    public static int distanceInCentimeters(double deltaX, double deltaY, double deltaZ) {
        return Math.round((float)Math.sqrt(
                deltaX * deltaX + deltaY * deltaY + deltaZ * deltaZ) * 100.0F);
    }

    public static String statisticForVehicle(String vehicleId) {
        if (HAPPY_GHAST_ENTITY.equals(vehicleId)) {
            return HAPPY_GHAST_STAT;
        }
        if (NAUTILUS_ENTITY.equals(vehicleId) || ZOMBIE_NAUTILUS_ENTITY.equals(vehicleId)) {
            return NAUTILUS_STAT;
        }
        return null;
    }
}
