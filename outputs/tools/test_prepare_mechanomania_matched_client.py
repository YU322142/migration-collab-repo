from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from outputs.tools import prepare_mechanomania_matched_client as subject


class ClientPreparationContractTest(unittest.TestCase):
    def test_runtime_pack_name_is_ascii_and_stable(self) -> None:
        self.assertEqual(
            subject.PACK_RUNTIME_NAME,
            "migration-local-resources-mc1.21.1.zip",
        )
        subject.PACK_RUNTIME_NAME.encode("ascii")

    def test_options_enable_only_the_named_local_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "options.txt"
            path.write_text(
                'resourcePacks:["fabric","file/old.zip"]\n'
                "lastServer:example.invalid:1\n",
                encoding="utf-8",
            )
            subject.update_options(path, subject.PACK_RUNTIME_NAME)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("resourcePacks:"), 1)
            self.assertEqual(text.count("file/" + subject.PACK_RUNTIME_NAME), 1)
            self.assertNotIn("file/old.zip", text)
            self.assertEqual(text.count("lastServer:127.0.0.1:12341"), 1)

    def test_servers_dat_is_binary_nbt_and_declines_remote_pack(self) -> None:
        value = subject.servers_dat()
        self.assertTrue(value.startswith(b"\x0a\x00\x00"))
        self.assertIn(b"127.0.0.1:12341", value)
        self.assertIn(b"acceptTextures", value)

    def test_xaero_online_checks_are_disabled_without_touching_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "client.cfg"
            path.write_text(
                "current_profile = default\n"
                "update_notifications = true\n"
                "differentiate_by_server_address = true\n",
                encoding="utf-8",
            )
            subject.set_cfg_value(path, "update_notifications", "false")
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("update_notifications = false"), 1)
            self.assertNotIn("update_notifications = true", text)
            self.assertIn("differentiate_by_server_address = true", text)

    def test_xaero_required_key_missing_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "common.cfg"
            path.write_text("default_enforced_profile = default\n", encoding="utf-8")
            with self.assertRaises(subject.ClientPrepareError):
                subject.set_cfg_value(path, "allow_internet_access", "false")


if __name__ == "__main__":
    unittest.main()
