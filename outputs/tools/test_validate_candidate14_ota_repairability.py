from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("validate_candidate14_ota_repairability.py")
SPEC = importlib.util.spec_from_file_location("candidate14_repairability", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class Candidate14OtaRepairabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(validator.DEFAULT_CONTRACT.read_text(encoding="utf-8"))

    def validate(self, contract):
        return validator.validate_contract(contract, validator.DEFAULT_CONTRACT)

    def test_authoritative_contract_passes(self) -> None:
        report = self.validate(copy.deepcopy(self.contract))
        self.assertEqual("PASS", report["status"], report["errors"])
        self.assertGreaterEqual(report["known_error_count"], 10)
        self.assertTrue(all(count > 0 for count in report["class_counts"].values()))

    def test_client_only_cannot_mutate_world(self) -> None:
        contract = copy.deepcopy(self.contract)
        item = next(row for row in contract["known_error_coverage"] if row["class"] == "client_only_ota")
        item["ota_route"]["world_mutation_allowed"] = True
        report = self.validate(contract)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("client-only OTA cannot mutate world data" in error for error in report["errors"]))

    def test_both_side_cannot_claim_mcmodsync_alone(self) -> None:
        contract = copy.deepcopy(self.contract)
        item = next(row for row in contract["known_error_coverage"] if row["class"] == "both_side_mod_update")
        item["mcmodsync_alone"] = True
        report = self.validate(contract)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("BOTH-side repair cannot claim MCModSync alone" in error for error in report["errors"]))

    def test_data_migration_requires_snapshot_and_sidecar(self) -> None:
        contract = copy.deepcopy(self.contract)
        item = next(row for row in contract["known_error_coverage"] if row["class"] == "server_only_data_migration")
        item["ota_route"]["world_snapshot_required"] = False
        item["stable_identity"].pop("sidecar")
        report = self.validate(contract)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("stable_identity.sidecar missing" in error for error in report["errors"]))
        self.assertTrue(any("data migration must require a snapshot" in error for error in report["errors"]))

    def test_unknown_error_policy_must_fail_closed(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["global_invariants"]["unknown_error_policy"] = "WARN_ONLY"
        report = self.validate(contract)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("unknown errors must fail closed" in error for error in report["errors"]))

    def test_known_error_ids_are_unique(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["known_error_coverage"].append(copy.deepcopy(contract["known_error_coverage"][0]))
        report = self.validate(contract)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("not unique" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
