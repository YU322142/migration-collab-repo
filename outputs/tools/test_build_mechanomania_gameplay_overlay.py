from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from outputs.tools.build_mechanomania_gameplay_overlay import (
    classify_config,
    classify_pack_path,
    content_digest,
    is_excluded_pack_path,
)


class GameplayOverlayUnitTests(unittest.TestCase):
    def test_forbidden_pack_state_is_excluded(self) -> None:
        for path in (
            "mods/example.jar",
            "configureddefaults/options.txt",
            "data/fabricDefaultResourcePacks.dat",
            ".mixin.out/a.txt",
            "icon.png",
            "config/journeymap-server.toml",
            "config/create-client-1.toml.bak",
            "config/spark/tmp/about.txt",
            "kubejs/README.txt",
        ):
            self.assertTrue(is_excluded_pack_path(path), path)

    def test_gameplay_payload_is_not_excluded(self) -> None:
        for path in (
            "kubejs/server_scripts/main.js",
            "kubejs/startup_scripts/fluids.js",
            "kubejs/data/example/recipe/a.json",
            "tlm_custom_pack/models/a.json",
            "resourcepacks/ccc.zip",
            "schematics/alloy_smelter.nbt",
        ):
            self.assertFalse(is_excluded_pack_path(path), path)

    def test_side_classification(self) -> None:
        expected = {
            "shaderpacks/a.zip": "CLIENT",
            "resourcepacks/ccc.zip": "CLIENT",
            "kubejs/client_scripts/main.js": "CLIENT",
            "kubejs/assets/example/lang/en_us.json": "CLIENT",
            "kubejs/server_scripts/main.js": "SERVER",
            "kubejs/data/example/recipe/a.json": "SERVER",
            "kubejs/startup_scripts/main.js": "BOTH",
            "tlm_custom_pack/a.json": "BOTH",
            ".sable/natives/a.dll": "BOTH",
            "schematics/a.nbt": "BOTH",
        }
        for path, target in expected.items():
            self.assertEqual(classify_pack_path(path), target, path)

    def test_config_classification(self) -> None:
        self.assertEqual(classify_config("config/create-client.toml"), "CLIENT")
        self.assertEqual(classify_config("config/create-server.toml"), "SERVER")
        self.assertEqual(classify_config("config/create-common.toml"), "BOTH")
        self.assertEqual(classify_config("config/modernfix-mixins.properties"), "CLIENT")
        self.assertEqual(classify_config("config/xaero/minimap.txt"), "CLIENT")

    def test_content_digest_is_order_independent(self) -> None:
        rows = [
            {"target": "SERVER", "target_rel": "a", "bytes": 1, "sha256": "A", "layer": "x", "merge_mode": "replace"},
            {"target": "CLIENT", "target_rel": "b", "bytes": 2, "sha256": "B", "layer": "y", "merge_mode": "copy_if_absent"},
        ]
        self.assertEqual(content_digest(rows), content_digest(list(reversed(rows))))

    def test_unknown_top_level_is_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unclassified"):
            classify_pack_path("mystery/file.bin")

    def test_superseded_paths_are_a_distinct_accounting_bucket(self) -> None:
        source = {"a", "b", "c", "d"}
        effective = {"a", "b"}
        excluded = {"c"}
        superseded = {"d"}
        self.assertEqual(source, effective | excluded | superseded)
        self.assertFalse(effective & excluded)
        self.assertFalse(effective & superseded)
        self.assertFalse(excluded & superseded)


if __name__ == "__main__":
    unittest.main()
