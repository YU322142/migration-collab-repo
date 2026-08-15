from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("build_candidate14_ota_readiness.py")
SPEC = importlib.util.spec_from_file_location("candidate14_ota", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ota = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ota)


class Candidate14OtaReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(ota.MOD_POLICY_JSON.read_text(encoding="utf-8"))
        cls.readiness = json.loads(ota.OTA_JSON.read_text(encoding="utf-8"))
        cls.draft = json.loads((ota.TEMPLATE_ROOT / "catalog-draft.json").read_text(encoding="utf-8"))
        cls.supersession = json.loads(ota.SUPERSESSION_JSON.read_text(encoding="utf-8"))

    def test_first_release_keeps_exact_candidate14_sides(self) -> None:
        server_count = ota.CANDIDATE14_LOCK["server_files"]
        client_count = ota.CANDIDATE14_LOCK["client_files"]
        self.assertEqual(ota.BUNDLE_REVISION, self.policy["bundle_revision"])
        self.assertTrue(self.policy["counts"]["release_snapshot_not_permanent_cap"])
        extension = self.policy["extension_policy"]
        self.assertEqual("acceptance_snapshot_not_permanent_allowlist", extension["release_lock_semantics"])
        self.assertTrue(extension["current_file_counts_are_not_production_caps"])
        self.assertTrue(extension["ota_additions_allowed"])
        self.assertFalse(extension["permanent_exact_mod_count_enforcement"])
        self.assertEqual(server_count, self.policy["bundle"]["server"]["file_count"])
        self.assertEqual(client_count, self.policy["bundle"]["client"]["file_count"])
        self.assertEqual(server_count + 1, len(self.policy["inventory"]))
        self.assertEqual([ota.SERVER_ONLY_FILE], self.policy["side_policy"]["server_only"])
        self.assertEqual([ota.CLIENT_ONLY_FILE], self.policy["side_policy"]["client_only"])
        client = [row for row in self.policy["inventory"] if row["side"] in {"both", "client"}]
        self.assertEqual(client_count, len(client))
        self.assertTrue(all(row["first_ota_kind"] == "required" for row in client))
        self.assertEqual(0, self.policy["counts"]["first_ota_recommended_rows"])
        self.assertEqual(server_count + client_count, self.policy["counts"]["validated_physical_jar_copies"])

    def test_mcmodsync_is_hash_locked_but_not_installed(self) -> None:
        self.assertFalse(self.readiness["candidate14"]["mcmodsync_present_server"])
        self.assertFalse(self.readiness["candidate14"]["mcmodsync_present_client"])
        self.assertEqual(ota.MCMODSYNC_LOCK["sha256"], self.readiness["mcmodsync"]["sha256"])
        self.assertIn(ota.MCMODSYNC_LOCK["file"], self.readiness["side_policy"]["server_forbidden"])
        self.assertIn(ota.SERVER_ONLY_FILE, self.readiness["side_policy"]["ota_forbidden"])
        self.assertEqual("client", self.readiness["mcmodsync"]["declared_side"])

    def test_remote_enablement_is_fail_closed_and_blocked(self) -> None:
        self.assertFalse(self.readiness["publish_allowed"])
        self.assertFalse(self.readiness["runtime_install_allowed"])
        self.assertIsNone(self.readiness["remote_manifest_url"])
        self.assertTrue(self.readiness["fail_closed"]["first_catalog_all_runtime_rows_required"])
        self.assertEqual(
            ota.CANDIDATE14_LOCK["client_files"] + 2,
            self.readiness["catalog_plan"]["expected_final_rows_after_config_generation"],
        )
        gate_ids = {row["id"] for row in self.readiness["release_gates"]}
        self.assertIn(
            f"complete_{ota.CANDIDATE14_LOCK['client_files'] + 2}_row_v4_catalog",
            gate_ids,
        )
        self.assertIn(
            "additions, upgrades and removals",
            self.readiness["catalog_plan"]["future_catalog_set_rule"],
        )
        self.assertIn("authoritative READY", self.readiness["catalog_plan"]["catalog_version_source"])
        expected_catalog_version = (
            f"{ota.BUNDLE_REVISION}-20260812-{ota.CANDIDATE14_LOCK['ready_sha256'][:16].lower()}"
        )
        self.assertEqual(expected_catalog_version, ota.derived_catalog_version())
        self.assertEqual(expected_catalog_version, self.readiness["catalog_plan"]["derived_catalog_version"])
        self.assertEqual(expected_catalog_version, self.draft["derived_catalog_version"])
        self.assertTrue(
            self.readiness["network_and_supply_chain_policy"]["no_signing_key_or_signature_in_current_local_template"]
        )
        self.assertEqual(["MCModSync-Config.jar"], self.readiness["catalog_plan"]["unresolved_rows"])

    def test_templates_cannot_be_accidentally_published(self) -> None:
        self.assertFalse((ota.TEMPLATE_ROOT / "mods-v4.txt").exists())
        self.assertFalse((ota.TEMPLATE_ROOT / "mods.txt").exists())
        self.assertFalse((ota.TEMPLATE_ROOT / "modsync.properties").exists())
        self.assertFalse((ota.TEMPLATE_ROOT / "MCModSync-Config.jar").exists())
        v4 = (ota.TEMPLATE_ROOT / "mods-v4.UNPUBLISHED.tsv").read_text(encoding="utf-8")
        v2 = (ota.TEMPLATE_ROOT / "mods-v2.UNPUBLISHED.tsv").read_text(encoding="utf-8")
        properties = (ota.TEMPLATE_ROOT / "modsync.properties.template").read_text(encoding="utf-8")
        self.assertNotIn("# mcmod-sync-v4\n", v4)
        self.assertIn("<UNRESOLVED_SHA256>", v4)
        self.assertIn("${CONTROLLED_HTTPS_MANIFEST_URL}", properties)
        self.assertNotIn("http://", properties)
        self.assertNotIn("https://", properties)
        self.assertIn("syncResourcePacks=false", properties)
        self.assertIn("syncServerList=false", properties)
        self.assertIn("strict=true", properties)
        self.assertIn("requireManifest=true", properties)
        self.assertIn(ota.BUNDLE_REVISION, v4)
        self.assertIn(ota.BUNDLE_REVISION, v2)
        self.assertIn(ota.BUNDLE_REVISION, properties)
        self.assertIn(ota.derived_catalog_version(), v4)
        self.assertIn(ota.derived_catalog_version(), v2)
        self.assertIn(ota.derived_catalog_version(), properties)
        self.assertEqual(ota.CANDIDATE14_LOCK["client_files"] + 1, len(self.draft["resolved_entries"]))
        self.assertEqual(1, len(self.draft["unresolved_entries"]))

    def test_production_config_lock_and_test_port_boundary(self) -> None:
        config = self.readiness["production_configuration"]
        self.assertEqual(ota.SERVER_PROPERTIES_LOCK["sha256"], config["sha256"])
        self.assertTrue(config["must_remain_byte_identical"])
        self.assertEqual("25566", config["locked_fields"]["server-port"])
        self.assertEqual([12341, 12342, 26341], config["test_only_loopback_ports_never_write_to_production"])
        self.assertFalse(self.readiness["production_or_prism_modified"])

    def test_hash_helpers_are_order_sensitive(self) -> None:
        rows = [
            {"file": "a.jar", "sha256": "A" * 64},
            {"file": "b.jar", "sha256": "B" * 64},
        ]
        self.assertNotEqual(ota.bundle_digest(rows), ota.bundle_digest(list(reversed(rows))))
        self.assertNotEqual(ota.pair_digest("A" * 64, "B" * 64), ota.pair_digest("B" * 64, "A" * 64))

    def test_digest_report_matches_generated_artifacts(self) -> None:
        report = json.loads(ota.DIGEST_JSON.read_text(encoding="utf-8"))
        self.assertEqual("PASS", report["status"])
        self.assertEqual(ota.BUNDLE_REVISION, report["bundle_revision"])
        for row in report["artifacts"]:
            path = ota.WORKSPACE / row["path"]
            self.assertEqual(row["bytes"], path.stat().st_size)
            self.assertEqual(row["sha256"], hashlib.sha256(path.read_bytes()).hexdigest().upper())

    def test_r2_is_explicitly_superseded_by_r3(self) -> None:
        self.assertEqual("STALE_SUPERSEDED", self.supersession["status"])
        self.assertEqual("candidate14-r2", self.supersession["superseded"]["bundle_revision"])
        self.assertEqual(ota.BUNDLE_REVISION, self.supersession["authoritative"]["bundle_revision"])
        self.assertTrue(self.supersession["same_business_jar_bytes"])
        self.assertNotEqual(
            self.supersession["superseded"]["ready_sha256"],
            self.supersession["authoritative"]["ready_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
