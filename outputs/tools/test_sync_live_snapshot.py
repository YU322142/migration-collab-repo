from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sync_live_snapshot as sync


class SyncLiveSnapshotTests(unittest.TestCase):
    def make_source(self, root: Path) -> None:
        (root / "world" / "region").mkdir(parents=True)
        (root / "config").mkdir()
        (root / "world" / "region" / "r.0.0.mca").write_bytes(b"region-v1")
        (root / "config" / "known.json").write_bytes(b"config-v1")
        (root / "server.properties").write_text("online-mode=true\n", encoding="utf-8")
        (root / "world" / "session.lock").write_bytes(b"volatile")
        (root / "ledger.sqlite").write_bytes(b"excluded")

    def test_preheat_copies_only_audited_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "remote"
            mirror = base / "mirror"
            report = base / "preheat.json"
            self.make_source(source)
            result = sync.preheat(source, mirror, report)
            self.assertEqual(result["status"], "PREHEATED")
            self.assertTrue((mirror / "world" / "region" / "r.0.0.mca").is_file())
            self.assertFalse((mirror / "world" / "session.lock").exists())
            self.assertFalse((mirror / "ledger.sqlite").exists())
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["copied"], 3)

    def test_refresh_changes_are_transactional_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "remote"
            mirror = base / "mirror"
            self.make_source(source)
            sync.preheat(source, mirror, base / "preheat.json")
            (source / "world" / "region" / "r.0.0.mca").write_bytes(b"region-v2")
            (source / "world" / "entities").mkdir()
            (source / "world" / "entities" / "r.0.0.mca").write_bytes(b"entities")
            # A test source has no held session.lock, so the stopped probe passes.
            result = sync.refresh(source, mirror, base / "refresh.json")
            self.assertEqual(result["status"], "READY_FOR_STAGING_REFRESH")
            self.assertEqual((mirror / "world" / "region" / "r.0.0.mca").read_bytes(), b"region-v2")
            self.assertTrue((mirror / "world" / "entities" / "r.0.0.mca").is_file())
            self.assertEqual(result["source_snapshot"]["snapshot_sha256"], result["mirror_snapshot"]["snapshot_sha256"])

    def test_source_deletion_blocks_without_modifying_mirror(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "remote"
            mirror = base / "mirror"
            self.make_source(source)
            sync.preheat(source, mirror, base / "preheat.json")
            (source / "config" / "known.json").unlink()
            with self.assertRaises(sync.SnapshotError):
                sync.refresh(source, mirror, base / "refresh.json")
            self.assertTrue((mirror / "config" / "known.json").is_file())
            report = json.loads((base / "refresh.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "BLOCKED_SOURCE_DELETIONS")

    def test_existing_mirror_is_not_overwritten_by_preheat(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "remote"
            mirror = base / "mirror"
            self.make_source(source)
            mirror.mkdir()
            with self.assertRaises(sync.SnapshotError):
                sync.preheat(source, mirror, base / "preheat.json")


if __name__ == "__main__":
    unittest.main()
