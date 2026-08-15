from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("remote_live_snapshot.py")
SPEC = importlib.util.spec_from_file_location(
    "remote_live_snapshot_under_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
snapshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)

ROOT = Path(__file__).resolve().parents[2]


class RemoteLiveSnapshotTest(unittest.TestCase):
    def temporary(self):
        (ROOT / "outputs/tmp").mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=ROOT / "outputs/tmp")

    @staticmethod
    def source_tree(root: Path) -> Path:
        source = root / "live"
        (source / "world/playerdata").mkdir(parents=True)
        (source / "config").mkdir()
        (source / "EasyAuth").mkdir()
        (source / "world/level.dat").write_bytes(b"level-v1")
        (source / "world/playerdata/player.dat").write_bytes(b"player-v1")
        (source / "config/example.toml").write_bytes(b"config-v1")
        (source / "EasyAuth/easyauth.db").write_bytes(b"auth-v1")
        (source / "server.properties").write_bytes(b"motd=test\n")
        # Volatile files must never enter the migration-input mirror.
        (source / "world/session.lock").write_bytes(b"lock")
        (source / "world/ledger.sqlite").write_bytes(b"ledger")
        return source

    @staticmethod
    def paths(base: Path) -> tuple[Path, Path]:
        meta = base / "meta"
        meta.mkdir()
        return base / "mirror", meta / "mirror-manifest.json"

    def preheat(self, source: Path, mirror: Path, manifest: Path) -> dict:
        with mock.patch.object(snapshot, "_probe", return_value={"status": "HELD"}):
            return snapshot.preheat(source, mirror, manifest, retries=1)

    def test_preheat_publishes_exact_source_relative_mirror(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            result = self.preheat(source, mirror, manifest)

            self.assertEqual(result["status"], "PREHEATED_MIRROR_PUBLISHED")
            self.assertEqual((mirror / "world/level.dat").read_bytes(), b"level-v1")
            self.assertEqual((mirror / "EasyAuth/easyauth.db").read_bytes(), b"auth-v1")
            self.assertFalse((mirror / "world/session.lock").exists())
            self.assertFalse((mirror / "world/ledger.sqlite").exists())
            value = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(value["file_count"], 5)
            self.assertEqual(
                value["snapshot_sha256"], result["snapshot"]["snapshot_sha256"]
            )
            verified = snapshot._mirror_matches_manifest(mirror, value)
            self.assertEqual(verified["status"], "PASS")

    def test_preheat_never_writes_inside_source(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            manifest = base / "meta.json"
            result = snapshot.preheat(source, source / "mirror", manifest)
            self.assertEqual(result["status"], "BLOCKED_PREHEAT")
            self.assertIn("disjoint", result["error"])
            self.assertFalse((source / "mirror").exists())

    def test_preheat_source_change_leaves_no_published_mirror(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            original = snapshot.source_snapshot
            source_calls = 0

            def changing(root: Path, **kwargs):
                nonlocal source_calls
                value = original(root, **kwargs)
                if snapshot._same_path(root, source):
                    source_calls += 1
                    if source_calls == 2:
                        value = {**value, "snapshot_sha256": "0" * 64}
                return value

            with (
                mock.patch.object(snapshot, "_probe", return_value={"status": "HELD"}),
                mock.patch.object(snapshot, "source_snapshot", side_effect=changing),
            ):
                result = snapshot.preheat(source, mirror, manifest, retries=1)
            self.assertEqual(result["status"], "BLOCKED_SOURCE_CHANGED_DURING_PREHEAT")
            self.assertFalse(mirror.exists())
            self.assertFalse(manifest.exists())

    def test_refresh_copies_only_changed_and_added_files(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            self.assertEqual(self.preheat(source, mirror, manifest)["exit_code"], 0)
            (source / "config/example.toml").write_bytes(b"config-v2")
            (source / "world/playerdata/new.dat").write_bytes(b"new-player")
            original_copy = snapshot._atomic_copy_verified

            with (
                mock.patch.object(
                    snapshot, "_probe", return_value={"status": "UNLOCKED"}
                ),
                mock.patch.object(
                    snapshot, "_atomic_copy_verified", wraps=original_copy
                ) as copied,
            ):
                result = snapshot.refresh(source, mirror, manifest, retries=1)

            self.assertEqual(result["status"], "REFRESHED_MIRROR")
            self.assertEqual(copied.call_count, 2)
            self.assertEqual(
                (mirror / "config/example.toml").read_bytes(), b"config-v2"
            )
            self.assertEqual(
                (mirror / "world/playerdata/new.dat").read_bytes(), b"new-player"
            )
            current = snapshot.source_snapshot(source, label="<LIVE_SERVER>", retries=1)
            mirrored = snapshot.source_snapshot(
                mirror, label="<LIVE_SNAPSHOT>", retries=1
            )
            self.assertEqual(current["snapshot_sha256"], mirrored["snapshot_sha256"])

    def test_refresh_blocks_deletion_without_touching_mirror(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            self.assertEqual(self.preheat(source, mirror, manifest)["exit_code"], 0)
            manifest_before = manifest.read_bytes()
            (source / "config/example.toml").unlink()

            with mock.patch.object(
                snapshot, "_probe", return_value={"status": "UNLOCKED"}
            ):
                result = snapshot.refresh(source, mirror, manifest, retries=1)

            self.assertEqual(result["status"], "BLOCKED_SOURCE_DELETIONS")
            self.assertTrue((mirror / "config/example.toml").is_file())
            self.assertEqual(manifest.read_bytes(), manifest_before)
            self.assertEqual(
                result["deletion_policy"]["all_deletions"], ["config/example.toml"]
            )

    def test_reviewed_noncritical_deletion_is_applied_transactionally(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            self.assertEqual(self.preheat(source, mirror, manifest)["exit_code"], 0)
            (source / "config/example.toml").unlink()

            with mock.patch.object(
                snapshot, "_probe", return_value={"status": "UNLOCKED"}
            ):
                result = snapshot.refresh(
                    source,
                    mirror,
                    manifest,
                    allow_source_deletions=True,
                    retries=1,
                )

            self.assertEqual(result["status"], "REFRESHED_MIRROR")
            self.assertFalse((mirror / "config/example.toml").exists())
            self.assertEqual(result["transaction"]["deletions"], 1)

    def test_critical_deletion_is_always_blocked(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            self.assertEqual(self.preheat(source, mirror, manifest)["exit_code"], 0)
            (source / "world/level.dat").unlink()

            with mock.patch.object(
                snapshot, "_probe", return_value={"status": "UNLOCKED"}
            ):
                result = snapshot.refresh(
                    source,
                    mirror,
                    manifest,
                    allow_source_deletions=True,
                    retries=1,
                )

            self.assertEqual(result["status"], "BLOCKED_SOURCE_DELETIONS")
            self.assertEqual(
                result["deletion_policy"]["critical_deletions"], ["world/level.dat"]
            )
            self.assertTrue((mirror / "world/level.dat").is_file())

    def test_refresh_requires_stopped_source(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            self.assertEqual(self.preheat(source, mirror, manifest)["exit_code"], 0)
            (source / "config/example.toml").write_bytes(b"changed")

            with mock.patch.object(snapshot, "_probe", return_value={"status": "HELD"}):
                result = snapshot.refresh(source, mirror, manifest, retries=1)

            self.assertEqual(result["status"], "BLOCKED_REFRESH")
            self.assertEqual(
                (mirror / "config/example.toml").read_bytes(), b"config-v1"
            )

    def test_tampered_mirror_blocks_before_refresh(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            self.assertEqual(self.preheat(source, mirror, manifest)["exit_code"], 0)
            (mirror / "config/example.toml").write_bytes(b"tampered")

            with mock.patch.object(
                snapshot, "_probe", return_value={"status": "UNLOCKED"}
            ):
                result = snapshot.refresh(source, mirror, manifest, retries=1)

            self.assertEqual(result["status"], "BLOCKED_REFRESH")
            self.assertEqual(result["mirror_before"]["status"], "FAIL")

    def test_post_commit_source_change_rolls_mirror_back(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            self.assertEqual(self.preheat(source, mirror, manifest)["exit_code"], 0)
            manifest_before = manifest.read_bytes()
            (source / "config/example.toml").write_bytes(b"config-v2")
            original_snapshot = snapshot.source_snapshot
            source_calls = 0

            def changing(root: Path, **kwargs):
                nonlocal source_calls
                value = original_snapshot(root, **kwargs)
                if snapshot._same_path(root, source):
                    source_calls += 1
                    if source_calls == 3:
                        value = {**value, "snapshot_sha256": "f" * 64}
                return value

            with (
                mock.patch.object(
                    snapshot, "_probe", return_value={"status": "UNLOCKED"}
                ),
                mock.patch.object(snapshot, "source_snapshot", side_effect=changing),
            ):
                result = snapshot.refresh(source, mirror, manifest, retries=1)

            self.assertEqual(result["status"], "BLOCKED_REFRESH")
            self.assertEqual(
                (mirror / "config/example.toml").read_bytes(), b"config-v1"
            )
            self.assertEqual(manifest.read_bytes(), manifest_before)

    def test_failed_rollback_retains_transaction_for_recovery(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            self.assertEqual(self.preheat(source, mirror, manifest)["exit_code"], 0)
            (source / "config/example.toml").write_bytes(b"config-v2")
            original_snapshot = snapshot.source_snapshot
            source_calls = 0

            def changing(root: Path, **kwargs):
                nonlocal source_calls
                value = original_snapshot(root, **kwargs)
                if snapshot._same_path(root, source):
                    source_calls += 1
                    if source_calls == 3:
                        value = {**value, "snapshot_sha256": "f" * 64}
                return value

            with (
                mock.patch.object(
                    snapshot, "_probe", return_value={"status": "UNLOCKED"}
                ),
                mock.patch.object(snapshot, "source_snapshot", side_effect=changing),
                mock.patch.object(
                    snapshot._MIGRATION,
                    "rollback_transaction",
                    side_effect=RuntimeError("simulated rollback outage"),
                ),
            ):
                result = snapshot.refresh(source, mirror, manifest, retries=1)

            self.assertEqual(
                result["status"],
                "REFRESH_ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED",
            )
            self.assertTrue(result["transaction"]["retained_for_recovery"])
            self.assertTrue(Path(result["transaction"]["path"]).is_dir())

    def test_orphan_transaction_blocks_refresh(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = self.source_tree(base)
            mirror, manifest = self.paths(base)
            self.assertEqual(self.preheat(source, mirror, manifest)["exit_code"], 0)
            (mirror.parent / ".mirror.refresh-orphan").mkdir()

            with mock.patch.object(
                snapshot, "_probe", return_value={"status": "UNLOCKED"}
            ):
                result = snapshot.refresh(source, mirror, manifest, retries=1)

            self.assertEqual(result["status"], "BLOCKED_REFRESH")
            self.assertIn("orphan", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
