from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("prepare_cutover_delta.py")
SPEC = importlib.util.spec_from_file_location("prepare_cutover_delta", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
delta = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(delta)


class CutoverDeltaTest(unittest.TestCase):
    def d_temp(self):
        root = Path(os.environ.get("MIGRATION_TEST_TMP", r"<AUDIT_ROOT>\tmp"))
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def make_source(self, root: Path) -> Path:
        source = root / "source"
        (source / "world" / "region").mkdir(parents=True)
        (source / "world" / "data").mkdir()
        (source / "config").mkdir()
        (source / "EasyAuth").mkdir()
        (source / "world" / "region" / "r.0.0.mca").write_bytes(b"region-v1")
        (source / "world" / "ledger.sqlite").write_bytes(b"ledger")
        (source / "world" / "session.lock").write_bytes(b"lock")
        (source / "config" / "mineastr-common.json").write_text("{}", encoding="ascii")
        (source / "EasyAuth" / "easyauth.db").write_bytes(b"auth")
        (source / "server.properties").write_text("online-mode=true\n", encoding="ascii")
        return source

    def test_snapshot_excludes_volatile_and_maps_auth(self):
        with self.d_temp() as temporary:
            source = self.make_source(Path(temporary))
            value = delta.exact_snapshot(source)
            self.assertNotIn("world/ledger.sqlite", value["files"])
            self.assertNotIn("world/session.lock", value["files"])
            self.assertEqual(
                value["files"]["EasyAuth/easyauth.db"]["target"],
                "migration-input/EasyAuth/easyauth.db",
            )

    def test_diff_uses_content_hash_not_size(self):
        with self.d_temp() as temporary:
            source = self.make_source(Path(temporary))
            before = delta.exact_snapshot(source)
            region = source / "world" / "region" / "r.0.0.mca"
            region.write_bytes(b"region-v2")
            after = delta.exact_snapshot(source)
            result = delta.snapshot_diff(before, after)
            self.assertEqual(result["changed"], ["world/region/r.0.0.mca"])

    def test_deleted_and_unknown_config_are_blockers(self):
        with self.assertRaisesRegex(RuntimeError, "deleted"):
            delta.validate_delta({"deleted": ["world/a"], "added": [], "changed": []})
        with self.assertRaisesRegex(RuntimeError, "no audited automatic mapping"):
            delta.validate_delta(
                {"deleted": [], "added": [], "changed": ["config/unknown.toml"]}
            )
        delta.validate_delta(
            {
                "deleted": [],
                "added": [],
                "changed": ["config/mineastr-common.json"],
            }
        )
        with self.assertRaisesRegex(RuntimeError, "SavedData"):
            delta.validate_delta(
                {
                    "deleted": [],
                    "added": [],
                    "changed": ["world/data/unknown.dat"],
                }
            )

    def test_atomic_copy_checks_payload(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            source = root / "source.bin"
            target = root / "nested" / "target.bin"
            source.write_bytes(b"payload")
            delta.atomic_copy(source, target)
            self.assertEqual(target.read_bytes(), b"payload")
            self.assertFalse(target.with_name(target.name + ".cutover.tmp").exists())

    def test_transaction_restore_recovers_existing_and_removes_new(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            existing = staging / "world" / "level.dat"
            created = staging / "world" / "new.dat"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"before")
            transaction = root / "transaction"
            manifest = delta.backup_targets(
                staging, [existing, created], transaction
            )
            existing.write_bytes(b"after")
            created.write_bytes(b"created")
            delta.restore_targets(staging, transaction, manifest)
            self.assertEqual(existing.read_bytes(), b"before")
            self.assertFalse(created.exists())
            self.assertTrue((transaction / "rollback-complete.json").is_file())

    @unittest.skipUnless(os.name == "nt", "Windows session lock probe")
    def test_unlocked_session_file_is_accepted_read_only(self):
        with self.d_temp() as temporary:
            source = Path(temporary) / "source"
            lock = source / "world" / "session.lock"
            lock.parent.mkdir(parents=True)
            lock.write_bytes(b"12345678")
            before = lock.read_bytes()
            delta.assert_source_stopped(source)
            self.assertEqual(lock.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
