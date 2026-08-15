package dev.migration.create_carriage_orientation_guard;

import net.minecraft.core.Direction;

public final class CarriageOrientationDecision {
    private CarriageOrientationDecision() {
    }

    public enum Resolution {
        KEEP_RAW,
        DERIVE_FROM_ASSEMBLY,
        SAFE_SOUTH
    }

    public static Resolution choose(boolean rawHorizontal, boolean assemblyHorizontal) {
        if (rawHorizontal) {
            return Resolution.KEEP_RAW;
        }
        return assemblyHorizontal ? Resolution.DERIVE_FROM_ASSEMBLY : Resolution.SAFE_SOUTH;
    }

    /**
     * Return a horizontal orientation for every carriage read path.
     *
     * <p>Create stores a carriage entity's initial orientation clockwise from
     * the carriage assembly direction.  The 1.21.11 codec writes lowercase
     * direction names; Create 6.0.10's 1.21.1 enum reader is case-sensitive
     * and silently leaves the synchronized value at its vertical default.
     * Keeping this relationship in one pure helper makes the fallback easy to
     * test against every source carriage while leaving valid horizontal data
     * byte-for-byte and behaviorally untouched.</p>
     */
    public static Direction resolve(Direction raw, Direction assemblyDirection) {
        boolean rawHorizontal = raw != null && raw.getAxis().isHorizontal();
        boolean assemblyHorizontal = assemblyDirection != null
                && assemblyDirection.getAxis().isHorizontal();
        return switch (choose(rawHorizontal, assemblyHorizontal)) {
            case KEEP_RAW -> raw;
            case DERIVE_FROM_ASSEMBLY -> assemblyDirection.getClockWise();
            case SAFE_SOUTH -> Direction.SOUTH;
        };
    }
}
