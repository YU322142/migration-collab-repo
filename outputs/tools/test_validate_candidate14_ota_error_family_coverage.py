from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("validate_candidate14_ota_error_family_coverage.py")
SPEC = importlib.util.spec_from_file_location("family_validator", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class Candidate14OtaErrorFamilyCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matrix = json.loads(validator.DEFAULT_MATRIX.read_text(encoding="utf-8"))

    def check(self, matrix):
        return validator.validate(matrix, validator.DEFAULT_MATRIX)

    def test_authoritative_matrix_passes(self) -> None:
        report = self.check(copy.deepcopy(self.matrix))
        self.assertEqual("PASS", report["status"], report["errors"])
        self.assertEqual(15, report["family_count"])

    def test_client_family_cannot_require_server_stop(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        row = next(x for x in matrix["families"] if x["route_class"] == "client_only_ota")
        row["requires_server_short_shutdown"] = True
        report = self.check(matrix)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("client-only route cannot need server stop" in e for e in report["errors"]))

    def test_client_family_without_mcmodsync_or_external_dependency_is_blocked(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        row = next(x for x in matrix["families"] if x["route_class"] == "client_only_ota" and not x["external_dependency"])
        row["mcmodsync_alone"] = False
        report = self.check(matrix)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("MCModSync or declare an external publication dependency" in e for e in report["errors"]))

    def test_data_family_cannot_claim_mcmodsync_alone(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        row = next(x for x in matrix["families"] if x["route_class"] == "server_only_data_migration")
        row["mcmodsync_alone"] = True
        report = self.check(matrix)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("data route cannot claim MCModSync alone" in e for e in report["errors"]))

    def test_duplicate_family_id_is_blocked(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["families"].append(copy.deepcopy(matrix["families"][0]))
        report = self.check(matrix)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("family IDs are not unique" in e for e in report["errors"]))

    def test_permanent_mod_cap_invariant_is_blocked(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["invariants"]["current_mod_count_is_not_a_permanent_cap"] = False
        report = self.check(matrix)
        self.assertEqual("NO_GO", report["status"])
        self.assertTrue(any("current_mod_count_is_not_a_permanent_cap" in e for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
