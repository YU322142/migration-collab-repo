from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("prepare_final_fullstack_smoke.py")
SPEC = importlib.util.spec_from_file_location("prepare_final_fullstack_smoke", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class PrepareSmokeTest(unittest.TestCase):
    def d_temp(self):
        root = Path(os.environ.get("MIGRATION_TEST_TMP", r"D:\Trans\migration-audit-work\tmp"))
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def test_properties_are_replaced_without_duplicates(self):
        with self.d_temp() as temporary:
            path = Path(temporary) / "server.properties"
            path.write_text("# header\nserver-port=25565\nonline-mode=true\n", encoding="ascii")
            smoke.replace_properties(
                path, {"server-port": "11821", "online-mode": "false", "enable-rcon": "true"}
            )
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("server-port="), 1)
            self.assertIn("server-port=11821", text)
            self.assertIn("online-mode=false", text)
            self.assertIn("enable-rcon=true", text)

    def test_mineastr_is_disabled_without_touching_other_values(self):
        with self.d_temp() as temporary:
            path = Path(temporary) / "mineastr-common.toml"
            path.write_text('enabled = true\nserverId = "unchanged"\n', encoding="utf-8")
            smoke.disable_mineastr_network(path)
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                'enabled = false\nserverId = "unchanged"\n',
            )


if __name__ == "__main__":
    unittest.main()
