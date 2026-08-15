package com.bmt.waypointfire.client;

import com.bmt.waypointfire.WaypointIcon;
import com.bmt.waypointfire.network.WaypointDeltaPayload;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.util.Mth;
import net.minecraft.world.phys.Vec3;

public final class WaypointHud {
    private static final int BAR_HALF_WIDTH = 91;
    private static final int DEFAULT_COLOR = 0xFF302C;

    private WaypointHud() {}

    public static void render(GuiGraphics graphics, net.minecraft.client.DeltaTracker deltaTracker) {
        Minecraft minecraft = Minecraft.getInstance();
        if (minecraft.player == null || minecraft.options.hideGui) {
            return;
        }
        int centerX = graphics.guiWidth() / 2;
        int y = graphics.guiHeight() - 49;
        for (WaypointDeltaPayload waypoint : ClientWaypointState.entries()) {
            float bearing = bearingDegrees(minecraft.player.position(), waypoint);
            float relative = Mth.wrapDegrees(bearing - minecraft.player.getYRot());
            int x = centerX + Math.round(Mth.clamp(relative / 90.0F, -1.0F, 1.0F) * BAR_HALF_WIDTH);
            int color = 0xFF000000 | (waypoint.hasColor() ? waypoint.color() : DEFAULT_COLOR);
            if (waypoint.style().equals(WaypointIcon.BOWTIE_STYLE)) {
                graphics.fill(x - 4, y, x + 5, y + 2, color);
                graphics.fill(x - 2, y - 2, x + 3, y + 4, color);
            } else {
                graphics.fill(x - 1, y - 3, x + 2, y + 4, color);
                graphics.fill(x - 3, y - 1, x + 4, y + 2, color);
            }
        }
    }

    private static float bearingDegrees(Vec3 player, WaypointDeltaPayload waypoint) {
        if (waypoint.mode() == WaypointDeltaPayload.PositionMode.ANGLE) {
            return waypoint.angleDegrees();
        }
        double dx = waypoint.x() + 0.5 - player.x;
        double dz = waypoint.z() + 0.5 - player.z;
        return (float) Math.toDegrees(Math.atan2(-dx, dz));
    }
}
