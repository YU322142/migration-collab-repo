#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("build_singleplayer_gameplay_parity.py")
SPEC = importlib.util.spec_from_file_location("singleplayer_parity", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SingleplayerGameplayParityPolicyTest(unittest.TestCase):
    def test_auth_and_operational_configs_are_denied(self) -> None:
        denied = [
            "EasyAuth/main.conf",
            "easybot/config.json",
            "floodgate/key.pem",
            "Geyser-Fabric/config.yml",
            "grieflogger/database.db",
            "hydraulic/cache/vanilla-assets.zip",
            "skinsrestorer/config.yml",
            "trueuuid-registry.json",
            "simplebackups-server.toml",
        ]
        for path in denied:
            with self.subTest(path=path):
                self.assertFalse(MODULE.safe_config_path(path))

    def test_gameplay_server_configs_are_allowed(self) -> None:
        allowed = [
            "create-server.toml",
            "createbigcannons-server.toml",
            "touhou_little_maid-server.toml",
            "l2configs/l2hostility-server.toml",
            "openpartiesandclaims-server.toml",
        ]
        for path in allowed:
            with self.subTest(path=path):
                self.assertTrue(MODULE.safe_config_path(path))

    def test_login_markers_are_explicit(self) -> None:
        self.assertIn("xiyuslogin", MODULE.AUTH_SCRIPT_MARKERS)
        self.assertIn("trueuuid", MODULE.AUTH_SCRIPT_MARKERS)
        self.assertIn("/login", MODULE.AUTH_SCRIPT_MARKERS)

    def test_tlm_pack_location_is_part_of_reviewed_repository(self) -> None:
        repo = SCRIPT.resolve().parents[2]
        pack = repo / "pack" / "common-tlm-custom-pack"
        self.assertTrue((pack / "touhou_little_maid-1.0.0" / "pack.mcmeta").is_file())


if __name__ == "__main__":
    unittest.main()
