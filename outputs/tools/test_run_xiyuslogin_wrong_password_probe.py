from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("run_xiyuslogin_wrong_password_probe.py")
SPEC = importlib.util.spec_from_file_location("run_xiyuslogin_wrong_password_probe", MODULE_PATH)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


class WrongPasswordProbeTest(unittest.TestCase):
    def test_snapshot_hashes_record_without_exposing_password_hash(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "players.json"
            path.write_text(
                json.dumps({"synthetic": {"passwordHash": "$2b$12$fixture", "loginCount": 2}}),
                encoding="utf-8",
            )
            summary = probe.snapshot(path)
            self.assertEqual(summary["login_count"], 2)
            self.assertNotIn("passwordHash", summary)
            self.assertNotIn("$2b$", json.dumps(summary))

    def test_snapshot_requires_one_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "players.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                probe.snapshot(path)


if __name__ == "__main__":
    unittest.main()
