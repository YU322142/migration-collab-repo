package net.minecraft.client.gui.components;

import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.client.gui.narration.NarratableEntry;
import net.minecraft.network.chat.Component;

public class Button implements GuiEventListener, Renderable, NarratableEntry {
    public boolean active = true;

    public static Builder builder(Component message, OnPress onPress) { return null; }

    @FunctionalInterface
    public interface OnPress {
        void onPress(Button button);
    }

    public static class Builder {
        public Builder bounds(int x, int y, int width, int height) { return this; }
        public Button build() { return null; }
    }
}
