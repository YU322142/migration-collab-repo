package com.bmt.waypointfire;

import java.util.stream.DoubleStream;

/** Pure boundary predicates shared by runtime code and smoke tests. */
public final class ParitySemantics {
    private ParitySemantics() {}

    public static int legacyFireRadius(boolean doFireTick) {
        return doFireTick ? -1 : 0;
    }

    public static boolean fireSpreadAllowed(int radius, DoubleStream nonSpectatorPlayerDistances) {
        if (radius == -1) {
            return true;
        }
        if (radius <= 0) {
            return false;
        }
        return nonSpectatorPlayerDistances.anyMatch(distance -> distance < radius);
    }

    public static boolean waypointInRange(double transmit, double receive, double distance) {
        return transmit > 0.0 && receive > 0.0 && distance < Math.min(transmit, receive);
    }

    public static boolean waypointVisible(
        boolean receiverSpectator,
        boolean transmitterSpectator,
        boolean invisibleToReceiver,
        double transmit,
        double receive,
        double distance
    ) {
        if (transmit <= 0.0) {
            return false;
        }
        if (receiverSpectator) {
            return true;
        }
        return !transmitterSpectator
            && !invisibleToReceiver
            && waypointInRange(transmit, receive, distance);
    }

    public static int parseHexColor(String value) {
        try {
            return switch (value.length()) {
                case 3 -> rgb(
                    duplicateHexDigit(Integer.parseInt(value, 0, 1, 16)),
                    duplicateHexDigit(Integer.parseInt(value, 1, 2, 16)),
                    duplicateHexDigit(Integer.parseInt(value, 2, 3, 16))
                );
                case 6 -> rgb(
                    Integer.parseInt(value, 0, 2, 16),
                    Integer.parseInt(value, 2, 4, 16),
                    Integer.parseInt(value, 4, 6, 16)
                );
                default -> throw new IllegalArgumentException(value);
            };
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(value, exception);
        }
    }

    private static int duplicateHexDigit(int value) {
        return value * 17;
    }

    private static int rgb(int red, int green, int blue) {
        return red << 16 | green << 8 | blue;
    }
}
