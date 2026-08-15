from __future__ import annotations

import json
import unittest
from pathlib import Path

from outputs.tools import audit_candidate6_bundle as audit


ROOT = Path(__file__).resolve().parents[2]


class Candidate6BundleAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = audit.load(ROOT / "outputs/final-mod-bundle-inventory-20260809.json")

    def test_digest_matches_existing_candidate5_convention(self) -> None:
        for side in ("server", "client"):
            path = ROOT / f"outputs/final-{side}-mods-candidate5-manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(audit.digest_rows(manifest["files"]), manifest["bundle_sha256"])

    def test_candidate6_contains_only_candidate5_rows_and_approved_patch(self) -> None:
        expected = {
            "server": "CF8D89759625A42E8FBA924D2A89A619825F1144892EEC1438B957BA550C15C7",
            "client": "368A5C53E75F0550BBF03079DE6930D45C3E72F6A7B298108D051FAD132E82BF",
        }
        for side in ("server", "client"):
            result = audit.audit_side(
                side,
                ROOT / f"outputs/tmp/final-{side}-mods-candidate6",
                ROOT / f"outputs/final-{side}-mods-candidate5-manifest.json",
                self.inventory,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["file_count"], 50)
            self.assertEqual(result["bundle_sha256"], expected[side])
            self.assertEqual(result["candidate5_delta"]["added"], [audit.PATCHED_PAINTING["file"]])
            self.assertEqual(result["candidate5_delta"]["removed"], [audit.PATCHED_PAINTING["replaces"]])
            self.assertEqual(result["candidate5_delta"]["changed_existing"], [])
            self.assertEqual(result["verification"]["stale_rejected_hash_hits"], [])
            self.assertEqual(result["verification"]["unclassified_files"], [])
            self.assertEqual(result["verification"]["required_inventory_components"], 24)
            self.assertEqual(result["verification"]["missing_required_inventory_components"], [])


if __name__ == "__main__":
    unittest.main()
