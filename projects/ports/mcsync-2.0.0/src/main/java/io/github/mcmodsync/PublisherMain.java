package io.github.mcmodsync;

import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JFileChooser;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.JTextField;
import javax.swing.JTabbedPane;
import javax.swing.SwingUtilities;
import javax.swing.SwingWorker;
import javax.swing.UIManager;
import javax.swing.filechooser.FileNameExtensionFilter;
import java.awt.BorderLayout;
import java.awt.Desktop;
import java.awt.FlowLayout;
import java.awt.Font;
import java.awt.GraphicsEnvironment;
import java.awt.GridBagConstraints;
import java.awt.GridBagLayout;
import java.awt.Insets;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public final class PublisherMain {
    private static final DisplayLanguage LANGUAGE = DisplayLanguage.detect(null);

    private PublisherMain() {
    }

    public static void main(String[] arguments) {
        if (arguments.length > 0
                && arguments[0].equals(PortableUpdateHelper.INTERNAL_LAUNCH_ARGUMENT)) {
            PortableUpdateHelper.main(Arrays.copyOfRange(arguments, 1, arguments.length));
            return;
        }
        if (arguments.length > 0) {
            int status = runCommandLine(arguments);
            if (status != 0) {
                System.exit(status);
            }
            return;
        }

        if (GraphicsEnvironment.isHeadless()) {
            printUsage();
            System.exit(2);
        }
        SwingUtilities.invokeLater(PublisherMain::showWindow);
    }

    private static int runCommandLine(String[] arguments) {
        if (arguments.length == 1 && (arguments[0].equals("--help") || arguments[0].equals("-h"))) {
            printUsage();
            return 0;
        }
        if (arguments.length == 1 && arguments[0].equals("--version")) {
            System.out.println(BuildInfo.PRODUCT_NAME + " " + BuildInfo.VERSION);
            return 0;
        }
        if (arguments.length >= 1 && arguments[0].equals("--upgrade-v2")) {
            if (arguments.length < 2 || arguments.length > 3) {
                printUsage();
                return 2;
            }
            Path modsDirectory = Path.of(arguments[1]).toAbsolutePath().normalize();
            Path output = arguments.length == 3
                    ? Path.of(arguments[2]).toAbsolutePath().normalize()
                    : modsDirectory.resolve(LegacyUpgradeManifest.DEFAULT_FILE_NAME);
            try {
                PublicationScan publication = preparePublication(modsDirectory);
                ModManifest catalog = completePublication(publication.scanned(), publication);
                LegacyUpgradeManifest.write(catalog, output);
                System.out.println(text(
                        "1.6.x/1.7 永久升级入口生成成功: ",
                        "Permanent 1.6.x/1.7 upgrade gateway generated: ") + output);
                return 0;
            } catch (Exception exception) {
                System.err.println(text(
                        "永久升级入口生成失败: ",
                        "Permanent upgrade gateway generation failed: ") + exception.getMessage());
                return 1;
            }
        }
        if (arguments.length >= 1 && arguments[0].equals("--publish-v5")) {
            if (arguments.length != 4) {
                printUsage();
                return 2;
            }
            try {
                PublisherProjectV5.Publication publication = PublisherProjectV5.publish(
                        Path.of(arguments[1]), Path.of(arguments[2]), Path.of(arguments[3]));
                System.out.println("MCSync v5 release generated: " + publication.manifestPath());
                return 0;
            } catch (Exception failure) {
                System.err.println("MCSync v5 release generation failed: " + failure.getMessage());
                return 1;
            }
        }
        if (arguments.length >= 1 && arguments[0].equals("--v5-template")) {
            if (arguments.length != 2) {
                printUsage();
                return 2;
            }
            try {
                PublisherProjectV5.writeTemplate(Path.of(arguments[1]));
                System.out.println("MCSync v5 publisher project template generated: " + arguments[1]);
                return 0;
            } catch (Exception failure) {
                System.err.println("Template generation failed: " + failure.getMessage());
                return 1;
            }
        }
        if (arguments.length >= 1 && arguments[0].equals("--serverlist")) {
            if (arguments.length < 2 || arguments.length > 3) {
                printUsage();
                return 2;
            }
            Path serversDat = Path.of(arguments[1]).toAbsolutePath().normalize();
            Path output = arguments.length == 3
                    ? Path.of(arguments[2]).toAbsolutePath().normalize()
                    : serversDat.getParent().resolve("serverlist.txt");
            try {
                generateServerList(serversDat, output);
                System.out.println(text("服务器列表清单生成成功: ", "Server-list manifest generated: ") + output);
                return 0;
            } catch (Exception exception) {
                System.err.println(text("服务器列表清单生成失败: ", "Failed to generate server-list manifest: ")
                        + exception.getMessage());
                return 1;
            }
        }
        if (arguments.length >= 1 && arguments[0].equals("--resourcepack")) {
            if (arguments.length < 2 || arguments.length > 3) {
                printUsage();
                return 2;
            }
            Path resourcePack = Path.of(arguments[1]).toAbsolutePath().normalize();
            Path output = arguments.length == 3
                    ? Path.of(arguments[2]).toAbsolutePath().normalize()
                    : resourcePack.getParent().resolve("resourcepacks.txt");
            try {
                generateResourcePack(resourcePack, output);
                System.out.println(text("资源包清单生成成功: ", "Resource-pack manifest generated: ") + output);
                return 0;
            } catch (Exception exception) {
                System.err.println(text("资源包清单生成失败: ", "Failed to generate resource-pack manifest: ")
                        + exception.getMessage());
                return 1;
            }
        }
        if (arguments.length < 1 || arguments.length > 2) {
            printUsage();
            return 2;
        }

        Path modsDirectory = Path.of(arguments[0]).toAbsolutePath().normalize();
        Path output = arguments.length == 2
                ? Path.of(arguments[1]).toAbsolutePath().normalize()
                : modsDirectory.resolve(ManagedClientConfig.MANIFEST_FILE_NAME);
        try {
            int count = generate(modsDirectory, output);
            System.out.println(text("生成成功，共 ", "Generated ") + count
                    + text(" 个 Mod: ", " mod(s): ") + output);
            return 0;
        } catch (Exception exception) {
            System.err.println(text("生成失败: ", "Generation failed: ") + exception.getMessage());
            return 1;
        }
    }

    private static int generate(Path modsDirectory, Path output) throws IOException {
        PublicationScan publication = preparePublication(modsDirectory);
        ModManifest manifest = completePublication(publication.scanned(), publication);
        try {
            manifest.ensureUniqueModIds();
        } catch (IllegalArgumentException exception) {
            throw new IOException(text(
                    "发布目录包含重复 Mod ID: ",
                    "The publishing directory contains duplicate mod IDs: ")
                    + exception.getMessage(), exception);
        }
        manifest.write(output);
        LegacyUpgradeManifest.write(manifest, modsDirectory.resolve(LegacyUpgradeManifest.DEFAULT_FILE_NAME));
        long withoutModId = manifest.entriesWithoutModId();
        if (withoutModId > 0) {
            System.err.println(text("警告：有 ", "Warning: ") + withoutModId
                    + text(
                            " 个 JAR 无法读取 Fabric/NeoForge 元数据中的 Mod ID，版本改名时将回退到文件名识别。",
                            " JAR(s) have no readable Fabric/NeoForge Mod ID; renamed versions will use filename matching."));
        }
        return manifest.entries().size();
    }

    private static PublicationScan preparePublication(Path modsDirectory) throws IOException {
        Path normalized = modsDirectory.toAbsolutePath().normalize();
        Path gameDirectory = normalized.getParent();
        if (gameDirectory == null) {
            throw new IOException("无法确定 mods 的游戏根目录: " + normalized);
        }
        Path configurationTemplate = gameDirectory.resolve("modsync.properties");
        ManagedClientConfig managedConfig = ManagedClientConfig.fromPropertiesFile(configurationTemplate);
        ManifestEntry bootstrapEntry = ManagedClientConfig.writeBootstrapJar(normalized, managedConfig);
        ModManifest scanned = ModManifest.scan(normalized, ManagedClientConfig.BOOTSTRAP_MOD_ID);
        scanned.ensureUniqueModIds();
        long syncTools = scanned.entries().stream()
                .filter(entry -> entry.modId().equals("mcmodsync"))
                .count();
        if (syncTools != 1) {
            throw new IOException("发布目录必须恰好包含一个当前 MCSync JAR（兼容 Mod ID: mcmodsync）");
        }
        return new PublicationScan(scanned, managedConfig, bootstrapEntry, configurationTemplate);
    }

    private static ModManifest completePublication(ModManifest edited, PublicationScan publication) {
        List<ManifestEntry> entries = new ArrayList<>(edited.entries().size() + 1);
        for (ManifestEntry entry : edited.entries()) {
            if (!entry.modId().equals(ManagedClientConfig.BOOTSTRAP_MOD_ID)) {
                entries.add(entry.modId().equals("mcmodsync") ? asRequired(entry) : entry);
            }
        }
        entries.add(publication.bootstrapEntry());
        return edited.withEntries(entries).withManagedClientConfig(publication.managedConfig());
    }

    private static ManifestEntry asRequired(ManifestEntry entry) {
        return new ManifestEntry(
                entry.sha256(),
                entry.md5(),
                entry.modId(),
                entry.fileName(),
                ModKind.REQUIRED,
                java.util.Set.of(),
                entry.displayName(),
                entry.version(),
                entry.descriptionZh(),
                entry.descriptionEn());
    }

    private static void generateResourcePack(Path resourcePack, Path output) throws IOException {
        ResourcePackManifest.fromFile(resourcePack).write(output);
    }

    private static void generateServerList(Path serversDat, Path output) throws IOException {
        ServerListManifest.fromFile(serversDat).write(output);
    }

    private static void showWindow() {
        try {
            UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName());
        } catch (Exception ignored) {
        }

        JFrame frame = new JFrame(text("MCSync 2.0 发布工作台", "MCSync 2.0 Publisher Workspace"));
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        frame.setSize(1180, 760);
        frame.setLocationRelativeTo(null);

        JPanel legacyPanel = new JPanel(new BorderLayout());

        JPanel form = new JPanel(new GridBagLayout());
        form.setBorder(BorderFactory.createEmptyBorder(16, 16, 8, 16));
        GridBagConstraints constraints = new GridBagConstraints();
        constraints.insets = new Insets(5, 5, 5, 5);
        constraints.fill = GridBagConstraints.HORIZONTAL;

        JTextField directoryField = new JTextField();
        JButton browseButton = new JButton(text("选择 mods 目录", "Choose mods directory"));
        JCheckBox loadPreviousCatalog = new JCheckBox(text(
                "扫描后选择上次清单", "Choose previous catalog after scanning"));
        loadPreviousCatalog.setToolTipText(text(
                "保留上次的分类、平台、名称和中英文描述，并更新当前 JAR 的哈希与版本",
                "Keep previous types, platforms, names and descriptions while refreshing current JAR hashes and versions"));
        JButton generateButton = new JButton(text(
                "编辑必须/推荐模组并生成清单", "Edit required/recommended mods and generate catalog"));
        JButton resourcePackButton = new JButton(text(
                "为资源包生成 resourcepacks.txt…", "Generate resourcepacks.txt…"));
        JButton serverListButton = new JButton(text(
                "为服务器列表生成 serverlist.txt…", "Generate serverlist.txt…"));
        JTextArea log = new JTextArea();
        log.setEditable(false);
        log.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 13));
        log.setLineWrap(true);
        log.setWrapStyleWord(true);
        log.setText(text(
                "选择测试完成的客户端 mods 目录。游戏根目录必须有发布用 modsync.properties。\n"
                        + "工具会生成正式 mods-v4.txt、仅含两个升级组件的旧版入口 mods.txt 和配置引导 JAR。\n",
                "Choose a tested client mods directory. A publishing modsync.properties must exist in the game root.\n"
                        + "The tool generates mods-v4.txt, an upgrade-components-only legacy mods.txt gateway, and a configuration bootstrap JAR.\n"));

        constraints.gridx = 0;
        constraints.gridy = 0;
        constraints.weightx = 0;
        form.add(new JLabel(text("Mod 目录：", "Mods directory:")), constraints);
        constraints.gridx = 1;
        constraints.weightx = 1;
        form.add(directoryField, constraints);
        constraints.gridx = 2;
        constraints.weightx = 0;
        form.add(browseButton, constraints);

        constraints.gridx = 1;
        constraints.gridy = 1;
        constraints.gridwidth = 2;
        constraints.weightx = 1;
        form.add(loadPreviousCatalog, constraints);

        JPanel actions = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        actions.add(serverListButton);
        actions.add(resourcePackButton);
        actions.add(generateButton);
        constraints.gridx = 0;
        constraints.gridy = 2;
        constraints.gridwidth = 3;
        constraints.weightx = 1;
        form.add(actions, constraints);

        legacyPanel.add(form, BorderLayout.NORTH);
        JScrollPane scroll = new JScrollPane(log);
        scroll.setBorder(BorderFactory.createTitledBorder(text("结果", "Results")));
        legacyPanel.add(scroll, BorderLayout.CENTER);

        browseButton.addActionListener(event -> {
            JFileChooser chooser = new JFileChooser();
            chooser.setDialogTitle(text("选择测试客户端的 mods 目录", "Choose a tested client mods directory"));
            chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY);
            chooser.setAcceptAllFileFilterUsed(false);
            if (!directoryField.getText().isBlank()) {
                chooser.setCurrentDirectory(Path.of(directoryField.getText()).toFile());
            }
            if (chooser.showOpenDialog(frame) == JFileChooser.APPROVE_OPTION) {
                directoryField.setText(chooser.getSelectedFile().toPath().toAbsolutePath().normalize().toString());
            }
        });

        generateButton.addActionListener(event -> {
            if (directoryField.getText().isBlank()) {
                JOptionPane.showMessageDialog(
                        frame,
                        text("请先选择 mods 目录。", "Choose a mods directory first."),
                        text("缺少目录", "Missing directory"),
                        JOptionPane.WARNING_MESSAGE);
                return;
            }
            Path modsDirectory;
            try {
                modsDirectory = Path.of(directoryField.getText()).toAbsolutePath().normalize();
            } catch (Exception exception) {
                JOptionPane.showMessageDialog(
                        frame,
                        text("目录格式无效。", "The directory path is invalid."),
                        text("错误", "Error"),
                        JOptionPane.ERROR_MESSAGE);
                return;
            }
            Path output = modsDirectory.resolve(ManagedClientConfig.MANIFEST_FILE_NAME);
            boolean choosePreviousCatalog = loadPreviousCatalog.isSelected();
            generateButton.setEnabled(false);
            loadPreviousCatalog.setEnabled(false);
            log.append(text(
                    "\n开始读取 Mod 信息并计算 MD5/SHA256：",
                    "\nReading mod metadata and calculating MD5/SHA256: ") + modsDirectory + "\n");
            new SwingWorker<PublicationScan, Void>() {
                @Override
                protected PublicationScan doInBackground() throws Exception {
                    return preparePublication(modsDirectory);
                }

                @Override
                protected void done() {
                    generateButton.setEnabled(true);
                    loadPreviousCatalog.setEnabled(true);
                    try {
                        PublicationScan publication = get();
                        log.append(text("发布配置模板：", "Publishing configuration template: ")
                                + publication.configurationTemplate() + "\n");
                        ModManifest scanned = publication.scanned();
                        if (choosePreviousCatalog) {
                            Optional<Path> previousPath = choosePreviousCatalog(frame, modsDirectory);
                            if (previousPath.isEmpty()) {
                                log.append(text(
                                        "已取消选择上次清单。\n",
                                        "Previous catalog selection cancelled.\n"));
                                return;
                            }
                            ModManifest previous = readPreviousCatalog(previousPath.get());
                            scanned = mergeCatalog(scanned, previous);
                            log.append(text(
                                    "已加载并合并上次清单：",
                                    "Loaded and merged previous catalog: ") + previousPath.get() + "\n");
                        } else {
                            scanned = mergeExistingCatalog(scanned, output);
                        }
                        long missingChinese = scanned.entries().stream()
                                .filter(entry -> entry.descriptionZh().isBlank())
                                .count();
                        if (missingChinese > 0) {
                            log.append(text(
                                    "有 " + missingChinese + " 个 Mod 的 JAR 未提供中文描述；请人工填写，或从上次清单继续编辑。\n",
                                    missingChinese + " mod(s) have no Chinese description in their JAR metadata; fill them manually or continue from a previous catalog.\n"));
                        }
                        var edited = CatalogEditorDialog.edit(frame, scanned);
                        if (edited.isEmpty()) {
                            log.append(text("已取消生成 Mod 清单。\n", "Mod catalog generation cancelled.\n"));
                            return;
                        }
                        ModManifest completed = completePublication(edited.get(), publication);
                        completed.ensureUniqueModIds();
                        completed.write(output);
                        Path upgradeOutput = modsDirectory.resolve(LegacyUpgradeManifest.DEFAULT_FILE_NAME);
                        LegacyUpgradeManifest.write(completed, upgradeOutput);
                        log.append(text(
                                "1.6.x/1.7 永久升级入口：",
                                "Permanent 1.6.x/1.7 upgrade gateway: ") + upgradeOutput + "\n");
                        String upgradeNotice = text(
                                "\n\nmods.txt 只包含 MCSync 与兼容配置引导 JAR。旧版升级后会切换到结构化发布清单。",
                                "\n\nmods.txt contains only MCSync and the compatibility bootstrap JAR. Upgraded clients switch to the structured release manifest.");
                        int count = completed.entries().size();
                        log.append(text("完成，共 ", "Completed: ") + count
                                + text(" 个 Mod。\n清单：", " mod(s).\nCatalog: ") + output + "\n");
                        Object[] options = Desktop.isDesktopSupported()
                                ? new Object[]{text("打开所在目录", "Open directory"), text("关闭", "Close")}
                                : new Object[]{text("关闭", "Close")};
                        int choice = JOptionPane.showOptionDialog(
                                frame,
                                text("正式 mods-v4.txt 已生成，共 ", "The production mods-v4.txt was generated with ") + count
                                        + text(
                                                " 个 Mod。\n已包含 MD5、SHA256、必须/推荐分类、平台兼容和中英文描述。",
                                                " mod(s).\nIncludes MD5, SHA256, required/recommended types, platform compatibility, and Chinese/English descriptions.")
                                        + upgradeNotice,
                                text("生成成功", "Generation complete"),
                                JOptionPane.DEFAULT_OPTION,
                                JOptionPane.INFORMATION_MESSAGE,
                                null,
                                options,
                                options[0]);
                        if (choice == 0 && Desktop.isDesktopSupported()) {
                            try {
                                Desktop.getDesktop().open(modsDirectory.toFile());
                            } catch (IOException exception) {
                                log.append(text("无法打开目录：", "Unable to open directory: ")
                                        + exception.getMessage() + "\n");
                            }
                        }
                    } catch (Exception exception) {
                        Throwable cause = exception.getCause() == null ? exception : exception.getCause();
                        log.append(text("失败：", "Failed: ") + cause.getMessage() + "\n");
                        JOptionPane.showMessageDialog(
                                frame,
                                cause.getMessage(),
                                text("生成失败", "Generation failed"),
                                JOptionPane.ERROR_MESSAGE);
                    }
                }
            }.execute();
        });

        resourcePackButton.addActionListener(event -> {
            JFileChooser chooser = new JFileChooser();
            chooser.setDialogTitle(text("选择要发布的资源包 ZIP", "Choose a resource-pack ZIP to publish"));
            chooser.setFileSelectionMode(JFileChooser.FILES_ONLY);
            chooser.setAcceptAllFileFilterUsed(false);
            chooser.setFileFilter(new FileNameExtensionFilter(text(
                    "Minecraft 资源包 (*.zip)", "Minecraft resource pack (*.zip)"), "zip"));
            if (chooser.showOpenDialog(frame) != JFileChooser.APPROVE_OPTION) {
                return;
            }
            Path resourcePack = chooser.getSelectedFile().toPath().toAbsolutePath().normalize();
            Path output = resourcePack.getParent().resolve("resourcepacks.txt");
            resourcePackButton.setEnabled(false);
            log.append(text("\n开始计算资源包 MD5：", "\nCalculating resource-pack MD5: ")
                    + resourcePack + "\n");
            new SwingWorker<Void, Void>() {
                @Override
                protected Void doInBackground() throws Exception {
                    generateResourcePack(resourcePack, output);
                    return null;
                }

                @Override
                protected void done() {
                    resourcePackButton.setEnabled(true);
                    try {
                        get();
                        log.append(text("资源包清单完成：", "Resource-pack manifest completed: ") + output + "\n");
                        Object[] options = Desktop.isDesktopSupported()
                                ? new Object[]{text("打开所在目录", "Open directory"), text("关闭", "Close")}
                                : new Object[]{text("关闭", "Close")};
                        int choice = JOptionPane.showOptionDialog(
                                frame,
                                text(
                                        "resourcepacks.txt 已生成。\n请把它和资源包 ZIP 上传到同一云端目录。",
                                        "resourcepacks.txt was generated.\nUpload it and the resource-pack ZIP to the same cloud directory."),
                                text("资源包清单生成成功", "Resource-pack manifest generated"),
                                JOptionPane.DEFAULT_OPTION,
                                JOptionPane.INFORMATION_MESSAGE,
                                null,
                                options,
                                options[0]);
                        if (choice == 0 && Desktop.isDesktopSupported()) {
                            Desktop.getDesktop().open(resourcePack.getParent().toFile());
                        }
                    } catch (Exception exception) {
                        Throwable cause = exception.getCause() == null ? exception : exception.getCause();
                        log.append(text("资源包清单失败：", "Resource-pack manifest failed: ")
                                + cause.getMessage() + "\n");
                        JOptionPane.showMessageDialog(
                                frame,
                                cause.getMessage(),
                                text("资源包清单生成失败", "Resource-pack manifest generation failed"),
                                JOptionPane.ERROR_MESSAGE);
                    }
                }
            }.execute();
        });

        serverListButton.addActionListener(event -> {
            JFileChooser chooser = new JFileChooser();
            chooser.setDialogTitle(text("选择测试客户端的 servers.dat", "Choose a tested client's servers.dat"));
            chooser.setFileSelectionMode(JFileChooser.FILES_ONLY);
            chooser.setAcceptAllFileFilterUsed(true);
            if (chooser.showOpenDialog(frame) != JFileChooser.APPROVE_OPTION) {
                return;
            }
            Path serversDat = chooser.getSelectedFile().toPath().toAbsolutePath().normalize();
            Path output = serversDat.getParent().resolve("serverlist.txt");
            serverListButton.setEnabled(false);
            log.append(text("\n开始计算服务器列表 MD5：", "\nCalculating server-list MD5: ")
                    + serversDat + "\n");
            new SwingWorker<Void, Void>() {
                @Override
                protected Void doInBackground() throws Exception {
                    generateServerList(serversDat, output);
                    return null;
                }

                @Override
                protected void done() {
                    serverListButton.setEnabled(true);
                    try {
                        get();
                        log.append(text("服务器列表清单完成：", "Server-list manifest completed: ") + output + "\n");
                        Object[] options = Desktop.isDesktopSupported()
                                ? new Object[]{text("打开所在目录", "Open directory"), text("关闭", "Close")}
                                : new Object[]{text("关闭", "Close")};
                        int choice = JOptionPane.showOptionDialog(
                                frame,
                                text(
                                        "serverlist.txt 已生成。\n请把它和 servers.dat 上传到同一云端目录。",
                                        "serverlist.txt was generated.\nUpload it and servers.dat to the same cloud directory."),
                                text("服务器列表清单生成成功", "Server-list manifest generated"),
                                JOptionPane.DEFAULT_OPTION,
                                JOptionPane.INFORMATION_MESSAGE,
                                null,
                                options,
                                options[0]);
                        if (choice == 0 && Desktop.isDesktopSupported()) {
                            Desktop.getDesktop().open(serversDat.getParent().toFile());
                        }
                    } catch (Exception exception) {
                        Throwable cause = exception.getCause() == null ? exception : exception.getCause();
                        log.append(text("服务器列表清单失败：", "Server-list manifest failed: ")
                                + cause.getMessage() + "\n");
                        JOptionPane.showMessageDialog(
                                frame,
                                cause.getMessage(),
                                text("服务器列表清单生成失败", "Server-list manifest generation failed"),
                                JOptionPane.ERROR_MESSAGE);
                    }
                }
            }.execute();
        });

        JTabbedPane publisherTabs = new JTabbedPane();
        publisherTabs.addTab(text("2.0 OTA 发布", "2.0 OTA publisher"), V5PublisherWorkspace.create(frame));
        publisherTabs.addTab(text("1.9.x 兼容工具", "1.9.x compatibility tools"), legacyPanel);
        frame.add(publisherTabs, BorderLayout.CENTER);
        frame.setVisible(true);
    }

    private static ModManifest mergeExistingCatalog(ModManifest scanned, Path output) {
        if (!Files.isRegularFile(output)) {
            return scanned;
        }
        try {
            return mergeCatalog(scanned, readPreviousCatalog(output));
        } catch (IOException | IllegalArgumentException exception) {
            return scanned;
        }
    }

    private static Optional<Path> choosePreviousCatalog(JFrame owner, Path modsDirectory) {
        JFileChooser chooser = new JFileChooser();
        chooser.setDialogTitle(text("选择上次发布的 Mod 清单", "Choose the previously published mod catalog"));
        chooser.setFileSelectionMode(JFileChooser.FILES_ONLY);
        chooser.setAcceptAllFileFilterUsed(false);
        chooser.setFileFilter(new FileNameExtensionFilter(text(
                "MCSync 清单 (*.txt)", "MCSync catalog (*.txt)"), "txt"));
        chooser.setCurrentDirectory(modsDirectory.toFile());
        if (chooser.showOpenDialog(owner) != JFileChooser.APPROVE_OPTION) {
            return Optional.empty();
        }
        return Optional.of(chooser.getSelectedFile().toPath().toAbsolutePath().normalize());
    }

    private static ModManifest readPreviousCatalog(Path path) throws IOException {
        ModManifest previous;
        try {
            previous = ModManifest.parse(Files.readString(path, StandardCharsets.UTF_8));
            previous.ensureUniqueModIds();
        } catch (IllegalArgumentException exception) {
            throw new IOException(text(
                    "上次清单无效：", "The previous catalog is invalid: ") + exception.getMessage(), exception);
        }
        if (!previous.supportsRecommendations()) {
            throw new IOException(text(
                    "只能继续编辑 v3 或 v4 清单；v1/v2 没有必须/推荐与双语字段。",
                    "Only v3 or v4 catalogs can be continued; v1/v2 have no required/recommended or bilingual fields."));
        }
        return previous;
    }

    static ModManifest mergeCatalog(ModManifest scanned, ModManifest previous) {
        if (!previous.supportsRecommendations()) {
            throw new IllegalArgumentException("Previous catalog must be v3 or v4");
        }
        Map<String, ManifestEntry> byId = new HashMap<>();
        Map<String, ManifestEntry> byName = new HashMap<>();
        for (ManifestEntry entry : previous.entries()) {
            if (!entry.modId().isBlank()) {
                byId.put(entry.modId(), entry);
            }
            byName.put(entry.fileName().toLowerCase(java.util.Locale.ROOT), entry);
        }
        var merged = scanned.entries().stream().map(current -> {
            ManifestEntry old = !current.modId().isBlank()
                    ? byId.get(current.modId())
                    : byName.get(current.fileName().toLowerCase(java.util.Locale.ROOT));
            if (old == null) {
                return current;
            }
            return new ManifestEntry(
                    current.sha256(),
                    current.md5(),
                    current.modId(),
                    current.fileName(),
                    old.kind(),
                    old.incompatiblePlatforms(),
                    old.displayName(),
                    current.version().isBlank() ? old.version() : current.version(),
                    old.descriptionZh().isBlank() ? current.descriptionZh() : old.descriptionZh(),
                    old.descriptionEn().isBlank() ? current.descriptionEn() : old.descriptionEn());
        }).toList();
        return ModManifest.fromEntries(previous.catalogVersion(), merged);
    }

    private static void printUsage() {
        System.out.println(text("用法：", "Usage:"));
        System.out.println(text("  双击 JAR：打开图形界面", "  Double-click the JAR to open the GUI"));
        System.out.println(text(
                "  java -jar MCSync.jar <mods目录> [mods-v4.txt输出路径]",
                "  java -jar MCSync.jar <mods-directory> [mods-v4.txt-output]"));
        System.out.println(text(
                "  java -jar MCSync.jar --resourcepack <资源包.zip> [resourcepacks.txt输出路径]",
                "  java -jar MCSync.jar --resourcepack <resource-pack.zip> [resourcepacks.txt-output]"));
        System.out.println(text(
                "  java -jar MCSync.jar --serverlist <servers.dat> [serverlist.txt输出路径]",
                "  java -jar MCSync.jar --serverlist <servers.dat> [serverlist.txt-output]"));
        System.out.println(text(
                "  java -jar MCSync.jar --upgrade-v2 <mods目录> [mods.txt输出路径]",
                "  java -jar MCSync.jar --upgrade-v2 <mods-directory> [mods.txt-output]"));
        System.out.println(text(
                "  java -jar MCSync.jar --v5-template <项目JSON输出路径>",
                "  java -jar MCSync.jar --v5-template <publisher-project-json-output>"));
        System.out.println(text(
                "  java -jar MCSync.jar --publish-v5 <游戏根目录> <项目JSON> <空输出目录>",
                "  java -jar MCSync.jar --publish-v5 <game-root> <project-json> <empty-output-directory>"));
        System.out.println(text(
                "  语言：-Dmodsync.language=zh_cn 或 -Dmodsync.language=en_us",
                "  Language: -Dmodsync.language=zh_cn or -Dmodsync.language=en_us"));
    }

    private static String text(String chinese, String english) {
        return LANGUAGE.text(chinese, english);
    }

    private record PublicationScan(
            ModManifest scanned,
            ManagedClientConfig managedConfig,
            ManifestEntry bootstrapEntry,
            Path configurationTemplate) {
    }
}
