package net.minecraft.client.gui.screens;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Renderable;
import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.client.gui.narration.NarratableEntry;
import net.minecraft.network.chat.Component;

public abstract class Screen implements Renderable {
    protected final Component title;
    protected Minecraft minecraft;
    protected Font font;
    public int width;
    public int height;

    protected Screen(Component title) { this.title = title; }
    protected void init() { }
    protected void clearWidgets() { }
    protected <T extends GuiEventListener & Renderable & NarratableEntry> T addRenderableWidget(T widget) { return widget; }
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) { }
    public void renderBackground(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) { }
    public boolean shouldCloseOnEsc() { return true; }
    public void onClose() { }
}
