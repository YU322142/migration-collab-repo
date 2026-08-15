package dev.migration.create_chute_unload_guard;

public final class ChuteGuardDecision {
    private ChuteGuardDecision() {
    }

    public static boolean shouldRemove(boolean hasLevel, boolean chuteAtPosition) {
        return !hasLevel || !chuteAtPosition;
    }
}
