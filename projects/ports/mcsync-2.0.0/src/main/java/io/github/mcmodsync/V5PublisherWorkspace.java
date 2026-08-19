package io.github.mcmodsync;

import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JComboBox;
import javax.swing.JFileChooser;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JSpinner;
import javax.swing.JSplitPane;
import javax.swing.JTabbedPane;
import javax.swing.JTable;
import javax.swing.JTextArea;
import javax.swing.JTextField;
import javax.swing.SpinnerNumberModel;
import javax.swing.SwingWorker;
import javax.swing.table.AbstractTableModel;
import javax.swing.table.TableColumn;
import java.awt.BorderLayout;
import java.awt.Dimension;
import java.awt.FlowLayout;
import java.awt.Font;
import java.awt.GridBagConstraints;
import java.awt.GridBagLayout;
import java.awt.Insets;
import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/** Primary MCSync 2.0 publisher workspace embedded in the executable JAR. */
final class V5PublisherWorkspace {
    private static final List<String> AUTO_SCAN_ROOTS = List.of(
            "mods", "resourcepacks", "shaderpacks", "kubejs", "tacz", "tlm_custom_pack");
    private static final Set<String> NEVER_SCAN_ROOTS = Set.of(
            "saves", "world", "logs", "crash-reports", "screenshots", "natives", "libraries",
            "assets", "versions", "downloads", "backups", "simplebackups", ".minecraft");
    private static final String[] FILE_SIDES = {"client", "both", "server"};

    private final JFrame owner;
    private final JPanel root = new JPanel(new BorderLayout(8, 8));
    private final JTextField gameRoot = new JTextField();
    private final JTextField outputDirectory = new JTextField();
    private final JTextField releaseId = new JTextField("motiquies-2.0.0-ota.1");
    private final JSpinner releaseSequence = new JSpinner(new SpinnerNumberModel(
            PublisherProjectV5.currentTimeReleaseSequence(), 1L, Long.MAX_VALUE, 1L));
    private final JCheckBox autoReleaseSequence = new JCheckBox("导出时按当前系统时间刷新序号", true);
    private final JTextField minimumVersion = new JTextField(BuildInfo.VERSION);
    private final JTextField publicBaseUrl = new JTextField("https://files.example.com/mcsync");
    private final JTextField stableManifestPath = new JTextField("channel/stable/mods-v4.txt");
    private final JTextField legacyV4Path = new JTextField("legacy/1.9/mods-v4.txt");
    private final JTextField legacyV2Path = new JTextField("legacy/1.6/mods.txt");
    private final JTextField legacyV4CurrentUrls = new JTextField("https://old.example.com/client/mods-v4.txt");
    private final JTextField legacyV2CurrentUrls = new JTextField("https://old.example.com/client/mods.txt");
    private final JCheckBox generateLegacyGateways = new JCheckBox("生成 1.9.x 和 1.6.x/1.7.x 永久升级入口", true);
    private final FileModel files = new FileModel();
    private final ScopeModel scopes = new ScopeModel();
    private final ConfigModel config = new ConfigModel();
    private final JTable fileTable = new JTable(files);
    private final JTable scopeTable = new JTable(scopes);
    private final JTable configTable = new JTable(config);
    private final JTextArea validation = new JTextArea();
    private final JLabel summary = new JLabel();
    private final PublisherModAutoMatcher modMatcher = new PublisherModAutoMatcher();

    private V5PublisherWorkspace(JFrame owner) {
        this.owner = owner;
        scopes.addDefaults();
        buildUi();
        refreshSummary();
    }

    static JPanel create(JFrame owner) {
        return new V5PublisherWorkspace(owner).root;
    }

    private void buildUi() {
        root.setBorder(BorderFactory.createEmptyBorder(10, 10, 10, 10));
        JPanel heading = new JPanel(new BorderLayout());
        JLabel title = new JLabel("MCSync 2.0 OTA 发布工作台");
        title.setFont(title.getFont().deriveFont(Font.BOLD, 18f));
        heading.add(title, BorderLayout.WEST);
        heading.add(summary, BorderLayout.EAST);
        root.add(heading, BorderLayout.NORTH);

        JTabbedPane tabs = new JTabbedPane();
        tabs.addTab("发布项目", projectPanel());
        tabs.addTab("文件与来源", filesPanel());
        tabs.addTab("同步范围", scopesPanel());
        tabs.addTab("配置 OTA", configPanel());
        tabs.addTab("远端与旧版升级", remotePanel());
        tabs.addTab("验证与导出", exportPanel());
        root.add(tabs, BorderLayout.CENTER);
    }

    private JPanel projectPanel() {
        JPanel panel = new JPanel(new BorderLayout(8, 8));
        JPanel form = new JPanel(new GridBagLayout());
        form.setBorder(BorderFactory.createEmptyBorder(18, 18, 10, 18));
        GridBagConstraints c = constraints();
        addPathRow(form, c, 0, "测试完成的客户端游戏根目录：", gameRoot, "选择目录", true);
        addPathRow(form, c, 1, "空的发布输出目录：", outputDirectory, "选择目录", false);
        addFieldRow(form, c, 2, "发布 ID：", releaseId);
        c.gridx = 0;
        c.gridy = 3;
        c.weightx = 0;
        form.add(new JLabel("防降级序号："), c);
        c.gridx = 1;
        c.weightx = 1;
        form.add(releaseSequence, c);
        c.gridx = 2;
        c.weightx = 0;
        form.add(autoReleaseSequence, c);
        addFieldRow(form, c, 4, "最低 MCSync 版本：", minimumVersion);

        JTextArea note = new JTextArea(
                "此工作台直接产生 schema-v5 发布。releaseSequence 只能增加，客户端会拒绝降级。\n"
                        + "自动扫描只查找 mods/resourcepacks/shaderpacks/kubejs 等可分发内容；"
                        + "config/defaultconfigs 默认不整树扫描，应在“配置 OTA”按键级管理，防止携带密钥。");
        note.setEditable(false);
        note.setLineWrap(true);
        note.setWrapStyleWord(true);
        note.setOpaque(false);
        note.setBorder(BorderFactory.createEmptyBorder(10, 22, 10, 22));
        panel.add(form, BorderLayout.NORTH);
        panel.add(note, BorderLayout.CENTER);

        JPanel actions = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        JButton load = new JButton("打开发布项目…");
        JButton save = new JButton("保存发布项目…");
        load.addActionListener(event -> loadProject());
        save.addActionListener(event -> saveProject());
        actions.add(load);
        actions.add(save);
        panel.add(actions, BorderLayout.SOUTH);
        return panel;
    }

    private JPanel filesPanel() {
        configureCombo(fileTable, 5, FILE_SIDES);
        fileTable.setAutoCreateRowSorter(true);
        fileTable.setRowHeight(23);

        JPanel panel = new JPanel(new BorderLayout(6, 6));
        JTextArea help = new JTextArea(
                "只有 mods/*.jar 会进行 Modrinth/CurseForge 精确哈希匹配；匹配成功使用上游来源，"
                        + "匹配失败回退为本地托管。资源包、光影、KubeJS、配置等始终只作为普通本地发布文件，"
                        + "不会接触模组站或镜像接口。");
        help.setEditable(false);
        help.setLineWrap(true);
        help.setWrapStyleWord(true);
        help.setRows(2);
        help.setOpaque(false);
        panel.add(help, BorderLayout.NORTH);
        panel.add(new JScrollPane(fileTable), BorderLayout.CENTER);

        JPanel buttons = new JPanel(new FlowLayout(FlowLayout.LEFT));
        JButton scan = new JButton("扫描安全内容目录");
        JButton add = new JButton("添加文件…");
        JButton rematch = new JButton("自动匹配全部 Mod");
        JButton remove = new JButton("移除选中");
        scan.addActionListener(event -> scanSafeRoots(scan));
        add.addActionListener(event -> addFiles());
        rematch.addActionListener(event -> autoMatchMods(rematch));
        remove.addActionListener(event -> removeSelected(fileTable, files.rows));
        buttons.add(scan);
        buttons.add(add);
        buttons.add(rematch);
        buttons.add(remove);
        panel.add(buttons, BorderLayout.SOUTH);
        return panel;
    }

    private JPanel scopesPanel() {
        configureCombo(scopeTable, 1, new String[]{"managed", "additive", "first-install"});
        scopeTable.setRowHeight(24);
        JPanel panel = new JPanel(new BorderLayout(6, 6));
        panel.add(new JScrollPane(scopeTable), BorderLayout.CENTER);
        JPanel footer = new JPanel(new BorderLayout());
        JTextArea excluded = new JTextArea(
                "永久排除：saves/world/playerdata/advancements/stats/logs/crash-reports/screenshots/"
                        + "journeymap/xaero 玩家探索数据、运行库与启动器缓存。\n"
                        + "内置于 Mod JAR 中的默认资源包/数据包/模型包不单独同步，由 mods 文件本身管理。");
        excluded.setEditable(false);
        excluded.setLineWrap(true);
        excluded.setWrapStyleWord(true);
        excluded.setRows(3);
        excluded.setOpaque(false);
        JPanel buttons = new JPanel(new FlowLayout(FlowLayout.LEFT));
        JButton add = new JButton("添加范围");
        JButton remove = new JButton("移除选中");
        add.addActionListener(event -> { scopes.rows.add(new ScopeRow("custom", "additive")); scopes.fireTableDataChanged(); });
        remove.addActionListener(event -> removeSelected(scopeTable, scopes.rows));
        buttons.add(add);
        buttons.add(remove);
        footer.add(excluded, BorderLayout.CENTER);
        footer.add(buttons, BorderLayout.SOUTH);
        panel.add(footer, BorderLayout.SOUTH);
        return panel;
    }

    private JPanel configPanel() {
        configTable.setAutoCreateRowSorter(true);
        configTable.setRowHeight(23);
        configureCombo(configTable, 1, new String[]{"config-set", "config-merge", "file-replace"});
        configureCombo(configTable, 2, new String[]{"toml", "json", "properties", "json5", "snbt", "text", "binary"});
        configureCombo(configTable, 4, new String[]{"boolean", "integer", "decimal", "string", "array", "object", "binary"});
        configureCombo(configTable, 8, new String[]{"create", "skip", "block"});
        configureCombo(configTable, 9, new String[]{"block", "keep-local", "report", "force", "replace-if-expected"});
        configureCombo(configTable, 10, new String[]{"client", "integrated_server", "dedicated_server", "both"});
        configureCombo(configTable, 11, new String[]{"prelaunch", "first-install"});

        JPanel panel = new JPanel(new BorderLayout(6, 6));
        panel.add(new JScrollPane(configTable), BorderLayout.CENTER);
        JTextArea help = new JTextArea(
                "expected/desired 使用 JSON 值（字符串可直接输入）。file-replace 必须填 expectedSha256 或 absent；"
                        + "密钥、token、玩家身份和存档状态不允许进入 OTA。");
        help.setEditable(false);
        help.setOpaque(false);
        help.setLineWrap(true);
        help.setWrapStyleWord(true);
        JPanel footer = new JPanel(new BorderLayout());
        footer.add(help, BorderLayout.CENTER);
        JPanel buttons = new JPanel(new FlowLayout(FlowLayout.LEFT));
        JButton add = new JButton("添加配置操作");
        JButton remove = new JButton("移除选中");
        add.addActionListener(event -> { config.rows.add(ConfigRow.defaults()); config.fireTableDataChanged(); });
        remove.addActionListener(event -> removeSelected(configTable, config.rows));
        buttons.add(add);
        buttons.add(remove);
        footer.add(buttons, BorderLayout.SOUTH);
        panel.add(footer, BorderLayout.SOUTH);
        return panel;
    }

    private JPanel remotePanel() {
        JPanel panel = new JPanel(new BorderLayout(8, 8));
        JPanel form = new JPanel(new GridBagLayout());
        form.setBorder(BorderFactory.createEmptyBorder(18, 18, 8, 18));
        GridBagConstraints c = constraints();
        addFieldRow(form, c, 0, "公开 HTTPS 根地址：", publicBaseUrl);
        addFieldRow(form, c, 1, "2.0 稳定入口：", stableManifestPath);
        addFieldRow(form, c, 2, "1.9.x 升级入口：", legacyV4Path);
        addFieldRow(form, c, 3, "1.6.x/1.7.x 升级入口：", legacyV2Path);
        addFieldRow(form, c, 4, "1.9.x 当前实际 URL（多个用逗号）：", legacyV4CurrentUrls);
        addFieldRow(form, c, 5, "1.6.x/1.7.x 当前实际 URL：", legacyV2CurrentUrls);
        c.gridx = 1;
        c.gridy = 6;
        c.gridwidth = 2;
        form.add(generateLegacyGateways, c);
        panel.add(form, BorderLayout.NORTH);

        JTextArea explanation = new JTextArea(
                "输出会按下列布局生成：\n\n"
                        + "releases/<releaseSequence>/       不可变的版本文件与 manifest-v5.json\n"
                        + "channel/stable/mods-v4.txt        2.0 客户端的固定 v5 入口\n"
                        + "legacy/1.9/mods-v4.txt            1.8/1.9 升级网关\n"
                        + "legacy/1.6/mods.txt               1.6/1.7 v2 升级网关\n"
                        + "client-modsync.properties         客户端/配置引导用的地址片段\n\n"
                        + "稳定入口仍使用 mods-v4.txt 文件名，但内容是 schema-v5 JSON。"
                        + "这样旧配置引导器允许该 URL，2.0 又可以根据内容自动识别新清单。\n"
                        + "旧客户端只读取它们现在已经配置的旧 URL。必须把 legacy 网关部署到这些原地址，"
                        + "或从原地址做 HTTP 重定向。\n"
                        + "发布时先上传 releases 和 legacy，部署旧 URL，最后原子替换 channel/stable/mods-v4.txt。");
        explanation.setEditable(false);
        explanation.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 13));
        explanation.setLineWrap(true);
        explanation.setWrapStyleWord(true);
        explanation.setBorder(BorderFactory.createTitledBorder("云端布局与发布顺序"));
        panel.add(new JScrollPane(explanation), BorderLayout.CENTER);
        return panel;
    }

    private JPanel exportPanel() {
        validation.setEditable(false);
        validation.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 13));
        validation.setLineWrap(true);
        validation.setWrapStyleWord(true);
        validation.setText("点击“验证项目”检查路径、Mod 自动匹配结果和配置操作。\n");
        JPanel panel = new JPanel(new BorderLayout(6, 6));
        JSplitPane split = new JSplitPane(JSplitPane.VERTICAL_SPLIT,
                new JScrollPane(validation), releaseChecklist());
        split.setResizeWeight(0.72);
        split.setBorder(null);
        panel.add(split, BorderLayout.CENTER);
        JPanel actions = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        JButton validate = new JButton("验证项目");
        JButton save = new JButton("保存项目 JSON…");
        JButton publish = new JButton("验证并导出 OTA");
        validate.addActionListener(event -> showValidation());
        save.addActionListener(event -> saveProject());
        publish.addActionListener(event -> publish(publish));
        actions.add(validate);
        actions.add(save);
        actions.add(publish);
        panel.add(actions, BorderLayout.SOUTH);
        return panel;
    }

    private JScrollPane releaseChecklist() {
        JTextArea checklist = new JTextArea(
                "导出门禁\n"
                        + "  • mods/*.jar 已完成平台精确匹配或回退本地发布\n"
                        + "  • 其他文件全部使用本地发布，不接触模组站\n"
                        + "  • 中国镜像仅是第三方传输候选，保留官方回退\n"
                        + "  • required 文件不能使用 manual\n"
                        + "  • 配置 OTA 有前像、冲突策略和作用端\n"
                        + "  • 输出目录为空，不混入旧发布");
        checklist.setEditable(false);
        checklist.setOpaque(false);
        return new JScrollPane(checklist);
    }

    private void addPathRow(
            JPanel form, GridBagConstraints c, int row, String label, JTextField field, String buttonText,
            boolean existing) {
        c.gridx = 0;
        c.gridy = row;
        c.weightx = 0;
        form.add(new JLabel(label), c);
        c.gridx = 1;
        c.weightx = 1;
        form.add(field, c);
        JButton button = new JButton(buttonText);
        c.gridx = 2;
        c.weightx = 0;
        form.add(button, c);
        button.addActionListener(event -> chooseDirectory(field, existing));
    }

    private static void addFieldRow(JPanel form, GridBagConstraints c, int row, String label, JTextField field) {
        c.gridx = 0;
        c.gridy = row;
        c.weightx = 0;
        form.add(new JLabel(label), c);
        c.gridx = 1;
        c.gridwidth = 2;
        c.weightx = 1;
        form.add(field, c);
        c.gridwidth = 1;
    }

    private static GridBagConstraints constraints() {
        GridBagConstraints c = new GridBagConstraints();
        c.insets = new Insets(6, 6, 6, 6);
        c.fill = GridBagConstraints.HORIZONTAL;
        return c;
    }

    private void chooseDirectory(JTextField target, boolean existing) {
        JFileChooser chooser = new JFileChooser();
        chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY);
        chooser.setDialogTitle(existing ? "选择游戏根目录" : "选择空的发布输出目录");
        if (!target.getText().isBlank()) chooser.setCurrentDirectory(Path.of(target.getText()).toFile());
        int result = existing ? chooser.showOpenDialog(owner) : chooser.showSaveDialog(owner);
        if (result == JFileChooser.APPROVE_OPTION) {
            target.setText(chooser.getSelectedFile().toPath().toAbsolutePath().normalize().toString());
        }
    }

    private void scanSafeRoots(JButton button) {
        Path rootPath;
        try {
            rootPath = requireGameRoot();
        } catch (IOException failure) {
            showError(failure.getMessage());
            return;
        }
        button.setEnabled(false);
        validation.append("\n正在扫描安全内容目录…\n");
        new SwingWorker<List<FileRow>, Void>() {
            @Override
            protected List<FileRow> doInBackground() throws Exception {
                ArrayList<FileRow> found = new ArrayList<>();
                Set<String> existing = files.normalizedPaths();
                for (String directory : AUTO_SCAN_ROOTS) {
                    Path scanRoot = rootPath.resolve(directory);
                    if (!Files.isDirectory(scanRoot, LinkOption.NOFOLLOW_LINKS)) continue;
                    try (var stream = Files.walk(scanRoot)) {
                        for (Path path : stream.filter(candidate -> Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS))
                                .sorted().toList()) {
                            if (Files.isSymbolicLink(path)) continue;
                            String relative = rootPath.relativize(path).toString().replace('\\', '/');
                            String first = relative.split("/", 2)[0].toLowerCase(Locale.ROOT);
                            if (NEVER_SCAN_ROOTS.contains(first) || !existing.add(relative.toLowerCase(Locale.ROOT))) continue;
                            FileRow row = FileRow.scanned(relative, kindFor(relative));
                            if (!PublisherModAutoMatcher.isModArtifact(relative, row.kind)) {
                                row.confirmed = true;
                                row.applyLocal("非 Mod 文件固定本地托管");
                            }
                            found.add(row);
                        }
                    }
                }
                List<FileRow> modRows = found.stream()
                        .filter(row -> PublisherModAutoMatcher.isModArtifact(row.path, row.kind)).toList();
                Map<Path, PublisherModAutoMatcher.Match> matches = modMatcher.matchAll(
                        modRows.stream().map(row -> rootPath.resolve(row.path)).toList());
                for (FileRow row : modRows) {
                    PublisherModAutoMatcher.Match match = matches.get(rootPath.resolve(row.path));
                    if (match == null) match = new PublisherModAutoMatcher.Match(
                            PublisherModAutoMatcher.localDownload(), "未匹配，使用本地文件");
                    row.applyMatch(match);
                }
                return found;
            }

            @Override
            protected void done() {
                button.setEnabled(true);
                try {
                    List<FileRow> found = get();
                    files.rows.addAll(found);
                    files.rows.sort(Comparator.comparing(row -> row.path));
                    files.fireTableDataChanged();
                    validation.append("扫描完成：新增 " + found.size()
                            + " 个文件；Mod 已按精确哈希匹配，其他文件固定本地托管。\n");
                    refreshSummary();
                } catch (Exception failure) {
                    showError(cause(failure).getMessage());
                }
            }
        }.execute();
    }

    private void autoMatchMods(JButton button) {
        Path rootPath;
        try {
            rootPath = requireGameRoot();
        } catch (IOException failure) {
            showError(failure.getMessage());
            return;
        }
        List<FileRow> mods = files.rows.stream()
                .filter(row -> PublisherModAutoMatcher.isModArtifact(row.path, row.kind))
                .toList();
        if (mods.isEmpty()) {
            validation.append("没有需要匹配的 mods/*.jar。\n");
            return;
        }
        if (button != null) button.setEnabled(false);
        validation.append("正在批量查询 Modrinth/CurseForge 精确哈希…\n");
        new SwingWorker<Map<Path, PublisherModAutoMatcher.Match>, Void>() {
            @Override protected Map<Path, PublisherModAutoMatcher.Match> doInBackground() {
                return modMatcher.matchAll(mods.stream().map(row -> rootPath.resolve(row.path)).toList());
            }
            @Override protected void done() {
                if (button != null) button.setEnabled(true);
                try {
                    Map<Path, PublisherModAutoMatcher.Match> matches = get();
                    int platform = 0;
                    for (FileRow row : mods) {
                        PublisherModAutoMatcher.Match match = matches.get(rootPath.resolve(row.path));
                        if (match == null) match = new PublisherModAutoMatcher.Match(
                                PublisherModAutoMatcher.localDownload(), "未匹配，使用本地文件");
                        row.applyMatch(match);
                        platform += !"publisher-hosted".equals(row.source) ? 1 : 0;
                    }
                    files.fireTableDataChanged();
                    refreshSummary();
                    validation.append("Mod 自动匹配完成：" + platform + " 个上游匹配，"
                            + (mods.size() - platform) + " 个回退本地托管。\n");
                } catch (Exception failure) {
                    showError(cause(failure).getMessage());
                }
            }
        }.execute();
    }

    private void addFiles() {
        Path rootPath;
        try {
            rootPath = requireGameRoot();
        } catch (IOException failure) {
            showError(failure.getMessage());
            return;
        }
        JFileChooser chooser = new JFileChooser(rootPath.toFile());
        chooser.setMultiSelectionEnabled(true);
        chooser.setFileSelectionMode(JFileChooser.FILES_ONLY);
        if (chooser.showOpenDialog(owner) != JFileChooser.APPROVE_OPTION) return;
        Set<String> existing = files.normalizedPaths();
        for (java.io.File selected : chooser.getSelectedFiles()) {
            Path path = selected.toPath().toAbsolutePath().normalize();
            if (!path.startsWith(rootPath)) {
                showError("只能添加游戏根目录内的文件：" + path);
                continue;
            }
            String relative = rootPath.relativize(path).toString().replace('\\', '/');
            if (existing.add(relative.toLowerCase(Locale.ROOT))) {
                FileRow row = FileRow.scanned(relative, kindFor(relative));
                if (!PublisherModAutoMatcher.isModArtifact(relative, row.kind)) {
                    row.confirmed = true;
                    row.applyLocal("非 Mod 文件固定本地托管");
                }
                files.rows.add(row);
            }
        }
        files.rows.sort(Comparator.comparing(row -> row.path));
        files.fireTableDataChanged();
        refreshSummary();
        if (files.rows.stream().anyMatch(row -> PublisherModAutoMatcher.isModArtifact(row.path, row.kind)
                && !row.confirmed)) autoMatchMods(null);
    }

    private static String kindFor(String relative) {
        String normalized = relative.toLowerCase(Locale.ROOT);
        if (normalized.startsWith("mods/")) return "mod";
        if (normalized.startsWith("resourcepacks/")) return "resource-pack";
        if (normalized.startsWith("shaderpacks/")) return "shader-pack";
        if (normalized.startsWith("kubejs/")) return "kubejs";
        if (normalized.startsWith("defaultconfigs/")) return "default-config";
        if (normalized.startsWith("config/")) return "config";
        return "support";
    }

    private List<String> validateProject() {
        ArrayList<String> errors = new ArrayList<>();
        Path rootPath = null;
        try {
            rootPath = requireGameRoot();
        } catch (IOException failure) {
            errors.add(failure.getMessage());
        }
        if (!releaseId.getText().matches("[A-Za-z0-9._-]{1,128}")) errors.add("releaseId 格式无效。");
        if (minimumVersion.getText().isBlank()) errors.add("最低 MCSync 版本不能为空。");
        try {
            URI base = URI.create(normalizedBaseUrl());
            if (!"https".equalsIgnoreCase(base.getScheme()) || base.getHost() == null) {
                errors.add("公开根地址必须是 HTTPS 绝对地址。");
            }
            validateCloudPath(stableManifestPath.getText(), "2.0 稳定入口", "mods-v4.txt");
            validateCloudPath(legacyV4Path.getText(), "1.9.x 入口", "mods-v4.txt");
            validateCloudPath(legacyV2Path.getText(), "1.6.x 入口", "mods.txt");
            if (generateLegacyGateways.isSelected()) {
                validateExistingUrls(legacyV4CurrentUrls.getText(), "1.9.x", "mods-v4.txt");
                validateExistingUrls(legacyV2CurrentUrls.getText(), "1.6.x/1.7.x", "mods.txt");
            }
        } catch (Exception failure) {
            errors.add("远端配置无效：" + failure.getMessage());
        }
        if (files.rows.isEmpty()) errors.add("至少需要一个发布文件。");
        Set<String> unique = new HashSet<>();
        for (int i = 0; i < files.rows.size(); i++) {
            FileRow row = files.rows.get(i);
            String at = "文件第 " + (i + 1) + " 行：";
            if (!row.confirmed) errors.add(at + "Mod 自动来源匹配尚未完成。");
            if (row.path.isBlank() || row.path.startsWith("/") || row.path.contains("..")
                    || !unique.add(row.path.toLowerCase(Locale.ROOT))) errors.add(at + "路径为空、不安全或重复。");
            if (rootPath != null && !Files.isRegularFile(rootPath.resolve(row.path), LinkOption.NOFOLLOW_LINKS)) {
                errors.add(at + "本地文件不存在：" + row.path);
            }
            boolean mod = PublisherModAutoMatcher.isModArtifact(row.path, row.kind);
            if (!mod && !row.source.equals("publisher-hosted")) {
                errors.add(at + "非 Mod 文件禁止使用模组站、镜像或 direct/manual 来源。");
            }
            if (!mod && !row.policy.equals("redistributable")) {
                errors.add(at + "非 Mod 文件固定使用本地托管策略。");
            }
            if (mod && row.source.equals("modrinth") && (row.projectId.isBlank() || row.versionId.isBlank())) {
                errors.add(at + "Modrinth 匹配缺少固定项目/版本。");
            }
            if (mod && row.source.equals("curseforge") && (row.projectId.isBlank() || !row.fileId.matches("[1-9][0-9]*"))) {
                errors.add(at + "CurseForge 匹配缺少固定项目/文件。");
            }
        }
        try {
            Map<String, Object> project = projectMap();
            StrictJson.parse(StrictJson.stringify(project));
            if (rootPath != null) PublisherProjectV5.validateProject(rootPath, project);
        } catch (Exception failure) {
            errors.add("项目结构无效：" + failure.getMessage());
        }
        return errors;
    }

    private void showValidation() {
        List<String> errors = validateProject();
        if (errors.isEmpty()) {
            validation.setText("PASS：项目的本地路径、来源、分发策略与配置操作已通过 GUI 预检。\n"
                    + "导出时还会计算 SHA-256，通过严格 schema-v5 解析，并解析平台固定版本地址。\n");
        } else {
            StringBuilder text = new StringBuilder("BLOCKED：发现 " + errors.size() + " 个问题\n\n");
            for (String error : errors) text.append(" - ").append(error).append('\n');
            validation.setText(text.toString());
        }
        validation.setCaretPosition(0);
    }

    private void publish(JButton button) {
        if (autoReleaseSequence.isSelected()) {
            releaseSequence.setValue(PublisherProjectV5.currentTimeReleaseSequence());
        }
        showValidation();
        List<String> errors = validateProject();
        if (!errors.isEmpty()) {
            JOptionPane.showMessageDialog(owner, "请先修复验证问题。", "发布被阻止", JOptionPane.WARNING_MESSAGE);
            return;
        }
        Path rootPath;
        Path output;
        try {
            rootPath = requireGameRoot();
            if (outputDirectory.getText().isBlank()) throw new IOException("请选择发布输出目录。");
            output = Path.of(outputDirectory.getText()).toAbsolutePath().normalize();
        } catch (Exception failure) {
            showError(failure.getMessage());
            return;
        }
        Map<String, Object> project;
        try {
            project = projectMap();
        } catch (Exception failure) {
            showError(failure.getMessage());
            return;
        }
        button.setEnabled(false);
        validation.append("\n开始计算哈希、解析平台来源并生成发布目录…\n");
        new SwingWorker<PublisherCloudBundle.Result, Void>() {
            @Override
            protected PublisherCloudBundle.Result doInBackground() throws Exception {
                Path updater = generateLegacyGateways.isSelected() ? locateUpdaterJar(rootPath) : null;
                return PublisherCloudBundle.publish(
                        rootPath, project, output, normalizedBaseUrl(), stableManifestPath.getText(),
                        legacyV4Path.getText(), legacyV2Path.getText(),
                        splitUrls(legacyV4CurrentUrls.getText()), splitUrls(legacyV2CurrentUrls.getText()),
                        generateLegacyGateways.isSelected(), updater);
            }

            @Override
            protected void done() {
                button.setEnabled(true);
                try {
                    PublisherCloudBundle.Result cloud = get();
                    PublisherProjectV5.Publication publication = cloud.publication();
                    validation.append("发布完成：" + publication.manifestPath() + "\n"
                            + "托管文件：" + publication.hostedFiles() + "\n"
                            + "报告：" + publication.reportPath() + "\n"
                            + "2.0 稳定入口：" + stableUrl() + "\n");
                    JOptionPane.showMessageDialog(owner,
                            "schema-v5 OTA 发布已生成。\n" + publication.manifestPath(),
                            "发布完成", JOptionPane.INFORMATION_MESSAGE);
                } catch (Exception failure) {
                    Throwable actual = cause(failure);
                    validation.append("发布失败：" + actual.getMessage() + "\n");
                    showError(actual.getMessage());
                }
            }
        }.execute();
    }

    private void saveProject() {
        try {
            JFileChooser chooser = new JFileChooser();
            chooser.setDialogTitle("保存 MCSync 2.0 发布项目");
            chooser.setSelectedFile(new java.io.File(releaseId.getText() + ".publisher.json"));
            if (chooser.showSaveDialog(owner) != JFileChooser.APPROVE_OPTION) return;
            Path output = chooser.getSelectedFile().toPath().toAbsolutePath().normalize();
            if (output.getParent() != null) Files.createDirectories(output.getParent());
            Files.writeString(output, StrictJson.stringify(projectMap()) + "\n", StandardCharsets.UTF_8);
            validation.append("项目已保存：" + output + "\n");
        } catch (Exception failure) {
            showError(failure.getMessage());
        }
    }

    private void loadProject() {
        JFileChooser chooser = new JFileChooser();
        chooser.setDialogTitle("打开 MCSync 2.0 发布项目");
        if (chooser.showOpenDialog(owner) != JFileChooser.APPROVE_OPTION) return;
        try {
            Object parsed = StrictJson.parse(Files.readString(chooser.getSelectedFile().toPath(), StandardCharsets.UTF_8));
            if (!(parsed instanceof Map<?, ?> raw)) throw new IOException("项目根必须是 JSON 对象。");
            @SuppressWarnings("unchecked") Map<String, Object> project = (Map<String, Object>) raw;
            loadProjectMap(project);
            validation.append("项目已加载：" + chooser.getSelectedFile() + "\n");
        } catch (Exception failure) {
            showError("无法加载项目：" + failure.getMessage());
        }
    }

    private Map<String, Object> projectMap() {
        LinkedHashMap<String, Object> project = new LinkedHashMap<>();
        project.put("schema", BigDecimal.ONE);
        project.put("releaseId", releaseId.getText().strip());
        project.put("releaseSequence", BigDecimal.valueOf(((Number) releaseSequence.getValue()).longValue()));
        project.put("minimumMCSyncVersion", minimumVersion.getText().strip());
        project.put("remote", Map.of(
                "baseUrl", normalizedBaseUrl(),
                "stablePath", cloudPath(stableManifestPath.getText()),
                "legacyV4Path", cloudPath(legacyV4Path.getText()),
                "legacyV2Path", cloudPath(legacyV2Path.getText()),
                "legacyV4CurrentUrls", legacyV4CurrentUrls.getText().strip(),
                "legacyV2CurrentUrls", legacyV2CurrentUrls.getText().strip(),
                "autoReleaseSequence", autoReleaseSequence.isSelected(),
                "generateLegacyGateways", generateLegacyGateways.isSelected()));
        project.put("managedScopes", scopes.rows.stream().map(row -> Map.of(
                "path", row.path.strip(), "policy", row.policy)).toList());
        project.put("files", files.rows.stream().map(this::fileJson).toList());
        project.put("configOperations", config.rows.stream().map(this::configJson).toList());
        return project;
    }

    private Path locateUpdaterJar(Path rootPath) throws IOException {
        try {
            URI location = V5PublisherWorkspace.class.getProtectionDomain().getCodeSource().getLocation().toURI();
            Path running = Path.of(location).toAbsolutePath().normalize();
            if (Files.isRegularFile(running) && running.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".jar")) {
                return running;
            }
        } catch (Exception ignored) {
        }
        Path mods = rootPath.resolve("mods");
        if (!Files.isDirectory(mods)) throw new IOException("游戏根目录缺少 mods，无法生成旧版升级入口。");
        ModManifest scanned = ModManifest.scan(mods);
        ManifestEntry updater = scanned.entries().stream().filter(entry -> entry.modId().equals("mcmodsync"))
                .findFirst().orElseThrow(() -> new IOException("找不到 MCSync/MCModSync 升级器 JAR。"));
        return mods.resolve(updater.fileName());
    }

    private String stableUrl() {
        return normalizedBaseUrl() + "/" + cloudPath(stableManifestPath.getText());
    }

    private String normalizedBaseUrl() {
        String value = publicBaseUrl.getText().strip();
        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
        return value;
    }

    private static String cloudPath(String value) {
        String normalized = value.strip().replace('\\', '/');
        while (normalized.startsWith("/")) normalized = normalized.substring(1);
        return normalized;
    }

    private static void validateCloudPath(String value, String label, String fileName) {
        String normalized = cloudPath(value);
        if (normalized.isBlank() || normalized.contains("..") || normalized.contains(":")
                || !normalized.endsWith("/" + fileName)) {
            throw new IllegalArgumentException(label + " 必须是以 /" + fileName + " 结尾的安全相对路径");
        }
    }

    private static void validateExistingUrls(String value, String label, String fileName) {
        List<String> urls = splitUrls(value);
        if (urls.isEmpty()) {
            throw new IllegalArgumentException(label + " 至少要填写一个当前客户端实际读取的 URL");
        }
        for (String raw : urls) {
            URI uri = URI.create(raw);
            boolean web = "https".equalsIgnoreCase(uri.getScheme()) || "http".equalsIgnoreCase(uri.getScheme());
            if (!web || uri.getHost() == null
                    || uri.getPath() == null || !uri.getPath().endsWith("/" + fileName)) {
                throw new IllegalArgumentException(label + " 旧 URL 必须是以 /" + fileName
                        + " 结尾的 HTTP/HTTPS 地址: " + raw);
            }
        }
    }

    private static List<String> splitUrls(String value) {
        return java.util.Arrays.stream((value == null ? "" : value).split("[,;\\r\\n]+"))
                .map(String::strip).filter(item -> !item.isEmpty()).toList();
    }

    private Map<String, Object> fileJson(FileRow row) {
        LinkedHashMap<String, Object> file = new LinkedHashMap<>();
        file.put("path", row.path.strip().replace('\\', '/'));
        file.put("kind", row.kind);
        file.put("required", row.required);
        file.put("restartRequired", row.restart);
        file.put("side", List.of(row.side));
        LinkedHashMap<String, Object> download = new LinkedHashMap<>();
        download.put("type", row.source);
        download.put("distributionPolicy", row.policy);
        if (!row.projectId.isBlank()) download.put("projectId", row.projectId.strip());
        if (!row.versionId.isBlank()) download.put("versionId", row.versionId.strip());
        if (row.source.equals("curseforge") && !row.fileId.isBlank()) {
            download.put("fileId", new BigDecimal(row.fileId.strip()));
        }
        if (row.source.equals("modrinth") || row.source.equals("curseforge")) {
            List<ReleaseManifestV5.DownloadEndpoint> endpoints = DownloadEndpointPresets.forPlatform(row.source, row.chinaMirror);
            download.put("endpoints", endpoints.stream().map(endpoint -> Map.of(
                    "url", endpoint.uri().toASCIIString(), "role", endpoint.role(),
                    "purpose", endpoint.purpose(), "region", endpoint.region(),
                    "priority", endpoint.priority(), "thirdParty", endpoint.thirdParty())).toList());
        } else if (row.source.equals("direct")) {
            download.put("endpoints", List.of(Map.of(
                    "url", row.directUrl.strip(), "role", "official", "purpose", "file",
                    "region", "global", "priority", 100, "thirdParty", false)));
        }
        file.put("download", download);
        return file;
    }

    private Map<String, Object> configJson(ConfigRow row) {
        LinkedHashMap<String, Object> operation = new LinkedHashMap<>();
        operation.put("path", row.path.strip().replace('\\', '/'));
        operation.put("op", row.operation);
        operation.put("format", row.format);
        if (!row.operation.equals("file-replace")) operation.put("key", row.key.strip());
        operation.put("valueType", row.valueType);
        operation.put("expected", parseValue(row.expected, row.valueType));
        operation.put("desired", parseValue(row.desired, row.valueType));
        if (!row.expectedSha256.isBlank()) operation.put("expectedSha256", row.expectedSha256.strip());
        operation.put("missingPolicy", row.missingPolicy);
        operation.put("conflictPolicy", row.conflictPolicy);
        operation.put("side", List.of(row.side));
        operation.put("phase", row.phase);
        operation.put("restartRequired", row.restart);
        return operation;
    }

    private static Object parseValue(String text, String type) {
        String stripped = text == null ? "" : text.strip();
        if (type.equals("string") || type.equals("binary")) return stripped;
        if (stripped.isEmpty()) return null;
        return StrictJson.parse(stripped);
    }

    @SuppressWarnings("unchecked")
    private void loadProjectMap(Map<String, Object> project) throws IOException {
        if (!BigDecimal.ONE.equals(project.get("schema"))) throw new IOException("只能打开 schema=1 的发布项目。");
        releaseId.setText(String.valueOf(project.getOrDefault("releaseId", "")));
        releaseSequence.setValue(((BigDecimal) project.getOrDefault("releaseSequence", BigDecimal.ONE)).longValue());
        minimumVersion.setText(String.valueOf(project.getOrDefault("minimumMCSyncVersion", BuildInfo.VERSION)));
        Map<String, Object> remote = (Map<String, Object>) project.getOrDefault("remote", Map.of());
        publicBaseUrl.setText(String.valueOf(remote.getOrDefault("baseUrl", publicBaseUrl.getText())));
        stableManifestPath.setText(String.valueOf(remote.getOrDefault("stablePath", stableManifestPath.getText())));
        legacyV4Path.setText(String.valueOf(remote.getOrDefault("legacyV4Path", legacyV4Path.getText())));
        legacyV2Path.setText(String.valueOf(remote.getOrDefault("legacyV2Path", legacyV2Path.getText())));
        legacyV4CurrentUrls.setText(String.valueOf(remote.getOrDefault(
                "legacyV4CurrentUrls", legacyV4CurrentUrls.getText())));
        legacyV2CurrentUrls.setText(String.valueOf(remote.getOrDefault(
                "legacyV2CurrentUrls", legacyV2CurrentUrls.getText())));
        autoReleaseSequence.setSelected(!Boolean.FALSE.equals(remote.get("autoReleaseSequence")));
        generateLegacyGateways.setSelected(!Boolean.FALSE.equals(remote.get("generateLegacyGateways")));
        scopes.rows.clear();
        for (Object value : (List<Object>) project.getOrDefault("managedScopes", List.of())) {
            Map<String, Object> row = (Map<String, Object>) value;
            scopes.rows.add(new ScopeRow(String.valueOf(row.get("path")), String.valueOf(row.get("policy"))));
        }
        files.rows.clear();
        for (Object value : (List<Object>) project.getOrDefault("files", List.of())) {
            Map<String, Object> row = (Map<String, Object>) value;
            Map<String, Object> download = (Map<String, Object>) row.getOrDefault("download", Map.of());
            List<Object> side = (List<Object>) row.getOrDefault("side", List.of("client"));
            FileRow file = FileRow.scanned(String.valueOf(row.get("path")), String.valueOf(row.get("kind")));
            file.confirmed = true;
            file.required = Boolean.TRUE.equals(row.get("required"));
            file.restart = !Boolean.FALSE.equals(row.get("restartRequired"));
            file.side = side.isEmpty() ? "client" : String.valueOf(side.getFirst());
            file.source = String.valueOf(download.getOrDefault("type", "publisher-hosted"));
            file.policy = String.valueOf(download.getOrDefault("distributionPolicy", defaultPolicy(file.source)));
            file.projectId = String.valueOf(download.getOrDefault("projectId", ""));
            file.versionId = String.valueOf(download.getOrDefault("versionId", ""));
            file.fileId = download.containsKey("fileId") ? String.valueOf(((BigDecimal) download.get("fileId")).longValue()) : "";
            List<Object> endpoints = (List<Object>) download.getOrDefault("endpoints", List.of());
            file.chinaMirror = endpoints.stream().filter(Map.class::isInstance).map(Map.class::cast)
                    .anyMatch(endpoint -> "cn".equals(endpoint.get("region")));
            file.directUrl = endpoints.stream().filter(Map.class::isInstance).map(Map.class::cast)
                    .filter(endpoint -> "file".equals(endpoint.get("purpose"))).map(endpoint -> String.valueOf(endpoint.get("url")))
                    .findFirst().orElse("");
            if (!PublisherModAutoMatcher.isModArtifact(file.path, file.kind)) {
                file.applyLocal("非 Mod 文件固定本地托管");
            }
            files.rows.add(file);
        }
        config.rows.clear();
        for (Object value : (List<Object>) project.getOrDefault("configOperations", List.of())) {
            Map<String, Object> row = (Map<String, Object>) value;
            ConfigRow item = ConfigRow.defaults();
            item.path = String.valueOf(row.getOrDefault("path", ""));
            item.operation = String.valueOf(row.getOrDefault("op", "config-set"));
            item.format = String.valueOf(row.getOrDefault("format", "toml"));
            item.key = String.valueOf(row.getOrDefault("key", ""));
            item.valueType = String.valueOf(row.getOrDefault("valueType", "string"));
            item.expected = displayValue(row.get("expected"), item.valueType);
            item.desired = displayValue(row.get("desired"), item.valueType);
            item.expectedSha256 = String.valueOf(row.getOrDefault("expectedSha256", ""));
            item.missingPolicy = String.valueOf(row.getOrDefault("missingPolicy", "block"));
            item.conflictPolicy = String.valueOf(row.getOrDefault("conflictPolicy", "block"));
            List<Object> side = (List<Object>) row.getOrDefault("side", List.of("both"));
            item.side = side.isEmpty() ? "both" : String.valueOf(side.getFirst());
            item.phase = String.valueOf(row.getOrDefault("phase", "prelaunch"));
            item.restart = !Boolean.FALSE.equals(row.get("restartRequired"));
            config.rows.add(item);
        }
        scopes.fireTableDataChanged();
        files.fireTableDataChanged();
        config.fireTableDataChanged();
        refreshSummary();
    }

    private static String displayValue(Object value, String type) {
        if (value == null) return "";
        if (type.equals("string") || type.equals("binary")) return String.valueOf(value);
        return StrictJson.stringify(value);
    }

    private Path requireGameRoot() throws IOException {
        if (gameRoot.getText().isBlank()) throw new IOException("请选择游戏根目录。");
        Path rootPath = Path.of(gameRoot.getText()).toAbsolutePath().normalize();
        if (!Files.isDirectory(rootPath)) throw new IOException("游戏根目录不存在：" + rootPath);
        return rootPath;
    }

    private void refreshSummary() {
        long confirmed = files.rows.stream().filter(row -> row.confirmed).count();
        summary.setText("文件 " + files.rows.size() + " / 已确认 " + confirmed
                + "  ·  范围 " + scopes.rows.size() + "  ·  配置操作 " + config.rows.size());
    }

    private void showError(String message) {
        JOptionPane.showMessageDialog(owner, message, "MCSync 2.0 发布器", JOptionPane.ERROR_MESSAGE);
    }

    private static Throwable cause(Throwable failure) {
        return failure.getCause() == null ? failure : failure.getCause();
    }

    private static void configureCombo(JTable table, int column, String[] values) {
        TableColumn target = table.getColumnModel().getColumn(column);
        target.setCellEditor(new javax.swing.DefaultCellEditor(new JComboBox<>(values)));
    }

    private static <T> void removeSelected(JTable table, List<T> rows) {
        int[] selected = table.getSelectedRows();
        for (int index = selected.length - 1; index >= 0; index--) {
            rows.remove(table.convertRowIndexToModel(selected[index]));
        }
        ((AbstractTableModel) table.getModel()).fireTableDataChanged();
    }

    private static String defaultPolicy(String source) {
        return source.equals("publisher-hosted") ? "redistributable" : source.equals("manual") ? "manual" : "upstream-only";
    }

    private static final class FileRow {
        boolean confirmed;
        String path;
        String kind;
        boolean required = true;
        boolean restart = true;
        String side = "client";
        String source = "publisher-hosted";
        String policy = "redistributable";
        String projectId = "";
        String versionId = "";
        String fileId = "";
        String directUrl = "";
        boolean chinaMirror = true;
        String matchDetail = "待匹配";

        static FileRow scanned(String path, String kind) {
            FileRow row = new FileRow();
            row.path = path;
            row.kind = kind;
            return row;
        }

        void applyLocal(String detail) {
            source = "publisher-hosted";
            policy = "redistributable";
            projectId = "";
            versionId = "";
            fileId = "";
            directUrl = "";
            chinaMirror = false;
            matchDetail = detail;
        }

        void applyMatch(PublisherModAutoMatcher.Match match) {
            Map<String, Object> download = match.download();
            source = String.valueOf(download.getOrDefault("type", "publisher-hosted"));
            policy = String.valueOf(download.getOrDefault("distributionPolicy", "redistributable"));
            projectId = String.valueOf(download.getOrDefault("projectId", ""));
            versionId = String.valueOf(download.getOrDefault("versionId", ""));
            Object id = download.get("fileId");
            fileId = id == null ? "" : String.valueOf(id);
            matchDetail = match.detail();
            confirmed = true;
        }
    }

    private static final class FileModel extends AbstractTableModel {
        private final String[] columns = {"状态", "相对路径", "类型", "必须", "重启", "作用端", "获取方式", "匹配结果"};
        final List<FileRow> rows = new ArrayList<>();

        @Override public int getRowCount() { return rows.size(); }
        @Override public int getColumnCount() { return columns.length; }
        @Override public String getColumnName(int column) { return columns[column]; }
        @Override public Class<?> getColumnClass(int column) { return Set.of(3, 4).contains(column) ? Boolean.class : String.class; }
        @Override public boolean isCellEditable(int row, int column) { return column == 3 || column == 4 || column == 5; }
        @Override public Object getValueAt(int rowIndex, int columnIndex) {
            FileRow r = rows.get(rowIndex);
            return switch (columnIndex) {
                case 0 -> r.confirmed ? "已确定" : "待匹配"; case 1 -> r.path; case 2 -> r.kind; case 3 -> r.required;
                case 4 -> r.restart; case 5 -> r.side;
                case 6 -> r.source.equals("publisher-hosted") ? "本地托管" : "上游平台";
                case 7 -> r.matchDetail; default -> "";
            };
        }
        @Override public void setValueAt(Object value, int rowIndex, int columnIndex) {
            FileRow r = rows.get(rowIndex);
            switch (columnIndex) {
                case 3 -> r.required = Boolean.TRUE.equals(value);
                case 4 -> r.restart = Boolean.TRUE.equals(value); case 5 -> r.side = String.valueOf(value);
                default -> { }
            }
            fireTableRowsUpdated(rowIndex, rowIndex);
        }
        Set<String> normalizedPaths() {
            HashSet<String> values = new HashSet<>();
            for (FileRow row : rows) values.add(row.path.toLowerCase(Locale.ROOT));
            return values;
        }
    }

    private static final class ScopeRow {
        String path;
        String policy;
        ScopeRow(String path, String policy) { this.path = path; this.policy = policy; }
    }

    private static final class ScopeModel extends AbstractTableModel {
        final List<ScopeRow> rows = new ArrayList<>();
        void addDefaults() {
            rows.add(new ScopeRow("mods", "managed"));
            rows.add(new ScopeRow("resourcepacks", "managed"));
            rows.add(new ScopeRow("shaderpacks", "managed"));
            rows.add(new ScopeRow("kubejs", "managed"));
            rows.add(new ScopeRow("config", "additive"));
            rows.add(new ScopeRow("defaultconfigs", "additive"));
            rows.add(new ScopeRow("configureddefaults", "first-install"));
            rows.add(new ScopeRow("options.txt", "first-install"));
        }
        @Override public int getRowCount() { return rows.size(); }
        @Override public int getColumnCount() { return 2; }
        @Override public String getColumnName(int column) { return column == 0 ? "相对路径" : "策略"; }
        @Override public boolean isCellEditable(int row, int column) { return true; }
        @Override public Object getValueAt(int row, int column) { return column == 0 ? rows.get(row).path : rows.get(row).policy; }
        @Override public void setValueAt(Object value, int row, int column) {
            if (column == 0) rows.get(row).path = String.valueOf(value); else rows.get(row).policy = String.valueOf(value);
            fireTableRowsUpdated(row, row);
        }
    }

    private static final class ConfigRow {
        String path = "config/example.toml";
        String operation = "config-set";
        String format = "toml";
        String key = "section.key";
        String valueType = "boolean";
        String expected = "false";
        String desired = "true";
        String expectedSha256 = "";
        String missingPolicy = "block";
        String conflictPolicy = "block";
        String side = "both";
        String phase = "prelaunch";
        boolean restart = true;
        static ConfigRow defaults() { return new ConfigRow(); }
    }

    private static final class ConfigModel extends AbstractTableModel {
        private final String[] columns = {"路径", "操作", "格式", "key", "值类型", "expected", "desired", "expectedSha256",
                "缺失", "冲突", "作用端", "阶段", "重启"};
        final List<ConfigRow> rows = new ArrayList<>();
        @Override public int getRowCount() { return rows.size(); }
        @Override public int getColumnCount() { return columns.length; }
        @Override public String getColumnName(int column) { return columns[column]; }
        @Override public Class<?> getColumnClass(int column) { return column == 12 ? Boolean.class : String.class; }
        @Override public boolean isCellEditable(int row, int column) { return true; }
        @Override public Object getValueAt(int row, int column) {
            ConfigRow r = rows.get(row);
            return switch (column) {
                case 0 -> r.path; case 1 -> r.operation; case 2 -> r.format; case 3 -> r.key;
                case 4 -> r.valueType; case 5 -> r.expected; case 6 -> r.desired; case 7 -> r.expectedSha256;
                case 8 -> r.missingPolicy; case 9 -> r.conflictPolicy; case 10 -> r.side;
                case 11 -> r.phase; case 12 -> r.restart; default -> "";
            };
        }
        @Override public void setValueAt(Object value, int row, int column) {
            ConfigRow r = rows.get(row);
            switch (column) {
                case 0 -> r.path = String.valueOf(value); case 1 -> r.operation = String.valueOf(value);
                case 2 -> r.format = String.valueOf(value); case 3 -> r.key = String.valueOf(value);
                case 4 -> r.valueType = String.valueOf(value); case 5 -> r.expected = String.valueOf(value);
                case 6 -> r.desired = String.valueOf(value); case 7 -> r.expectedSha256 = String.valueOf(value);
                case 8 -> r.missingPolicy = String.valueOf(value); case 9 -> r.conflictPolicy = String.valueOf(value);
                case 10 -> r.side = String.valueOf(value); case 11 -> r.phase = String.valueOf(value);
                case 12 -> r.restart = Boolean.TRUE.equals(value); default -> { }
            }
            fireTableRowsUpdated(row, row);
        }
    }
}
