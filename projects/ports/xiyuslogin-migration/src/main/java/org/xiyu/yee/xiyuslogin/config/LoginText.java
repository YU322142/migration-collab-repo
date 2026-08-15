package org.xiyu.yee.xiyuslogin.config;

import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import net.neoforged.neoforge.common.ModConfigSpec;

public final class LoginText {
    private LoginText() {
    }

    public static MutableComponent component(ModConfigSpec.ConfigValue<String> value, Object... replacements) {
        return Component.literal(text(value, replacements));
    }

    public static String text(ModConfigSpec.ConfigValue<String> value, Object... replacements) {
        String message = value.get();
        for (int i = 0; i + 1 < replacements.length; i += 2) {
            String key = String.valueOf(replacements[i]);
            String replacement = String.valueOf(replacements[i + 1]);
            message = message.replace("{" + key + "}", replacement);
        }
        return message.replace("\\n", "\n").replace('&', '§');
    }
}
