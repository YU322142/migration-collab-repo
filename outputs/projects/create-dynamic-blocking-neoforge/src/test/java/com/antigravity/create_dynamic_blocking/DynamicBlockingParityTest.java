package com.antigravity.create_dynamic_blocking;

public final class DynamicBlockingParityTest {
    private static final double EPSILON = 1.0e-12;

    private DynamicBlockingParityTest() {
    }

    public static void main(String[] args) {
        assertClose(72.0, DynamicBlockingMath.scanDistance(0.0, 1.0, 60.0, 128.0));
        assertClose(100.0, DynamicBlockingMath.scanDistance(10.0, 1.0, 60.0, 128.0));
        assertClose(128.0, DynamicBlockingMath.scanDistance(100.0, 0.25, 60.0, 128.0));
        assertClose(128.0, DynamicBlockingMath.scanDistance(2.0, 0.0, 60.0, 128.0));
        assertClose(Math.sqrt(17.0), DynamicBlockingMath.maxSafeSpeed(1.0, 10.0));
        assertClose(Math.sqrt(0.17), DynamicBlockingMath.maxSafeSpeed(0.0, 10.0));
        assertClose(0.0, DynamicBlockingMath.maxSafeSpeed(1.0, 0.0));
    }

    private static void assertClose(double expected, double actual) {
        if (!Double.isFinite(actual) || Math.abs(expected - actual) > EPSILON) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
    }
}
