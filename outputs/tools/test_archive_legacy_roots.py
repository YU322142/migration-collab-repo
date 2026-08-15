from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import archive_legacy_roots as archive


class ArchiveLegacyRootsTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        for name in archive.LEGACY_ROOTS:
            legacy = self.source / name
            (legacy / "region").mkdir(parents=True)
            (legacy / "empty").mkdir()
            (legacy / "level.dat").write_bytes((name + "-level").encode("ascii"))
            (legacy / "region" / "r.0.0.mca").write_bytes((name + "-region").encode("ascii"))
        self.audit = self.root / "legacy-audit.md"
        self.audit.write_text("audit\n", encoding="utf-8")
        self.output = self.root / "archives"
        self.marker = self.output / "legacy-policy-pass.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_archives_are_deterministic_and_match_both_source_trees(self) -> None:
        first = archive.build_archives(self.source, self.output, self.audit, self.marker)
        first_archives = {
            name: Path(row["path"]).read_bytes()
            for name, row in first["archives"].items()
        }
        second = archive.build_archives(self.source, self.output, self.audit, self.marker)
        marker = json.loads(self.marker.read_text(encoding="utf-8"))

        self.assertEqual(marker["decision"], archive.DECISION)
        self.assertFalse(marker["merge_into_canonical"])
        self.assertEqual(set(marker["archives"]), set(archive.LEGACY_ROOTS))
        for name in archive.LEGACY_ROOTS:
            row = second["archives"][name]
            path = Path(row["path"])
            self.assertEqual(path.read_bytes(), first_archives[name])
            self.assertEqual(
                archive.scan_tree(self.source / name)["tree_sha256"],
                archive.scan_archive(path)["tree_sha256"],
            )

    def test_output_or_marker_overlapping_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(archive.ArchiveError, "must not overlap"):
            archive.build_archives(
                self.source,
                self.source / "archives",
                self.audit,
                self.source / "archives" / "marker.json",
            )
        outside = self.root / "outside"
        with self.assertRaisesRegex(archive.ArchiveError, "inside the archive output"):
            archive.build_archives(
                self.source,
                outside,
                self.audit,
                self.root / "marker.json",
            )

    def test_source_change_during_archive_blocks_marker(self) -> None:
        real_scan = archive.scan_tree
        calls = {name: 0 for name in archive.LEGACY_ROOTS}

        def changing_scan(path: Path):
            name = path.name
            calls[name] += 1
            value = real_scan(path)
            if name == "world_nether" and calls[name] == 2:
                (path / "level.dat").write_bytes(b"changed")
                value = real_scan(path)
            return value

        with mock.patch.object(archive, "scan_tree", side_effect=changing_scan):
            with self.assertRaisesRegex(archive.ArchiveError, "changed while"):
                archive.build_archives(self.source, self.output, self.audit, self.marker)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
