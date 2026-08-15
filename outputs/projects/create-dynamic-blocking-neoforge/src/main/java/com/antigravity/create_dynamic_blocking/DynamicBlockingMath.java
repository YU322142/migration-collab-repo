package com.antigravity.create_dynamic_blocking;

final class DynamicBlockingMath {
    private DynamicBlockingMath() {
    }

    static double scanDistance(
            double currentSpeed,
            double acceleration,
            double slowdownDistance,
            double maxScanDistance
    ) {
        double brakingDistance = currentSpeed * currentSpeed / (2.0 * Math.max(0.01, acceleration));
        double requiredScanDistance = Math.max(brakingDistance * 2.0, slowdownDistance * 1.2);
        return Math.min(maxScanDistance, requiredScanDistance);
    }

    static double maxSafeSpeed(double acceleration, double availableDistance) {
        return Math.sqrt(2.0 * Math.max(0.01, acceleration) * availableDistance * 0.85);
    }
}
