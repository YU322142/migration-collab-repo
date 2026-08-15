package com.github.ysbbbbbb.kaleidoscopetavern.compat.carryon;

import com.github.ysbbbbbb.kaleidoscopetavern.KaleidoscopeTavern;
import net.minecraftforge.fml.InterModComms;
import net.minecraftforge.registries.ForgeRegistries;

public class BlackList {
    private static final String CARRY_ON_ID = "carryon";

    public static void addBlackList() {
        ForgeRegistries.BLOCKS.getKeys().stream().filter(id -> id.getNamespace().equals(KaleidoscopeTavern.MOD_ID))
                .forEach(id -> InterModComms.sendTo(CARRY_ON_ID, "blacklistBlock", id::toString));
    }
}
