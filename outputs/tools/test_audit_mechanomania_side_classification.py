from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import audit_mechanomania_side_classification as audit
import validate_mechanomania_side_classification as validator


class SideClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report(
            audit.Inputs(generated_at_utc="2026-08-13T10:00:00+00:00")
        )
        cls.by_id = {row["mod_id"]: row for row in cls.report["classifications"]}

    def test_exact_target_set_and_clean_status(self) -> None:
        self.assertEqual(set(self.by_id), set(audit.TARGET_IDS))
        self.assertEqual(self.report["status"], "PASS_STATIC_SIDE_CLASSIFICATION")
        self.assertEqual(self.report["unresolved_mod_ids"], [])

    def test_both_classifications(self) -> None:
        expected = {
            "byepregen",
            "efficient_hashing",
            "fastrecipesearch",
            "mr_dungeons_andtavernsancientcityoverhaul",
            "mr_epic_structuresvillages",
            "mr_lukis_crazychambers",
            "rhino",
        }
        actual = {mod_id for mod_id, row in self.by_id.items() if row["classification"] == "BOTH"}
        self.assertEqual(actual, expected)
        for mod_id in expected:
            self.assertTrue(self.by_id[mod_id]["server_bundle"])
            self.assertTrue(self.by_id[mod_id]["client_bundle"])

    def test_pure_data_pack_placement_is_fail_closed(self) -> None:
        expected = {"hoporp"}
        actual = {mod_id for mod_id, row in self.by_id.items() if row["classification"] == "SERVER_ONLY"}
        self.assertEqual(actual, expected)
        for mod_id in audit.PURE_DATA_IDS:
            inspection = self.by_id[mod_id]["inspection"]
            self.assertTrue(inspection["pure_data_pack"])
            self.assertEqual(inspection["class_count"], 0)
            self.assertGreater(inspection["data_file_count"], 0)
            self.assertEqual(inspection["asset_file_count"], 0)
        self.assertEqual(
            self.by_id["hoporp"]["inspection"]["metadata"]["display_test"],
            "IGNORE_SERVER_VERSION",
        )
        for mod_id in audit.PURE_DATA_IDS - {"hoporp"}:
            self.assertEqual(self.by_id[mod_id]["classification"], "BOTH")
            self.assertIsNone(self.by_id[mod_id]["inspection"]["metadata"]["display_test"])

    def test_client_only_classifications(self) -> None:
        expected = {"jecharacters", "mousetweaks", "yet_another_config_lib_v3"}
        actual = {mod_id for mod_id, row in self.by_id.items() if row["classification"] == "CLIENT_ONLY"}
        self.assertEqual(actual, expected)
        for mod_id in expected:
            row = self.by_id[mod_id]
            self.assertFalse(row["server_bundle"])
            self.assertTrue(row["client_bundle"])
            self.assertGreater(row["inspection"]["bytecode"]["client_symbol_count"], 0)

    def test_byepregen_duplicate_is_resolved(self) -> None:
        row = self.by_id["byepregen"]
        self.assertEqual(row["selected_file"], "byepregen-1.0.7.jar")
        self.assertEqual(row["excluded_candidate_files"], ["byepregen-1.0.0.jar"])
        self.assertGreater(row["inspection"]["mixins"]["client_count"], 0)
        self.assertGreater(row["inspection"]["mixins"]["common_count"], 0)

    def test_fast_recipe_search_has_two_side_evidence(self) -> None:
        row = self.by_id["fastrecipesearch"]
        configs = row["inspection"]["mixins"]["configs"]
        common = {name for config in configs for name in config.get("common", [])}
        client = {name for config in configs for name in config.get("client", [])}
        self.assertIn("ServerResourcesMixin", common)
        self.assertIn("ClientPacketListenerMixin", client)

    def test_rhino_is_required_by_kubejs_on_both(self) -> None:
        reverse = self.by_id["rhino"]["reverse_dependencies"]
        self.assertTrue(
            any(
                row["side"] == "BOTH"
                and row["type"] == "required"
                and "kubejs" in row["dependent_mod_ids"]
                for row in reverse
            )
        )

    def test_yacl_required_reverse_dependencies_are_client_scoped(self) -> None:
        required = [
            row
            for row in self.by_id["yet_another_config_lib_v3"]["reverse_dependencies"]
            if row["type"] == "required"
        ]
        self.assertTrue(required)
        self.assertEqual({row["side"] for row in required}, {"CLIENT"})

    def test_scope_is_read_only(self) -> None:
        scope = self.report["scope"]
        self.assertFalse(scope["java_or_minecraft_started"])
        self.assertFalse(scope["release_modified"])
        self.assertFalse(scope["world_modified"])
        self.assertFalse(scope["network_used"])

    def test_markdown_is_actionable(self) -> None:
        text = audit.markdown_report(self.report)
        self.assertIn("SERVER_ONLY", text)
        self.assertIn("CLIENT_ONLY", text)
        self.assertIn("专服启动", text)
        self.assertIn("不锁死后续 MCModSync OTA", text)

    def test_validator_rejects_tampered_classification(self) -> None:
        tampered = copy.deepcopy(self.report)
        tampered["classifications"][0]["classification"] = "CLIENT_ONLY"
        with tempfile.TemporaryDirectory(dir=audit.WORKSPACE / "outputs/tmp") as root:
            path = Path(root) / "tampered.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected BOTH"):
                validator.validate(path)

    def test_validator_accepts_written_report(self) -> None:
        with tempfile.TemporaryDirectory(dir=audit.WORKSPACE / "outputs/tmp") as root:
            json_path = Path(root) / "report.json"
            md_path = Path(root) / "report.md"
            audit.write_reports(self.report, json_path, md_path)
            result = validator.validate(json_path)
            self.assertEqual(result["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
