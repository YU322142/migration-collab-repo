package io.github.mcmodsync;

import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JDialog;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JTable;
import javax.swing.JTextField;
import javax.swing.ListSelectionModel;
import javax.swing.WindowConstants;
import javax.swing.table.DefaultTableModel;
import java.awt.BorderLayout;
import java.awt.Dimension;
import java.awt.FlowLayout;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

final class CatalogEditorDialog {
    static final int FILE_COLUMN = 0;
    static final int REQUIRED_COLUMN = 1;
    static final int RECOMMENDED_COLUMN = 2;
    static final int NAME_COLUMN = 3;
    static final int VERSION_COLUMN = 4;
    static final int WINDOWS_COLUMN = 5;
    static final int MAC_COLUMN = 6;
    static final int LINUX_COLUMN = 7;
    static final int MOBILE_COLUMN = 8;
    static final int DESCRIPTION_ZH_COLUMN = 9;
    static final int DESCRIPTION_EN_COLUMN = 10;

    private static final String[] COLUMNS = {
            "文件名 / File",
            "必须 / Required",
            "推荐 / Recommended",
            "显示名称 / Display name",
            "版本 / Version",
            "Windows 不兼容",
            "Mac 不兼容",
            "Linux 不兼容",
            "手机不兼容 / Mobile",
            "中文描述",
            "English description"
    };

    private CatalogEditorDialog() {
    }

    static Optional<ModManifest> edit(JFrame owner, ModManifest scanned) {
        CatalogTableModel model = new CatalogTableModel();
        for (ManifestEntry entry : scanned.entries()) {
            model.addRow(new Object[]{
                    entry.fileName(),
                    entry.kind() == ModKind.REQUIRED,
                    entry.kind() == ModKind.RECOMMENDED,
                    entry.displayName(),
                    entry.version(),
                    entry.incompatiblePlatforms().contains(ClientPlatform.WINDOWS),
                    entry.incompatiblePlatforms().contains(ClientPlatform.MAC),
                    entry.incompatiblePlatforms().contains(ClientPlatform.LINUX),
                    entry.incompatiblePlatforms().contains(ClientPlatform.MOBILE),
                    entry.descriptionZh(),
                    entry.descriptionEn()
            });
        }

        JTable table = new JTable(model);
        table.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION);
        table.setAutoResizeMode(JTable.AUTO_RESIZE_OFF);
        table.setRowHeight(26);
        table.putClientProperty("terminateEditOnFocusLost", Boolean.TRUE);
        int[] widths = {220, 125, 145, 180, 100, 125, 105, 115, 145, 360, 360};
        for (int index = 0; index < widths.length; index++) {
            table.getColumnModel().getColumn(index).setPreferredWidth(widths[index]);
        }

        JTextField versionField = new JTextField(scanned.catalogVersion(), 24);
        JPanel heading = new JPanel(new FlowLayout(FlowLayout.LEFT));
        heading.setBorder(BorderFactory.createEmptyBorder(8, 8, 4, 8));
        heading.add(new JLabel("推荐清单版本 / Catalog version:"));
        heading.add(versionField);
        heading.add(new JLabel(
                "每行必须二选一；不兼容平台仅适用于推荐模组。 / Choose exactly one type per row."));

        JButton allRequired = new JButton("所选设为必须 / Set selected required");
        JButton allRecommended = new JButton("所选设为推荐 / Set selected recommended");
        JButton generate = new JButton("生成 v4 清单 / Generate v4");
        JButton cancel = new JButton("取消 / Cancel");
        JPanel actions = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        actions.add(allRequired);
        actions.add(allRecommended);
        actions.add(cancel);
        actions.add(generate);

        JDialog dialog = new JDialog(
                owner,
                "MCSync 发布文件编辑器 · Release File Editor",
                true);
        dialog.setDefaultCloseOperation(WindowConstants.DO_NOTHING_ON_CLOSE);
        dialog.add(heading, BorderLayout.NORTH);
        JScrollPane scroll = new JScrollPane(table);
        scroll.setPreferredSize(new Dimension(1_450, 620));
        dialog.add(scroll, BorderLayout.CENTER);
        dialog.add(actions, BorderLayout.SOUTH);
        dialog.pack();
        dialog.setLocationRelativeTo(owner);

        AtomicReference<ModManifest> result = new AtomicReference<>();
        allRequired.addActionListener(event -> setSelectedType(table, model, ModKind.REQUIRED));
        allRecommended.addActionListener(event -> setSelectedType(table, model, ModKind.RECOMMENDED));
        cancel.addActionListener(event -> dialog.dispose());
        generate.addActionListener(event -> {
            if (table.isEditing()) {
                table.getCellEditor().stopCellEditing();
            }
            try {
                List<ManifestEntry> edited = new ArrayList<>();
                for (int row = 0; row < model.getRowCount(); row++) {
                    ManifestEntry source = scanned.entries().get(row);
                    ModKind kind = model.kindAt(row);
                    EnumSet<ClientPlatform> incompatible = EnumSet.noneOf(ClientPlatform.class);
                    if (kind == ModKind.RECOMMENDED) {
                        if (bool(model, row, WINDOWS_COLUMN)) incompatible.add(ClientPlatform.WINDOWS);
                        if (bool(model, row, MAC_COLUMN)) incompatible.add(ClientPlatform.MAC);
                        if (bool(model, row, LINUX_COLUMN)) incompatible.add(ClientPlatform.LINUX);
                        if (bool(model, row, MOBILE_COLUMN)) incompatible.add(ClientPlatform.MOBILE);
                    }
                    edited.add(new ManifestEntry(
                            source.sha256(),
                            source.md5(),
                            source.modId(),
                            source.fileName(),
                            kind,
                            Set.copyOf(incompatible),
                            string(model, row, NAME_COLUMN),
                            string(model, row, VERSION_COLUMN),
                            string(model, row, DESCRIPTION_ZH_COLUMN),
                            string(model, row, DESCRIPTION_EN_COLUMN)));
                }
                ModManifest manifest = ModManifest.fromEntries(versionField.getText(), edited);
                manifest.ensureUniqueModIds();
                result.set(manifest);
                dialog.dispose();
            } catch (RuntimeException exception) {
                JOptionPane.showMessageDialog(
                        dialog,
                        exception.getMessage(),
                        "清单内容无效 / Invalid catalog",
                        JOptionPane.ERROR_MESSAGE);
            }
        });
        dialog.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosing(WindowEvent event) {
                dialog.dispose();
            }
        });
        dialog.setVisible(true);
        return Optional.ofNullable(result.get());
    }

    private static void setSelectedType(JTable table, CatalogTableModel model, ModKind kind) {
        int[] selected = table.getSelectedRows();
        if (selected.length == 0) {
            for (int row = 0; row < model.getRowCount(); row++) {
                model.setKind(row, kind);
            }
            return;
        }
        for (int viewRow : selected) {
            model.setKind(table.convertRowIndexToModel(viewRow), kind);
        }
    }

    private static String string(DefaultTableModel model, int row, int column) {
        Object value = model.getValueAt(row, column);
        return value == null ? "" : value.toString();
    }

    private static boolean bool(DefaultTableModel model, int row, int column) {
        return Boolean.TRUE.equals(model.getValueAt(row, column));
    }

    static final class CatalogTableModel extends DefaultTableModel {
        CatalogTableModel() {
            super(COLUMNS, 0);
        }

        @Override
        public boolean isCellEditable(int row, int column) {
            if (column == FILE_COLUMN) {
                return false;
            }
            if (column >= WINDOWS_COLUMN && column <= MOBILE_COLUMN) {
                return kindAt(row) == ModKind.RECOMMENDED;
            }
            return true;
        }

        @Override
        public Class<?> getColumnClass(int column) {
            return column == REQUIRED_COLUMN
                    || column == RECOMMENDED_COLUMN
                    || (column >= WINDOWS_COLUMN && column <= MOBILE_COLUMN)
                    ? Boolean.class
                    : String.class;
        }

        @Override
        public void setValueAt(Object value, int row, int column) {
            if (column != REQUIRED_COLUMN && column != RECOMMENDED_COLUMN) {
                super.setValueAt(value, row, column);
                return;
            }
            int other = column == REQUIRED_COLUMN ? RECOMMENDED_COLUMN : REQUIRED_COLUMN;
            boolean checked = Boolean.TRUE.equals(value);
            super.setValueAt(checked, row, column);
            super.setValueAt(!checked, row, other);
            if (kindAt(row) == ModKind.REQUIRED) {
                for (int platform = WINDOWS_COLUMN; platform <= MOBILE_COLUMN; platform++) {
                    super.setValueAt(Boolean.FALSE, row, platform);
                }
            }
            fireTableRowsUpdated(row, row);
        }

        ModKind kindAt(int row) {
            return Boolean.TRUE.equals(getValueAt(row, RECOMMENDED_COLUMN))
                    ? ModKind.RECOMMENDED
                    : ModKind.REQUIRED;
        }

        void setKind(int row, ModKind kind) {
            setValueAt(Boolean.TRUE, row,
                    kind == ModKind.REQUIRED ? REQUIRED_COLUMN : RECOMMENDED_COLUMN);
        }
    }
}
