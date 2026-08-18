package io.github.mcmodsync;

import javax.swing.BorderFactory;
import javax.swing.BoxLayout;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JDialog;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JProgressBar;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.SwingUtilities;
import javax.swing.Timer;
import javax.swing.WindowConstants;
import java.awt.BorderLayout;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.FlowLayout;
import java.awt.GraphicsEnvironment;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.io.IOException;
import java.nio.file.Path;
import java.lang.reflect.InvocationTargetException;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

final class UserNotifier implements SyncObserver {
    private static JDialog activeDownloadDialog;
    private static JLabel activePhaseLabel;
    private static JLabel activeFileDetailLabel;
    private static JLabel activeTotalDetailLabel;
    private static JProgressBar activeFileProgressBar;
    private static JProgressBar activeTotalProgressBar;
    private static JTextArea activePlanArea;
    private static JButton activeCloseButton;
    private static volatile Boolean dialogsAvailableCache;
    private final boolean portableMode;
    private final boolean mobileRuntime;
    private final DisplayLanguage language;
    private final SyncStatusReporter statusReporter;
    private final AtomicReference<DownloadProgress> pendingProgress = new AtomicReference<>();
    private final AtomicBoolean progressUpdateScheduled = new AtomicBoolean();
    private volatile boolean progressUiStarted;
    private volatile boolean helperExitScheduled;

    UserNotifier() {
        this(false, null);
    }

    UserNotifier(boolean portableMode) {
        this(portableMode, null);
    }

    UserNotifier(boolean portableMode, Path gameDirectory) {
        this.portableMode = portableMode;
        Path directory = gameDirectory;
        if (directory == null) {
            String configured = System.getProperty("modsync.gameDir");
            if (configured != null && !configured.isBlank()) {
                directory = Path.of(configured.strip());
            }
        }
        RuntimeEnvironment environment = RuntimeEnvironment.detect();
        this.mobileRuntime = environment.mobile();
        this.language = DisplayLanguage.detect(directory);
        boolean dialogs = dialogsAvailable(environment);
        // Desktop (dialogs available): keep original Swing-only UX.
        // Mobile/headless: log + .modsync status files.
        this.statusReporter = dialogs ? null : new SyncStatusReporter(directory, language);
        if (this.statusReporter != null) {
            this.statusReporter.setEnvironment(environment);
            this.statusReporter.setMode(
                    mobileRuntime
                            ? (portableMode ? "portable-mobile" : "agent-mobile")
                            : (portableMode ? "portable-headless" : "agent-headless"));
            System.out.println("[MCSync] " + environment.summaryLine());
        }
    }

    private void reportPhase(String phase, String detail) {
        MinecraftWindowStatus.update(detail == null || detail.isBlank() ? phase : phase + " — " + detail);
        if (statusReporter != null) {
            statusReporter.phase(phase, detail);
        }
    }

    private void reportPlan(String plan) {
        if (statusReporter != null) {
            statusReporter.plan(plan);
        }
    }

    private void reportProgress(DownloadProgress progress) {
        MinecraftWindowStatus.update(progress.fileName() + "  " + (progress.totalPermille() / 10.0) + "%");
        if (statusReporter != null) {
            statusReporter.progress(progress);
        }
    }

    private void reportCompleted(int downloaded, int quarantined, int unchanged) {
        MinecraftWindowStatus.update(text("更新已就绪，请重启", "Update ready; restart required"));
        if (statusReporter != null) {
            statusReporter.completed(downloaded, quarantined, unchanged, portableMode);
        }
    }

    private String text(String chinese, String english) {
        return language.text(chinese, english);
    }

    static String restartRequiredTitle(DisplayLanguage language) {
        return language.text("MCSync：需要重新启动", "MCSync: Restart Required");
    }

    static String restartRequiredMessage(DisplayLanguage language) {
        return language.text(
                "下载和校验已完成，需要重新启动 Minecraft",
                "Download and verification are complete; restart Minecraft");
    }

    static String restartRequiredButton(DisplayLanguage language) {
        return language.text("确定，返回启动器", "OK, Return to Launcher");
    }

    static boolean shouldShowRestartRequired(boolean portableMode, boolean mobileRuntime) {
        return portableMode && !mobileRuntime;
    }

    private String localizePhase(String message) {
        if (language.chinese()) {
            return message;
        }
        return message
                .replace("游戏目录", "Game directory")
                .replace("正在读取云端清单……", "Reading the cloud catalog…")
                .replace("正在获取下载文件大小，准备总进度……", "Reading download sizes and preparing overall progress…")
                .replace("准备下载 ", "Preparing to download ")
                .replace(" 个 Mod……", " mod(s)…")
                .replace("正在使用 ", "Using ")
                .replace(" 个线程并行下载并校验 Mod……", " threads to download and verify mods in parallel…")
                .replace("并行下载未成功，正在自动回退单线程重新下载……",
                        "Parallel download failed; retrying automatically with one thread…")
                .replace("下载和校验完成，正在安全备份并替换 Mod……",
                        "Download and verification complete; backing up and replacing mods safely…")
                .replace("正在生成并校验本地 Mod 清单……",
                        "Generating and verifying the local mod catalog…")
                .replace("正在校验 MD5/SHA256：", "Verifying MD5/SHA256: ")
                .replace("正在读取云端资源包 MD5 清单……", "Reading the cloud resource-pack MD5 catalog…")
                .replace("正在获取资源包大小，准备总进度……",
                        "Reading resource-pack sizes and preparing overall progress…")
                .replace(" 个线程并行下载并校验资源包……",
                        " threads to download and verify resource packs in parallel…")
                .replace("资源包并行下载未成功，正在自动回退单线程重新下载……",
                        "Parallel resource-pack download failed; retrying with one thread…")
                .replace("资源包下载和 MD5 校验完成，正在安全备份并替换……",
                        "Resource-pack download and MD5 verification complete; backing up and replacing safely…")
                .replace("正在校验资源包 MD5：", "Verifying resource-pack MD5: ")
                .replace("正在读取云端服务器列表 MD5 清单……", "Reading the cloud server-list MD5 catalog…")
                .replace("服务器列表下载完成，正在解析 NBT 并合并玩家条目……",
                        "Server-list download complete; parsing NBT and merging player entries…")
                .replace("服务器列表合并完成，正在保存管理台账并安全更新 servers.dat……",
                        "Server-list merge complete; saving the ownership ledger and safely updating servers.dat…")
                .replace("游戏进程已退出，正在读取云端清单……",
                        "The game process exited; reading the cloud catalog…");
    }

    void showWaitingForGameExit(long parentPid) throws IOException {
        progressUiStarted = true;
        String plan = text(
                "MCSync 已检测到 Mod、资源包或服务器列表变化。\n\n"
                        + "新版通常会让 Minecraft 自动正常退出。\n"
                        + "如果加载器、Minecraft 或启动器仍显示错误/退出窗口，请将那个窗口关闭；"
                        + "只要游戏 Java 进程结束，下载就会自动继续。\n\n"
                        + "请不要再次启动游戏，也不要手动改动 mods 目录。",
                "MCSync detected changes to mods, resource packs, or the server list.\n\n"
                        + "Minecraft should exit normally. Close any remaining loader, Minecraft, or launcher window; "
                        + "the download starts after the game Java process exits.\n\n"
                        + "Do not launch the game again or modify the mods directory.");
        if (!dialogsAvailable()) {
            reportPlan(plan + text(
                    "\n无独立弹窗环境可查看 .modsync/ui-status.txt、progress.log 与 helper.log。",
                    "\nWithout a GUI, see .modsync/ui-status.txt, progress.log, and helper.log."));
            reportPhase(text("正在等待 Minecraft/加载器进程退出……",
                            "Waiting for the Minecraft/loader process to exit…"),
                    text("进程 PID ", "Process PID ") + parentPid
                            + text("；退出后将自动开始下载", "; download starts after exit"));
            return;
        }
        try {
            runOnUiThread(() -> {
                closeActiveDownloadDialog();
                ensureProgressDialog();
                activeDownloadDialog.setTitle(text("MCSync 正在准备更新", "MCSync Preparing Update"));
                activePhaseLabel.setText(text("正在等待 Minecraft/加载器进程退出……",
                        "Waiting for the Minecraft/loader process to exit…"));
                activeFileDetailLabel.setText(text("进程 PID ", "Process PID ") + parentPid
                        + text("；退出后将自动开始下载", "; download starts after exit"));
                setWaitingProgress(activeFileProgressBar, text("等待游戏退出", "Waiting for game exit"));
                activeTotalDetailLabel.setText(text("总进度：等待开始", "Overall: waiting to start"));
                setWaitingProgress(activeTotalProgressBar, text("等待游戏退出", "Waiting for game exit"));
                activePlanArea.setText(plan);
            });
        } catch (IOException exception) {
            markDialogsUnavailable(exception.getMessage());
        }
    }

    @Override
    public RemovalDecision decideServerRemoved(List<String> serverRemoved) {
        if (serverRemoved.isEmpty()) {
            return RemovalDecision.KEEP;
        }
        if (!dialogsAvailable()) {
            // Desktop headless keeps extras so operators are not surprised.
            // Mobile must clean leftovers (e.g. kuayue / c2me natives) or the next
            // Loader resolution can hard-fail before the next startup callback runs.
            if (mobileRuntime) {
                reportPhase(text(
                                "手机端：自动移出并备份服务器已移除/不在清单中的 Mod",
                                "Mobile: moving server-removed or unlisted mods to backup"),
                        String.join(", ", serverRemoved));
                System.out.println("[MCSync] " + text(
                        "手机端自动隔离服务器已移除 Mod: ",
                        "Mobile: quarantined mods removed by the server: ") + serverRemoved);
                return RemovalDecision.BACKUP;
            }
            reportPhase(text(
                            "无弹窗环境：保留服务器已移除的 Mod 为客户端文件",
                            "Headless environment: keeping server-removed mods as client files"),
                    String.join(", ", serverRemoved));
            System.out.println("[MCSync] " + text(
                    "无弹窗环境，自动保留服务器已移除 Mod: ",
                    "Headless environment: retained server-removed mods: ") + serverRemoved);
            return RemovalDecision.KEEP;
        }
        AtomicReference<RemovalDecision> decision = new AtomicReference<>(RemovalDecision.KEEP);
        try {
            runOnUiThread(() -> {
                JTextArea content = new JTextArea(buildRemovedText(serverRemoved));
                content.setEditable(false);
                content.setCaretPosition(0);
                content.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 13));
                content.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
                JScrollPane scroll = new JScrollPane(content);
                scroll.setPreferredSize(new Dimension(650, 330));
                Object[] options = {
                        text("移出 mods 并备份（推荐）", "Move out of mods and back up (recommended)"),
                        text("保留为客户端 Mod", "Keep as a client mod")
                };
                prepareForInteractiveDecision(
                        text("等待确认服务器已移除 Mod", "Waiting for removed-mod decision"),
                        text(
                                "请在置顶的选择窗口中决定如何处理服务器已移除的 Mod",
                                "Choose how to handle mods removed by the server in the topmost window"));
                int choice = showTopmostOptionDialog(
                        scroll,
                        text("MCSync：服务器已移除 Mod", "MCSync: Mods Removed by Server"),
                        options,
                        options[0]);
                decision.set(choice == 0 ? RemovalDecision.BACKUP : RemovalDecision.KEEP);
            });
        } catch (IOException exception) {
            System.err.println("[MCSync] " + text(
                    "无法显示服务器移除选择窗口，将安全保留文件: ",
                    "Cannot show the removed-mod dialog; files will be retained safely: ") + exception.getMessage());
        }
        return decision.get();
    }

    @Override
    public UnknownModDecision decideUnknownClientMod(String fileName) throws IOException {
        if (!dialogsAvailable()) {
            if (mobileRuntime) {
                reportPhase(text(
                        "手机端：自动移出并备份未在云端清单中的本地 Mod",
                        "Mobile: moving local mods absent from the cloud catalog to backup"), fileName);
                System.out.println("[MCSync] " + text(
                        "手机端自动隔离未确认客户端 Mod: ",
                        "Mobile: quarantined unconfirmed client mod: ") + fileName);
                return UnknownModDecision.BACKUP;
            }
            // Desktop headless: keep as client mod so operators are not blocked.
            reportPhase(text(
                    "无弹窗环境：保留未在云端清单中的本地 Mod",
                    "Headless environment: keeping local mods absent from the cloud catalog"), fileName);
            System.out.println("[MCSync] " + text(
                    "无弹窗环境，自动保留未确认客户端 Mod: ",
                    "Headless environment: retained unconfirmed client mod: ") + fileName);
            return UnknownModDecision.KEEP_CLIENT;
        }
        AtomicReference<UnknownModDecision> decision = new AtomicReference<>();
        try {
            runOnUiThread(() -> {
                Object[] options = {
                        text("是，作为纯客户端 Mod 保留", "Yes, keep as a client-only mod"),
                        text("否，移出并备份", "No, move out and back up")
                };
                prepareForInteractiveDecision(
                        text("等待确认纯客户端 Mod", "Waiting for client-only mod decision"),
                        text("请在置顶的选择窗口中确认：", "Confirm in the topmost window: ") + fileName);
                int choice = showTopmostOptionDialog(
                        text(
                                "本地发现一个云端服务器清单中没有的 Mod：\n\n"
                                        + fileName + "\n\n"
                                        + "它是否是仅在客户端运行、可以安全保留的纯客户端 Mod？\n"
                                        + "如果不确定，请选择“否”；文件只会移入 .modsync/backups，不会永久删除。",
                                "A local mod is not listed in the cloud catalog:\n\n"
                                        + fileName + "\n\n"
                                        + "Is it a client-only mod that is safe to keep?\n"
                                        + "If unsure, choose No. The file is moved to .modsync/backups and is not deleted."),
                        text("MCSync：确认纯客户端 Mod", "MCSync: Confirm Client-only Mod"),
                        options,
                        options[0]);
                if (choice == 0) {
                    decision.set(UnknownModDecision.KEEP_CLIENT);
                } else if (choice == 1) {
                    decision.set(UnknownModDecision.BACKUP);
                }
            });
        } catch (IOException exception) {
            markDialogsUnavailable(exception.getMessage());
            reportPhase(text(
                    "图形窗口失败，自动保留未确认客户端 Mod",
                    "The dialog failed; retaining the unconfirmed client mod"), fileName);
            return UnknownModDecision.KEEP_CLIENT;
        }
        if (decision.get() == null) {
            throw new IOException("尚未确认该 Mod 是否为纯客户端 Mod，已阻止启动: " + fileName);
        }
        return decision.get();
    }

    @Override
    public Set<String> chooseRecommendedMods(RecommendedSelectionRequest request) throws IOException {
        if (mobileRuntime) {
            return request.initiallySelected();
        }
        if (!dialogsAvailable()) {
            String detail = language.text(
                    "当前桌面环境无法显示选择窗口，将采用所有兼容推荐模组。清单版本: ",
                    "The recommendation window is unavailable; all compatible recommended mods will be used. Catalog: ")
                    + request.catalogVersion();
            reportPhase(language.text("推荐模组使用默认选择", "Using default recommended mods"), detail);
            System.out.println("[MCSync] " + detail);
            return request.initiallySelected();
        }

        AtomicReference<Set<String>> selected = new AtomicReference<>();
        runOnUiThread(() -> selected.set(showRecommendedSelectionDialog(request, language)));
        return selected.get() == null ? request.initiallySelected() : selected.get();
    }

    private static Set<String> showRecommendedSelectionDialog(
            RecommendedSelectionRequest request,
            DisplayLanguage language) {
        Map<ManifestEntry, JCheckBox> checkboxes = new LinkedHashMap<>();
        JPanel list = new JPanel();
        list.setLayout(new BoxLayout(list, BoxLayout.Y_AXIS));
        list.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));

        for (ManifestEntry entry : request.recommendedMods()) {
            boolean compatible = entry.compatibleWith(request.platform());
            JCheckBox checkbox = new JCheckBox();
            checkbox.setSelected(compatible && request.initiallySelected().contains(entry.selectionKey()));
            checkbox.setEnabled(compatible);
            String version = entry.version().isBlank()
                    ? language.text("未知版本", "Unknown version")
                    : entry.version();
            String localizedDescription = entry.localizedDescription(language);
            String description = localizedDescription.isBlank()
                    ? language.text("无描述", "No description")
                    : escapeHtml(localizedDescription);
            String compatibility = compatible
                    ? language.text("兼容当前平台", "Compatible with this platform")
                    : language.text("不兼容当前平台，禁止选择", "Incompatible with this platform; selection disabled");
            checkbox.setText("<html><b>" + escapeHtml(entry.displayName()) + "</b>  "
                    + escapeHtml(version) + "<br>"
                    + "<span style='color:#555'>" + description + "</span><br>"
                    + "<span style='color:" + (compatible ? "#267a35" : "#b42318") + "'>"
                    + compatibility + "</span>  <span style='color:#777'>" + escapeHtml(entry.fileName())
                    + "</span><br><br></html>");
            list.add(checkbox);
            checkboxes.put(entry, checkbox);
        }

        JLabel heading = new JLabel("<html><b>"
                + language.text("选择本客户端要安装的推荐模组", "Choose recommended mods for this client")
                + "</b><br>"
                + language.text("平台：", "Platform: ") + request.platform().displayName(language)
                + language.text("　推荐清单：", "　Catalog: ") + escapeHtml(request.catalogVersion())
                + (request.previousCatalogVersion().isBlank()
                        ? ""
                        : language.text("（原版本 ", " (previous ")
                                + escapeHtml(request.previousCatalogVersion())
                                + language.text("）", ")"))
                + "<br>" + language.text(
                        "关闭窗口也会按照当前勾选状态继续同步。",
                        "Closing this window continues with the current selections.")
                + "</html>");
        heading.setBorder(BorderFactory.createEmptyBorder(12, 12, 8, 12));

        JButton selectCompatible = new JButton(language.text(
                "选择全部兼容模组", "Select all compatible"));
        JButton clear = new JButton(language.text(
                "一键取消所有推荐模组", "Clear all recommended"));
        JButton continueButton = new JButton(language.text(
                "按当前选择继续", "Continue with selection"));
        JPanel actions = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        actions.add(selectCompatible);
        actions.add(clear);
        actions.add(continueButton);

        JPanel content = new JPanel(new BorderLayout());
        content.add(heading, BorderLayout.NORTH);
        JScrollPane scroll = new JScrollPane(list);
        scroll.setPreferredSize(new Dimension(760, 480));
        content.add(scroll, BorderLayout.CENTER);
        content.add(actions, BorderLayout.SOUTH);

        JDialog owner = activeDownloadDialog != null && activeDownloadDialog.isDisplayable()
                ? activeDownloadDialog
                : null;
        JDialog dialog = new JDialog(owner, language.text(
                "MCSync 推荐模组选择", "MCSync Recommended Mods"), true);
        dialog.setDefaultCloseOperation(WindowConstants.DO_NOTHING_ON_CLOSE);
        dialog.setAlwaysOnTop(true);
        dialog.setAutoRequestFocus(true);
        dialog.add(content);
        dialog.pack();
        dialog.setLocationRelativeTo(null);

        AtomicReference<Set<String>> result = new AtomicReference<>();
        Runnable finish = () -> {
            Set<String> current = new LinkedHashSet<>();
            for (Map.Entry<ManifestEntry, JCheckBox> item : checkboxes.entrySet()) {
                if (item.getValue().isEnabled() && item.getValue().isSelected()) {
                    current.add(item.getKey().selectionKey());
                }
            }
            result.set(Set.copyOf(current));
            dialog.dispose();
        };
        selectCompatible.addActionListener(event -> checkboxes.values().forEach(box -> {
            if (box.isEnabled()) {
                box.setSelected(true);
            }
        }));
        clear.addActionListener(event -> checkboxes.values().forEach(box -> box.setSelected(false)));
        continueButton.addActionListener(event -> finish.run());
        dialog.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosing(WindowEvent event) {
                finish.run();
            }
        });
        dialog.setVisible(true);
        return result.get() == null ? request.initiallySelected() : result.get();
    }

    private static String escapeHtml(String value) {
        return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;");
    }

    @Override
    public void beforeDownload(
            List<String> downloads,
            List<String> replacedOldVersions,
            List<String> rejectedUnknownMods,
            List<String> quarantinedServerRemoved,
            List<String> retainedServerRemoved,
            List<String> retainedClientMods) throws IOException {
        progressUiStarted = true;
        String plan = buildPlanText(
                downloads,
                replacedOldVersions,
                rejectedUnknownMods,
                quarantinedServerRemoved,
                retainedServerRemoved,
                retainedClientMods);
        if (!dialogsAvailable()) {
            reportPlan(plan);
            reportPhase(text("已检测到 Mod 变化，正在准备下载……",
                            "Mod changes detected; preparing downloads…"),
                    text("共需下载或替换 ", "Files to download or replace: ") + downloads.size()
                            + text(" 个文件", ""));
            return;
        }
        try {
            runOnUiThread(() -> {
                ensureProgressDialog();
                activeDownloadDialog.setTitle(text("MCSync 正在自动同步", "MCSync Automatic Sync"));
                activePhaseLabel.setText(text(
                        "已检测到 Mod 变化，正在准备下载……",
                        "Mod changes detected; preparing downloads…"));
                activeFileDetailLabel.setText(text("当前文件：准备中", "Current file: preparing"));
                setWaitingProgress(activeFileProgressBar, text("准备下载", "Preparing download"));
                if (activeTotalProgressBar.isIndeterminate()) {
                    activeTotalDetailLabel.setText(text(
                            "总进度：共需下载或替换 ", "Overall files to download or replace: ")
                            + downloads.size());
                    setWaitingProgress(activeTotalProgressBar, text("准备下载", "Preparing download"));
                } else {
                    activeTotalDetailLabel.setText(text(
                            "总进度：正在准备下一个 BakaXL 同步目标",
                            "Overall: preparing the next BakaXL sync target"));
                }
                activePlanArea.setText(plan);
                activePlanArea.setCaretPosition(0);
            });
        } catch (IOException exception) {
            markDialogsUnavailable(exception.getMessage());
        }
    }

    @Override
    public void beforeResourcePackDownload(
            List<String> downloads,
            List<String> backedUpRemoved) throws IOException {
        progressUiStarted = true;
        String plan = buildResourcePackPlanText(downloads, backedUpRemoved);
        if (!dialogsAvailable()) {
            reportPlan(plan);
            reportPhase(text("已检测到资源包变化，正在准备下载……",
                            "Resource-pack changes detected; preparing downloads…"),
                    text("共需下载或替换 ", "Resource packs to download or replace: ") + downloads.size()
                            + text(" 个资源包", ""));
            return;
        }
        try {
            runOnUiThread(() -> {
                ensureProgressDialog();
                activeDownloadDialog.setTitle(text("MCSync 正在同步资源包", "MCSync Resource-pack Sync"));
                activePhaseLabel.setText(text(
                        "已检测到资源包变化，正在准备下载……",
                        "Resource-pack changes detected; preparing downloads…"));
                activeFileDetailLabel.setText(text("当前资源包：准备中", "Current resource pack: preparing"));
                setWaitingProgress(activeFileProgressBar, text("准备下载", "Preparing download"));
                if (activeTotalProgressBar.isIndeterminate()) {
                    activeTotalDetailLabel.setText(text(
                            "总进度：共需下载或替换 ", "Overall resource packs to download or replace: ")
                            + downloads.size());
                    setWaitingProgress(activeTotalProgressBar, text("准备下载", "Preparing download"));
                } else {
                    activeTotalDetailLabel.setText(text(
                            "总进度：正在准备资源包同步阶段",
                            "Overall: preparing resource-pack sync"));
                }
                activePlanArea.setText(plan);
                activePlanArea.setCaretPosition(0);
            });
        } catch (IOException exception) {
            markDialogsUnavailable(exception.getMessage());
        }
    }

    @Override
    public void beforeServerListDownload(String fileName) throws IOException {
        progressUiStarted = true;
        String plan = text(
                "检测到云端服务器列表 MD5 已变化。\n\n"
                        + "将自动下载并校验：" + fileName + "\n\n"
                        + "只有 MCSync 所有权台账确认的云端条目才会更新或移除。\n"
                        + "玩家自行添加、同地址重复或无法确认所有权的条目都会原样保留。\n"
                        + "现有条目保持原位置和相对顺序；新的云端服务器只追加到列表末尾。\n"
                        + "现有 servers.dat 会先保存到 .modsync/backups，再安全替换。\n\n"
                        + "下载内容只有通过 MD5 复核后才会提交，无需确认。",
                "The cloud server-list MD5 changed.\n\n"
                        + "Download and verify automatically: " + fileName + "\n\n"
                        + "Only cloud entries verified by the MCSync ownership ledger may be updated or removed.\n"
                        + "Player-added, duplicate-address, and ownership-ambiguous entries are retained unchanged.\n"
                        + "Existing entries keep their positions and relative order; new cloud servers are appended.\n"
                        + "The existing servers.dat is backed up to .modsync/backups before replacement.\n\n"
                        + "The download is committed only after MD5 verification.");
        if (!dialogsAvailable()) {
            reportPlan(plan);
            reportPhase(text(
                            "已检测到服务器列表变化，正在自动下载……",
                            "Server-list changes detected; downloading automatically…"),
                    text("当前文件：", "Current file: ") + fileName);
            return;
        }
        try {
            runOnUiThread(() -> {
                ensureProgressDialog();
                activeDownloadDialog.setTitle(text("MCSync 正在同步服务器列表", "MCSync Server-list Sync"));
                activePhaseLabel.setText(text(
                        "已检测到服务器列表变化，正在自动下载……",
                        "Server-list changes detected; downloading automatically…"));
                activeFileDetailLabel.setText(text("当前文件：", "Current file: ") + fileName);
                setWaitingProgress(activeFileProgressBar, text("准备下载", "Preparing download"));
                if (activeTotalProgressBar.isIndeterminate()) {
                    activeTotalDetailLabel.setText(text(
                            "总进度：正在准备服务器列表同步阶段",
                            "Overall: preparing server-list sync"));
                    setWaitingProgress(activeTotalProgressBar, text("准备下载", "Preparing download"));
                } else {
                    activeTotalDetailLabel.setText(text(
                            "总进度：正在准备服务器列表同步阶段",
                            "Overall: preparing server-list sync"));
                }
                activePlanArea.setText(plan);
                activePlanArea.setCaretPosition(0);
            });
        } catch (IOException exception) {
            markDialogsUnavailable(exception.getMessage());
        }
    }

    @Override
    public void phaseChanged(String message) {
        if (!progressUiStarted) {
            progressUiStarted = true;
        }
        String localizedMessage = localizePhase(message);
        if (!dialogsAvailable()) {
            reportPhase(localizedMessage, text(
                    "正在安全处理，请勿修改 mods 目录",
                    "Processing safely; do not modify the mods directory"));
            return;
        }
        DownloadProgress latestProgress = pendingProgress.getAndSet(null);
        try {
            runOnUiThread(() -> {
                ensureProgressDialog();
                if (latestProgress != null) {
                    applyDownloadProgress(latestProgress);
                }
                activePhaseLabel.setText(localizedMessage);
                activeFileDetailLabel.setText(text(
                        "正在安全处理，请勿关闭此窗口或修改 mods 目录",
                        "Processing safely; do not close this window or modify the mods directory"));
                setWaitingProgress(activeFileProgressBar, text("处理中", "Processing"));
            });
        } catch (IOException exception) {
            markDialogsUnavailable(exception.getMessage());
            System.err.println("[MCSync] " + text(
                    "无法更新进度窗口: ", "Cannot update the progress window: ") + exception.getMessage());
        }
    }

    @Override
    public void downloadProgress(DownloadProgress progress) {
        progressUiStarted = true;
        if (!dialogsAvailable()) {
            reportProgress(progress);
            return;
        }
        pendingProgress.set(progress);
        scheduleProgressFlush();
    }

    @Override
    public void afterUpdate(int downloaded, int quarantined, int unchanged) {
        if (mobileRuntime || !dialogsAvailable()) {
            reportCompleted(downloaded, quarantined, unchanged);
            if (portableMode && Boolean.getBoolean("modsync.helperProcess")) {
                // Keep helper process short-lived on mobile/headless; logs already contain the summary.
                helperExitScheduled = false;
            }
            return;
        }
        try {
            runOnUiThread(() -> {
                if (shouldShowRestartRequired(portableMode, mobileRuntime)) {
                    ensureProgressDialog();
                    activeDownloadDialog.setTitle(restartRequiredTitle(language));
                    activePhaseLabel.setText(restartRequiredMessage(language));
                    activeFileDetailLabel.setText(text("当前文件：全部完成", "Current file: complete"));
                    setCompletedProgress(activeFileProgressBar);
                    activeTotalDetailLabel.setText(text(
                            "总进度：100%，等待你确认后返回启动器",
                            "Overall: 100%; confirm to return to the launcher"));
                    setCompletedProgress(activeTotalProgressBar);
                    activePlanArea.setText(text(
                            "下载/替换：" + downloaded + "\n"
                                    + "移入备份：" + quarantined + "\n"
                                    + "无需更改：" + unchanged + "\n\n"
                                    + "Mod 已通过 MD5/SHA256，资源包和服务器列表已通过各自清单校验并安全提交。\n"
                                    + "必须重新启动 Minecraft 才能加载更新后的内容。\n"
                                    + "点击“确定，返回启动器”，然后在启动器中再次点击启动。",
                            "Downloaded/replaced: " + downloaded + "\n"
                                    + "Moved to backup: " + quarantined + "\n"
                                    + "Unchanged: " + unchanged + "\n\n"
                                    + "Mods passed MD5/SHA256; resource packs and the server list passed their catalogs.\n"
                                    + "Minecraft must be restarted to load the updated content.\n"
                                    + "Click ‘OK, Return to Launcher’, then launch the instance again."));
                    activePlanArea.setCaretPosition(0);
                    activeCloseButton.setText(restartRequiredButton(language));
                    activeCloseButton.setVisible(true);
                    activeDownloadDialog.pack();
                    activeDownloadDialog.setLocationRelativeTo(null);
                    activeDownloadDialog.toFront();
                    activeDownloadDialog.requestFocus();
                    helperExitScheduled = true;
                    return;
                }
                closeActiveDownloadDialog();
                JDialog dialog = new JDialog(
                        (java.awt.Frame) null,
                        text("MCSync 更新完成", "MCSync Update Complete"),
                        false);
                dialog.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE);
                JLabel content = new JLabel("<html><div style='padding:12px'>"
                        + text("同步完成。", "Sync complete.") + "<br><br>"
                        + text("下载/替换：", "Downloaded/replaced: ") + downloaded + "<br>"
                        + text("移入备份：", "Moved to backup: ") + quarantined + "<br>"
                        + text("无需更改：", "Unchanged: ") + unchanged + "<br><br>"
                        + text("游戏将继续自动启动。", "The game will continue launching automatically.")
                        + "</div></html>");
                dialog.add(content, BorderLayout.CENTER);
                dialog.pack();
                dialog.setLocationRelativeTo(null);
                dialog.setVisible(true);
                Timer timer = new Timer(5_000, event -> dialog.dispose());
                timer.setRepeats(false);
                timer.start();
            });
        } catch (IOException exception) {
            markDialogsUnavailable(exception.getMessage());
            System.err.println("[MCSync] " + text(
                    "无法显示完成提示: ", "Cannot show the completion message: ") + exception.getMessage());
        }
    }

    static void showFatalError(Throwable failure) {
        String message = mostUsefulMessage(failure);
        DisplayLanguage language = DisplayLanguage.detect(resolveOptionalGameDirectory());
        System.err.println("[MCSync] "
                + language.text("游戏启动已阻止: ", "Game startup blocked: ") + message);
        if (!dialogsAvailable()) {
            new SyncStatusReporter(resolveOptionalGameDirectory(), language).failed(message);
            return;
        }
        try {
            runOnUiThread(() -> {
                closeActiveDownloadDialog();
                JTextArea content = new JTextArea(
                        language.text(
                                "为防止加载不完整或损坏的同步内容，游戏启动已被阻止。\n\n"
                                        + "错误：" + message + "\n\n"
                                        + "请关闭其他 Minecraft/Java 进程，并检查网络、mods.txt、目录写入权限和只读属性后重试。\n"
                                        + "完整错误信息仍保留在启动器/Java 启动日志中。",
                                "Game startup was blocked to prevent loading incomplete or damaged synchronized content.\n\n"
                                        + "Error: " + message + "\n\n"
                                        + "Close other Minecraft/Java processes, then check the network, mods.txt, write permissions, "
                                        + "and read-only attributes before retrying.\n"
                                        + "Full error details remain in the launcher/Java log."));
                content.setEditable(false);
                content.setLineWrap(true);
                content.setWrapStyleWord(true);
                content.setCaretPosition(0);
                content.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
                JScrollPane scroll = new JScrollPane(content);
                scroll.setPreferredSize(new Dimension(620, 260));
                JOptionPane.showMessageDialog(
                        null,
                        scroll,
                        language.text(
                                "MCSync 错误：游戏启动已阻止",
                                "MCSync Error: Game Startup Blocked"),
                        JOptionPane.ERROR_MESSAGE);
            });
        } catch (IOException exception) {
            markDialogsUnavailable(exception.getMessage());
            System.err.println("[MCSync] " + language.text(
                    "无法显示错误窗口: ", "Cannot show the error window: ") + exception.getMessage());
        }
    }

    static void showInstanceBusy() {
        DisplayLanguage language = DisplayLanguage.detect(resolveOptionalGameDirectory());
        System.err.println("[MCSync] " + language.text(
                "本次启动已取消：请等待同步完成，或关闭该实例的旧 Minecraft/Java 进程后重试。",
                "Launch cancelled: wait for sync to finish, or close the old Minecraft/Java process and retry."));
        if (!dialogsAvailable()) {
            return;
        }
        try {
            runOnUiThread(() -> JOptionPane.showMessageDialog(
                    null,
                    language.text(
                            "该客户端正在由 MCSync 下载或替换文件，\n"
                                    + "或者同一游戏实例已有一个 Minecraft/Java 进程正在运行。\n\n"
                                    + "本次启动已安全取消，不是 Mod 崩溃。\n"
                                    + "请等待更新窗口显示完成并自动关闭；若没有更新窗口，\n"
                                    + "请先关闭旧的 Minecraft/Java，然后再点击启动。",
                            "MCSync is downloading or replacing files, or another Minecraft/Java process is running "
                                    + "for this instance.\n\n"
                                    + "This launch was cancelled safely; it is not a mod crash.\n"
                                    + "Wait for the update window to finish and close. If there is no update window, "
                                    + "close the old Minecraft/Java process before launching again."),
                    language.text("MCSync：客户端正在使用中", "MCSync: Client Is Busy"),
                    JOptionPane.WARNING_MESSAGE));
        } catch (IOException exception) {
            System.err.println("[MCSync] " + language.text(
                    "无法显示客户端占用提示: ", "Cannot show the client-busy message: ") + exception.getMessage());
        }
    }

    private String buildPlanText(
            List<String> downloads,
            List<String> replacedOldVersions,
            List<String> rejectedUnknownMods,
            List<String> quarantinedServerRemoved,
            List<String> retainedServerRemoved,
            List<String> retainedClientMods) {
        StringBuilder result = new StringBuilder();
        result.append(text(
                "检测到本地 Mod 与云端清单不一致。\n\n",
                "Local mods differ from the cloud catalog.\n\n"));
        result.append(text("将下载或替换（", "Download or replace (")).append(downloads.size())
                .append(text("）：\n", "):\n"));
        if (downloads.isEmpty()) {
            result.append(text("  （无）\n", "  (none)\n"));
        } else {
            downloads.forEach(name -> result.append("  + ").append(name).append('\n'));
        }
        result.append(text(
                        "\n同一 Mod 的旧版本，将自动移入备份（",
                        "\nOlder versions of the same mod moved to backup ("))
                .append(replacedOldVersions.size()).append(text("）：\n", "):\n"));
        if (replacedOldVersions.isEmpty()) {
            result.append(text("  （无）\n", "  (none)\n"));
        } else {
            replacedOldVersions.forEach(name -> result.append("  ↻ ").append(name).append('\n'));
        }
        result.append(text(
                        "\n首次检查中确认不是纯客户端 Mod、将移入备份（",
                        "\nUnknown mods confirmed not to be client-only and moved to backup ("))
                .append(rejectedUnknownMods.size()).append(text("）：\n", "):\n"));
        if (rejectedUnknownMods.isEmpty()) {
            result.append(text("  （无）\n", "  (none)\n"));
        } else {
            rejectedUnknownMods.forEach(name -> result.append("  ? ").append(name).append('\n'));
        }
        result.append(text(
                        "\n用户选择移出的服务器已移除 Mod（",
                        "\nServer-removed mods selected for backup ("))
                .append(quarantinedServerRemoved.size()).append(text("）：\n", "):\n"));
        if (quarantinedServerRemoved.isEmpty()) {
            result.append(text("  （无）\n", "  (none)\n"));
        } else {
            quarantinedServerRemoved.forEach(name -> result.append("  - ").append(name).append('\n'));
        }
        result.append(text("\n服务器已移除但选择保留（", "\nServer-removed mods kept locally ("))
                .append(retainedServerRemoved.size()).append(text("）：\n", "):\n"));
        if (retainedServerRemoved.isEmpty()) {
            result.append(text("  （无）\n", "  (none)\n"));
        } else {
            retainedServerRemoved.forEach(name -> result.append("  = ").append(name).append('\n'));
        }
        result.append(text("\n用户自行添加并保留（", "\nUser-added mods retained ("))
                .append(retainedClientMods.size()).append(text("）：\n", "):\n"));
        if (retainedClientMods.isEmpty()) {
            result.append(text("  （无）\n", "  (none)\n"));
        } else {
            retainedClientMods.forEach(name -> result.append("  * ").append(name).append('\n'));
        }
        result.append(text(
                "\n正在自动下载。Mod 会同时通过 MD5/SHA256 校验后才提交，无需确认。",
                "\nDownloading automatically. Mods are committed only after both MD5 and SHA256 verification."));
        return result.toString();
    }

    private String buildRemovedText(List<String> serverRemoved) {
        StringBuilder result = new StringBuilder();
        result.append(text(
                "以下 Mod 存在于上次云端清单，但已从本次云端清单移除：\n\n",
                "These mods were in the previous cloud catalog but were removed from the current one:\n\n"));
        serverRemoved.forEach(name -> result.append("  - ").append(name).append('\n'));
        result.append(text(
                "\n选择“移出”时文件不会永久删除，而是保存到 .modsync/backups。\n"
                        + "选择“保留”后，这些文件将视为用户客户端 Mod，后续不再重复询问。\n\n"
                        + "只在本地出现、从未由服务器管理的 Mod 会自动保留。",
                "\nMove stores files in .modsync/backups instead of deleting them.\n"
                        + "Keep converts them to local client mods and does not ask again.\n\n"
                        + "Mods that only ever existed locally are retained automatically."));
        return result.toString();
    }

    private String buildResourcePackPlanText(
            List<String> downloads,
            List<String> backedUpRemoved) {
        StringBuilder result = new StringBuilder();
        result.append(text(
                "检测到本地资源包与云端 MD5 清单不一致。\n\n",
                "Local resource packs differ from the cloud MD5 catalog.\n\n"));
        result.append(text("将下载或替换（", "Download or replace (")).append(downloads.size())
                .append(text("）：\n", "):\n"));
        if (downloads.isEmpty()) {
            result.append(text("  （无）\n", "  (none)\n"));
        } else {
            downloads.forEach(name -> result.append("  + ").append(name).append('\n'));
        }
        result.append(text("\n云端清单已移除并将备份（", "\nRemoved from cloud catalog and backed up ("))
                .append(backedUpRemoved.size()).append(text("）：\n", "):\n"));
        if (backedUpRemoved.isEmpty()) {
            result.append(text("  （无）\n", "  (none)\n"));
        } else {
            backedUpRemoved.forEach(name -> result.append("  - ").append(name).append('\n'));
        }
        result.append(text(
                "\n玩家自行添加、未出现在云端清单中的其他资源包会原样保留。\n"
                        + "下载内容只有通过 MD5 复核后才会替换本地文件。",
                "\nUser-added resource packs not in the cloud catalog are retained.\n"
                        + "Downloads replace local files only after MD5 verification."));
        return result.toString();
    }

    private void ensureProgressDialog() {
        if (activeDownloadDialog != null && activeDownloadDialog.isDisplayable()) {
            return;
        }

        activePhaseLabel = new JLabel(text("MCSync 正在准备更新……", "MCSync is preparing an update…"));
        activePhaseLabel.setBorder(BorderFactory.createEmptyBorder(12, 12, 8, 12));

        activePlanArea = new JTextArea();
        activePlanArea.setEditable(false);
        activePlanArea.setLineWrap(true);
        activePlanArea.setWrapStyleWord(true);
        activePlanArea.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 13));
        activePlanArea.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
        JScrollPane scroll = new JScrollPane(activePlanArea);
        scroll.setPreferredSize(new Dimension(700, 300));

        activeFileDetailLabel = new JLabel(text("当前文件：准备中", "Current file: preparing"));
        activeFileDetailLabel.setBorder(BorderFactory.createEmptyBorder(4, 2, 6, 2));
        activeFileProgressBar = new JProgressBar(0, 1000);
        setWaitingProgress(activeFileProgressBar, text("准备中", "Preparing"));

        activeTotalDetailLabel = new JLabel(text("总进度：准备中", "Overall: preparing"));
        activeTotalDetailLabel.setBorder(BorderFactory.createEmptyBorder(10, 2, 6, 2));
        activeTotalProgressBar = new JProgressBar(0, 1000);
        setWaitingProgress(activeTotalProgressBar, text("准备中", "Preparing"));

        activeCloseButton = new JButton(text("关闭", "Close"));
        activeCloseButton.setVisible(false);
        activeCloseButton.addActionListener(event -> closeProgressWindowAndExitHelper());
        JPanel buttonRow = new JPanel(new BorderLayout());
        buttonRow.add(activeCloseButton, BorderLayout.EAST);

        JPanel progressPanel = new JPanel();
        progressPanel.setLayout(new BoxLayout(progressPanel, BoxLayout.Y_AXIS));
        progressPanel.setBorder(BorderFactory.createEmptyBorder(6, 12, 12, 12));
        progressPanel.add(activeFileDetailLabel);
        progressPanel.add(activeFileProgressBar);
        progressPanel.add(activeTotalDetailLabel);
        progressPanel.add(activeTotalProgressBar);
        progressPanel.add(buttonRow);

        JDialog dialog = new JDialog(
                (java.awt.Frame) null,
                text("MCSync 正在自动同步", "MCSync Automatic Sync"),
                false);
        dialog.setDefaultCloseOperation(WindowConstants.DO_NOTHING_ON_CLOSE);
        dialog.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosing(WindowEvent event) {
                if (activeCloseButton != null && activeCloseButton.isVisible()) {
                    closeProgressWindowAndExitHelper();
                }
            }
        });
        dialog.setAlwaysOnTop(true);
        dialog.setAutoRequestFocus(true);
        dialog.add(activePhaseLabel, BorderLayout.NORTH);
        dialog.add(scroll, BorderLayout.CENTER);
        dialog.add(progressPanel, BorderLayout.SOUTH);
        dialog.pack();
        dialog.setLocationRelativeTo(null);
        dialog.setVisible(true);
        dialog.toFront();
        dialog.requestFocus();
        activeDownloadDialog = dialog;
    }

    private void prepareForInteractiveDecision(String phase, String detail) {
        if (activeDownloadDialog == null || !activeDownloadDialog.isDisplayable()) {
            return;
        }
        activeDownloadDialog.setTitle(text("MCSync 等待你的选择", "MCSync Waiting for Your Choice"));
        activePhaseLabel.setText(phase);
        activeFileDetailLabel.setText(detail);
        setWaitingProgress(activeFileProgressBar, text("等待选择", "Waiting for selection"));
        activeDownloadDialog.toFront();
    }

    private static int showTopmostOptionDialog(
            Object message,
            String title,
            Object[] options,
            Object initialValue) {
        JDialog owner = activeDownloadDialog != null && activeDownloadDialog.isDisplayable()
                ? activeDownloadDialog
                : null;
        boolean restoreOwnerAlwaysOnTop = owner != null && owner.isAlwaysOnTop();
        if (owner != null) {
            // A topmost progress window can otherwise cover a JOptionPane that
            // was created without an owner. Temporarily lower the owner and
            // make the actual decision dialog topmost instead.
            owner.setAlwaysOnTop(false);
        }

        JOptionPane pane = new JOptionPane(
                message,
                JOptionPane.QUESTION_MESSAGE,
                JOptionPane.DEFAULT_OPTION,
                null,
                options,
                initialValue);
        JDialog decisionDialog = pane.createDialog(owner, title);
        decisionDialog.setAlwaysOnTop(true);
        decisionDialog.setAutoRequestFocus(true);
        decisionDialog.setModal(true);
        decisionDialog.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE);
        SwingUtilities.invokeLater(() -> {
            decisionDialog.toFront();
            decisionDialog.requestFocus();
        });

        try {
            decisionDialog.setVisible(true);
            Object selected = pane.getValue();
            for (int index = 0; index < options.length; index++) {
                if (Objects.equals(selected, options[index])) {
                    return index;
                }
            }
            return JOptionPane.CLOSED_OPTION;
        } finally {
            decisionDialog.dispose();
            if (owner != null && owner.isDisplayable()) {
                owner.setAlwaysOnTop(restoreOwnerAlwaysOnTop);
                owner.toFront();
                owner.requestFocus();
            }
        }
    }

    private void scheduleProgressFlush() {
        if (progressUpdateScheduled.compareAndSet(false, true)) {
            SwingUtilities.invokeLater(this::flushDownloadProgress);
        }
    }

    private void flushDownloadProgress() {
        try {
            DownloadProgress snapshot = pendingProgress.getAndSet(null);
            if (snapshot != null) {
                applyDownloadProgress(snapshot);
            }
        } finally {
            progressUpdateScheduled.set(false);
            if (pendingProgress.get() != null) {
                scheduleProgressFlush();
            }
        }
    }

    private void applyDownloadProgress(DownloadProgress snapshot) {
        ensureProgressDialog();
        activeDownloadDialog.toFront();
        activeDownloadDialog.setTitle(text("MCSync 正在下载", "MCSync Downloading"));
        activePhaseLabel.setText(text("正在下载 [", "Downloading [")
                + snapshot.fileIndex() + "/" + snapshot.fileCount()
                + "] " + snapshot.fileName());

        String downloaded = formatBytes(snapshot.fileDownloadedBytes());
        if (snapshot.fileTotalBytes() > 0) {
            double fraction = Math.min(1.0, (double) snapshot.fileDownloadedBytes() / snapshot.fileTotalBytes());
            int value = (int) Math.round(fraction * 1000.0);
            setProgress(activeFileProgressBar, value,
                    String.format(Locale.ROOT, "%.1f%%", fraction * 100.0));
            activeFileDetailLabel.setText(text("当前文件：", "Current file: ") + downloaded + " / "
                    + formatBytes(snapshot.fileTotalBytes()));
        } else {
            setWaitingProgress(activeFileProgressBar, text("已下载 ", "Downloaded ") + downloaded);
            activeFileDetailLabel.setText(text(
                    "当前文件：服务器未提供大小；已下载 ",
                    "Current file: server did not provide a size; downloaded ") + downloaded);
        }

        int totalValue = Math.max(0, Math.min(1000, snapshot.totalPermille()));
        setProgress(activeTotalProgressBar, totalValue,
                String.format(Locale.ROOT, "%.1f%%", totalValue / 10.0));
        if (snapshot.totalBytes() > 0 && snapshot.totalDownloadedBytes() >= 0) {
            activeTotalDetailLabel.setText(text("总进度：", "Overall: ")
                    + formatBytes(snapshot.totalDownloadedBytes())
                    + " / " + formatBytes(snapshot.totalBytes()));
        } else {
            activeTotalDetailLabel.setText(text("总进度：正在处理第 ", "Overall: processing file ")
                    + snapshot.fileIndex() + " / " + snapshot.fileCount()
                    + text(" 个文件（按文件/同步目标估算）", " (estimated by file/sync target)"));
        }
    }

    private static void setWaitingProgress(JProgressBar progressBar, String text) {
        progressBar.setIndeterminate(true);
        progressBar.setStringPainted(true);
        progressBar.setString(text);
    }

    private static void setProgress(JProgressBar progressBar, int value, String text) {
        progressBar.setIndeterminate(false);
        progressBar.setMinimum(0);
        progressBar.setMaximum(1000);
        progressBar.setValue(value);
        progressBar.setStringPainted(true);
        progressBar.setString(text);
    }

    private void setCompletedProgress(JProgressBar progressBar) {
        setProgress(progressBar, 1000, text("100% — 更新完成", "100% — Complete"));
    }

    private static String formatBytes(long bytes) {
        if (bytes < 1024) {
            return bytes + " B";
        }
        double value = bytes;
        String[] units = {"B", "KiB", "MiB", "GiB"};
        int unit = 0;
        while (value >= 1024.0 && unit < units.length - 1) {
            value /= 1024.0;
            unit++;
        }
        return String.format(Locale.ROOT, "%.1f %s", value, units[unit]);
    }

    private static void closeActiveDownloadDialog() {
        if (activeDownloadDialog != null) {
            activeDownloadDialog.dispose();
            activeDownloadDialog = null;
        }
        activePhaseLabel = null;
        activeFileDetailLabel = null;
        activeTotalDetailLabel = null;
        activeFileProgressBar = null;
        activeTotalProgressBar = null;
        activePlanArea = null;
        activeCloseButton = null;
    }

    boolean helperExitScheduled() {
        return helperExitScheduled;
    }

    private static void closeProgressWindowAndExitHelper() {
        closeActiveDownloadDialog();
        if (Boolean.getBoolean("modsync.helperProcess")) {
            System.exit(0);
        }
    }

    private static String mostUsefulMessage(Throwable failure) {
        Throwable current = failure;
        String selected = failure.getClass().getSimpleName();
        while (current != null) {
            if (current.getMessage() != null && !current.getMessage().isBlank()) {
                selected = current.getMessage();
            }
            current = current.getCause();
        }
        return selected;
    }

    static boolean dialogsAvailable() {
        return dialogsAvailable(null);
    }

    static boolean dialogsAvailable(RuntimeEnvironment environment) {
        if (Boolean.getBoolean("modsync.disableDialogs") || Boolean.getBoolean("modsync.forceHeadless")) {
            dialogsAvailableCache = false;
            return false;
        }
        if (dialogsAvailableCache != null) {
            return dialogsAvailableCache;
        }
        RuntimeEnvironment detected = environment == null ? RuntimeEnvironment.detect() : environment;
        if (!detected.dialogsUsable()) {
            dialogsAvailableCache = false;
            return false;
        }
        try {
            boolean available = !GraphicsEnvironment.isHeadless();
            dialogsAvailableCache = available;
            return available;
        } catch (Throwable failure) {
            dialogsAvailableCache = false;
            return false;
        }
    }

    static void resetDialogsAvailabilityForTests() {
        dialogsAvailableCache = null;
    }

    static void markDialogsUnavailable(String reason) {
        dialogsAvailableCache = false;
        System.setProperty("modsync.disableDialogs", "true");
        System.err.println("[MCSync] " + staticText(
                        "图形窗口不可用，已切换为无弹窗模式",
                        "GUI dialogs are unavailable; switched to headless mode")
                + (reason == null || reason.isBlank() ? "" : ": " + reason));
    }

    private static String staticText(String chinese, String english) {
        return DisplayLanguage.detect(resolveOptionalGameDirectory()).text(chinese, english);
    }

    private static Path resolveOptionalGameDirectory() {
        String configured = System.getProperty("modsync.gameDir");
        if (configured != null && !configured.isBlank()) {
            return Path.of(configured.strip());
        }
        return null;
    }

    private static void runOnUiThread(Runnable action) throws IOException {
        if (!dialogsAvailable()) {
            throw new IOException(staticText(
                    "当前环境不支持图形提示窗口",
                    "The current environment does not support GUI dialogs"));
        }
        if (SwingUtilities.isEventDispatchThread()) {
            action.run();
            return;
        }
        try {
            SwingUtilities.invokeAndWait(action);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IOException(staticText(
                    "等待提示窗口时线程被中断",
                    "Interrupted while waiting for the dialog"), exception);
        } catch (InvocationTargetException exception) {
            markDialogsUnavailable(String.valueOf(exception.getCause()));
            throw new IOException(staticText(
                    "显示提示窗口失败",
                    "Failed to show the dialog"), exception.getCause());
        } catch (RuntimeException exception) {
            markDialogsUnavailable(exception.getMessage());
            throw new IOException(staticText(
                    "显示提示窗口失败",
                    "Failed to show the dialog"), exception);
        }
    }
}
