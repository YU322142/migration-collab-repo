from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_schematicannon_corrected_smoke.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("schematicannon_corrected_audit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class CorrectedSchematicannonAuditTest(unittest.TestCase):
    def test_conversion_gate_requires_all_four_production_cannons(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            target = Path(temporary_dir) / "target"
            target.mkdir()
            report = Path(temporary_dir) / "world-convert.json"
            value = {
                "world": str(target / "world"),
                "schematicannon_inventory_conversions": [
                    {"x": x, "y": y, "z": z}
                    for x, y, z in audit.EXPECTED_CANNON_POSITIONS
                ],
                "unsupported_block_entities": [],
                "malformed_regions": [],
            }
            report.write_text(json.dumps(value), encoding="utf-8")
            result = audit.conversion_gate(report, target)
            self.assertEqual("PASS", result["status"])
            self.assertEqual(4, result["conversion_count"])

            value["schematicannon_inventory_conversions"].pop()
            report.write_text(json.dumps(value), encoding="utf-8")
            result = audit.conversion_gate(report, target)
            self.assertEqual("FAIL", result["status"])
            self.assertIn("CONVERSION_COUNT_MISMATCH", result["blockers"])

    def test_markdown_reports_each_cannon(self):
        value = {
            "status": "PASS",
            "conversion": {"conversion_count": 4},
            "runs": {"run1": {"status": "PASS"}, "run2": {"status": "PASS"}},
            "schematicannons": {
                "status": "PASS",
                "lost_item_units": 0,
                "comparisons": [
                    {
                        "position": [-12, 64, 9],
                        "status": "PASS",
                        "target": {
                            "inventory": {
                                "encoding": "neoforge_item_handler_compound",
                                "items": [
                                    {"slot": 4, "id": "minecraft:gunpowder", "count": 23}
                                ],
                            }
                        },
                    }
                ],
            },
            "blockers": [],
        }
        text = audit.markdown(value)
        self.assertIn("minecraft:gunpowder x23", text)
        self.assertIn("None in this bounded gate", text)


if __name__ == "__main__":
    unittest.main()
