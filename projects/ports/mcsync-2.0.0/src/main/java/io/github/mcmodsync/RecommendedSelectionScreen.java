package io.github.mcmodsync;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.io.IOException;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

/** Minecraft-window selection screen shown before optional content is installed. */
public final class RecommendedSelectionScreen extends Screen {
    private static final int PAGE_SIZE = 7;
    private static final AtomicBoolean STARTED = new AtomicBoolean();

    private final Path gameDirectory;
    private final V5RecommendedSelectionStore.PendingSelection pending;
    private final DisplayLanguage language;
    private final Set<String> selected = new LinkedHashSet<>();
    private int page;
    private String error = "";

    private RecommendedSelectionScreen(
            Path gameDirectory,
            V5RecommendedSelectionStore.PendingSelection pending) {
        super(Component.literal(DisplayLanguage.detect(gameDirectory).text(
                "MCSync 可选内容选择", "MCSync Optional Content")));
        this.gameDirectory = gameDirectory;
        this.pending = pending;
        this.language = DisplayLanguage.detect(gameDirectory);
        for (V5RecommendedSelectionStore.PendingMod mod : pending.mods()) {
            if (mod.compatible() && mod.selected()) selected.add(mod.key());
        }
    }

    public static void start(Path gameDirectory) {
        if (!InGameRecommendedSelection.pending(gameDirectory) || !STARTED.compareAndSet(false, true)) return;
        Thread waiter = new Thread(() -> waitForMinecraft(gameDirectory), "MCSync-in-game-selection");
        waiter.setDaemon(true);
        waiter.start();
    }

    private static void waitForMinecraft(Path gameDirectory) {
        for (int attempt = 0; attempt < 1200; attempt++) {
            try {
                Minecraft minecraft = Minecraft.getInstance();
                if (minecraft != null && minecraft.screen != null && minecraft.getOverlay() == null) {
                    V5RecommendedSelectionStore.PendingSelection pending =
                            V5RecommendedSelectionStore.readPending(gameDirectory);
                    if (pending == null) return;
                    minecraft.execute(() -> minecraft.setScreen(new RecommendedSelectionScreen(gameDirectory, pending)));
                    return;
                }
                Thread.sleep(250L);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return;
            } catch (Throwable ignored) {
                try {
                    Thread.sleep(250L);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }

    @Override
    protected void init() {
        clearWidgets();
        int left = width / 2 - 210;
        int top = 58;
        int first = page * PAGE_SIZE;
        int last = Math.min(first + PAGE_SIZE, pending.mods().size());
        for (int index = first; index < last; index++) {
            V5RecommendedSelectionStore.PendingMod mod = pending.mods().get(index);
            Button button = Button.builder(Component.literal(buttonLabel(mod)), clicked -> {
                if (selected.contains(mod.key())) selected.remove(mod.key());
                else selected.add(mod.key());
                rebuild();
            }).bounds(left, top + (index - first) * 30, 420, 24).build();
            button.active = mod.compatible();
            addRenderableWidget(button);
        }

        int bottom = Math.min(height - 52, top + PAGE_SIZE * 30 + 10);
        addRenderableWidget(Button.builder(Component.literal(language.text("全选", "Select all")), button -> {
            pending.mods().stream().filter(V5RecommendedSelectionStore.PendingMod::compatible)
                    .forEach(mod -> selected.add(mod.key()));
            rebuild();
        }).bounds(left, bottom, 78, 20).build());
        addRenderableWidget(Button.builder(Component.literal(language.text("全不选", "Clear")), button -> {
            selected.clear();
            rebuild();
        }).bounds(left + 82, bottom, 78, 20).build());
        if (page > 0) {
            addRenderableWidget(Button.builder(Component.literal(language.text("上一页", "Previous")), button -> {
                page--;
                rebuild();
            }).bounds(left + 164, bottom, 78, 20).build());
        }
        if ((page + 1) * PAGE_SIZE < pending.mods().size()) {
            addRenderableWidget(Button.builder(Component.literal(language.text("下一页", "Next")), button -> {
                page++;
                rebuild();
            }).bounds(left + 246, bottom, 78, 20).build());
        }
        addRenderableWidget(Button.builder(Component.literal(language.text(
                "确认并退出", "Confirm and exit")), button -> confirm())
                .bounds(left + 328, bottom, 92, 20).build());
        int categoryRow = bottom + 24;
        addRenderableWidget(Button.builder(Component.literal(language.text(
                "取消全部资源包", "Clear resource packs")), button -> {
            clearKind("resource-pack");
            rebuild();
        }).bounds(left, categoryRow, 160, 20).build());
        addRenderableWidget(Button.builder(Component.literal(language.text(
                "取消全部光影包", "Clear shader packs")), button -> {
            clearKind("shader-pack");
            rebuild();
        }).bounds(left + 164, categoryRow, 160, 20).build());
    }

    private void clearKind(String kind) {
        pending.mods().stream().filter(mod -> mod.kind().equals(kind))
                .forEach(mod -> selected.remove(mod.key()));
    }

    private void rebuild() {
        init();
    }

    private String buttonLabel(V5RecommendedSelectionStore.PendingMod mod) {
        String mark = !mod.compatible() ? "[×] " : selected.contains(mod.key()) ? "[✓] " : "[ ] ";
        String version = mod.version().isBlank() ? "" : "  " + mod.version();
        return mark + "[" + mod.typeLabel(language) + "] " + mod.displayName() + version;
    }

    private void confirm() {
        try {
            V5RecommendedSelectionStore.confirm(gameDirectory, pending, selected);
            error = "";
            Minecraft.getInstance().stop();
        } catch (IOException failure) {
            error = language.text("保存选择失败：", "Failed to save selection: ") + failure.getMessage();
        }
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        renderBackground(graphics, mouseX, mouseY, partialTick);
        graphics.drawCenteredString(font, title, width / 2, 18, 0xFFFFFF);
        graphics.drawCenteredString(font, Component.literal(language.text(
                "必须内容已锁定；推荐模组、资源包和光影包默认全选。确认后退出，下次启动前同步。",
                "Required content is locked. Optional mods, resource packs and shaders default to selected; confirm, then relaunch.")),
                width / 2, 36, 0xB7C9E2);
        int first = page * PAGE_SIZE;
        int last = Math.min(first + PAGE_SIZE, pending.mods().size());
        for (int index = first; index < last; index++) {
            V5RecommendedSelectionStore.PendingMod mod = pending.mods().get(index);
            String description = mod.description(language);
            if (!description.isBlank()) {
                if (description.length() > 72) description = description.substring(0, 69) + "...";
                graphics.drawString(font, description, width / 2 - 204,
                        83 + (index - first) * 30, 0xA0A0A0);
            }
        }
        if (!error.isBlank()) graphics.drawCenteredString(font, Component.literal(error), width / 2, height - 22, 0xFF6666);
        super.render(graphics, mouseX, mouseY, partialTick);
    }

    @Override
    public boolean shouldCloseOnEsc() {
        return false;
    }

    @Override
    public void onClose() {
        // A choice is required before this catalog can install recommended JARs.
    }
}
