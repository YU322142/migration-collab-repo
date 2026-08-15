from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from outputs.tools import build_remote_cutover_prep as builder


ROOT = Path(__file__).resolve().parents[2]
REMOTE_PATH = ROOT / "outputs/remote-cutover-prep-src/remote_cutover.py"
SPEC = importlib.util.spec_from_file_location("remote_cutover_under_test", REMOTE_PATH)
assert SPEC is not None and SPEC.loader is not None
remote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remote)


class RemoteCutoverTest(unittest.TestCase):
    def temporary(self):
        return tempfile.TemporaryDirectory(dir=ROOT / "outputs/tmp")

    def test_snapshot_round_trip_and_mutation_detection(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            source = base / "live"
            (source / "world/data").mkdir(parents=True)
            (source / "mods").mkdir()
            (source / "server.properties").write_text("motd=test\n", encoding="utf-8")
            (source / "world/session.lock").write_bytes(b"stopped")
            (source / "world/data/value.dat").write_bytes(b"payload")
            manifest = remote.scan_snapshot(source, "<LIVE_SERVER>")
            rendered = json.dumps(manifest)
            self.assertNotIn("value.dat", rendered)
            self.assertNotIn("session.lock", rendered)
            self.assertEqual(remote.verify_snapshot(source, manifest)["status"], "PASS")
            (source / "world/data/value.dat").write_bytes(b"changed")
            result = remote.verify_snapshot(source, manifest)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(len(result["differences"]["changed_files"]), 1)

    def test_preflight_distinguishes_running_and_stopped(self) -> None:
        with self.temporary() as temporary:
            root = Path(temporary) / "live"
            (root / "world").mkdir(parents=True)
            (root / "mods").mkdir()
            (root / "server.properties").write_text("motd=test\n", encoding="utf-8")
            ready = {"status": "READY_PORTAL_ZERO", "exit_code": 0, "totals": {"portal_count": 0}}
            with mock.patch.object(remote, "portal_probe", return_value=ready), mock.patch.object(
                remote, "probe_session_lock", return_value={"status": "HELD"}
            ):
                self.assertEqual(remote.run_preflight(root, "running")["status"], "READY_PRESTOP_ONLY")
                self.assertEqual(remote.run_preflight(root, "stopped")["status"], "BLOCKED_READ_ONLY_PREFLIGHT")
            with mock.patch.object(remote, "portal_probe", return_value=ready), mock.patch.object(
                remote, "probe_session_lock", return_value={"status": "UNLOCKED"}
            ):
                self.assertEqual(remote.run_preflight(root, "stopped")["status"], "READY_FOR_SNAPSHOT")

    def test_candidate_bundle_verification_fails_closed(self) -> None:
        with self.temporary() as temporary:
            mods = Path(temporary) / "mods"
            mods.mkdir()
            first = mods / "a.jar"
            second = mods / "b.jar"
            first.write_bytes(b"a")
            second.write_bytes(b"bb")
            rows = [
                {"file": path.name, "bytes": path.stat().st_size, "sha256": remote.sha256_file(path)}
                for path in (first, second)
            ]
            manifest = {
                "file_count": 2,
                "bytes": 3,
                "bundle_sha256": remote.bundle_digest(rows),
                "files": rows,
            }
            self.assertEqual(remote.verify_bundle(mods, manifest)["status"], "PASS")
            second.write_bytes(b"tampered")
            self.assertEqual(remote.verify_bundle(mods, manifest)["status"], "FAIL")

    def test_builder_is_deterministic_and_package_is_path_neutral(self) -> None:
        with self.temporary() as temporary:
            base = Path(temporary)
            outputs = []
            for suffix in ("a", "b"):
                package = base / f"package-{suffix}"
                archive = base / f"package-{suffix}.zip"
                report = base / f"package-{suffix}.json"
                built = builder.build(ROOT, package, archive, report)
                self.assertEqual(built["status"], "BUILT")
                outputs.append((package, archive, report))
            self.assertEqual(builder.sha256(outputs[0][1]), builder.sha256(outputs[1][1]))
            package = outputs[0][0]
            for path in package.rglob("*"):
                if path.is_file():
                    content = path.read_bytes().lower()
                    self.assertNotIn(b"d:\\trans", content)
                    self.assertNotIn(b"20260807", content)
            result = remote.verify_package(package, package / "PACKAGE-MANIFEST.json")
            self.assertEqual(result["status"], "PASS")

    def test_outputs_must_stay_outside_inspected_root(self) -> None:
        with self.temporary() as temporary:
            root = Path(temporary) / "live"
            root.mkdir()
            with self.assertRaisesRegex(remote.CutoverError, "outside"):
                remote.require_external_output(root, root / "report.json", "report")


if __name__ == "__main__":
    unittest.main()
