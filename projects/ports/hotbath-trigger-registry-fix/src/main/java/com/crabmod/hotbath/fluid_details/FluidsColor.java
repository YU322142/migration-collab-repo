package com.crabmod.hotbath.fluid_details;

import org.joml.Vector3f;

public final class FluidsColor {
    // return 16 bits color
    public static int setFluidColor(int red, int green, int blue) {
        return 0xff000000 | (red << 16) | (green << 8) | blue;
    }

    public static final int HERBAL_BATH_COLOR = setFluidColor(36, 202, 173);
    public static final int HOT_WATER_COLOR = setFluidColor(69, 225, 233);
    public static final int HONEY_BATH_COLOR = setFluidColor(254, 209, 122);

    public static final int MILK_BATH_COLOR = setFluidColor(248, 248, 248);
    public static final int PEONY_BATH_COLOR = setFluidColor(253, 104, 159);
    public static final int ROSE_BATH_COLOR = setFluidColor(254, 119, 142);

    public static final Vector3f DEFAULT_FOG_COLOR = new Vector3f(0.0f, 0.0f, 0.0f);
}
