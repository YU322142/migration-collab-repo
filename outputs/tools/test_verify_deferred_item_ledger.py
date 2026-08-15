from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("verify_deferred_item_ledger.py")
SPEC = importlib.util.spec_from_file_location("verify_deferred_item_ledger", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)


OWNER_UUID = [0, 16384, -2147483648, 2]


def record(label: str, path: str, *, count: int = 1, owner_uuid=None, stack_extra=None):
    stack = {"id": ledger.TARGET_ITEM, "count": count}
    if stack_extra:
        stack.update(stack_extra)
    return {
        "root_label": label,
        "file": "entities/r.-1.-1.mca",
        "path": path,
        "count_key": "count",
        "count": count,
        "slot": None,
        "components": stack.get("components", {}),
        "legacy_tag": {},
        "stack": stack,
        "owner": {
            "path": "Entities[1]",
            "id": "minecraft:horse",
            "UUID": OWNER_UUID if owner_uuid is None else owner_uuid,
            "Pos": [-229.2, 63.0, -43.8],
        },
        "mca_slot": 945,
        "compression": 2,
    }


def report(rows):
    return {
        "schema": 1,
        "status": "PASS",
        "read_only": True,
        "target_item": ledger.TARGET_ITEM,
        "totals": {"errors": 0},
        "matches": rows,
    }


class DeferredLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.baseline = self.root / "baseline.json"
        self.runtime1 = self.root / "runtime1.json"
        self.runtime2 = self.root / "runtime2.json"
        self.write(
            self.baseline,
            report([
                record("source", "Entities[1].equipment.body"),
                record("staging", "Entities[1].body_armor_item"),
            ]),
        )
        self.write(self.runtime1, report([record("runtime", "Entities[7].body_armor_item")]))
        self.write(self.runtime2, report([record("runtime", "Entities[3].body_armor_item")]))

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path: Path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def bindings(self):
        return [
            ("runtime_round_1_after_stop", self.runtime1, "runtime"),
            ("runtime_round_2_after_stop", self.runtime2, "runtime"),
        ]

    def test_full_four_boundary_ledger_passes(self):
        result = ledger.verify(self.baseline, self.bindings())
        self.assertEqual("PASS", result["status"])
        self.assertEqual("00000000-0000-4000-8000-000000000002", result["protected_owner_uuid"])
        self.assertEqual([], result["blockers"])

    def test_baseline_only_is_explicitly_pending(self):
        result = ledger.verify(self.baseline, [])
        self.assertEqual("BASELINE_LOCKED_RUNTIME_PENDING", result["status"])
        self.assertEqual(2, len(result["blockers"]))

    def test_owner_uuid_drift_is_rejected(self):
        self.write(
            self.runtime1,
            report([record("runtime", "Entities[7].body_armor_item", owner_uuid=[1, 2, 3, 4])]),
        )
        with self.assertRaisesRegex(ValueError, "owner_uuid"):
            ledger.verify(self.baseline, self.bindings())

    def test_stack_component_drift_is_rejected(self):
        self.write(
            self.runtime2,
            report([record(
                "runtime",
                "Entities[3].body_armor_item",
                stack_extra={"components": {"minecraft:custom_data": {"lost": 1}}},
            )]),
        )
        with self.assertRaisesRegex(ValueError, "canonical_stack_sha256"):
            ledger.verify(self.baseline, self.bindings())

    def test_duplicate_or_missing_occurrence_is_rejected(self):
        self.write(self.runtime1, report([]))
        with self.assertRaisesRegex(ValueError, "exactly one occurrence"):
            ledger.verify(self.baseline, self.bindings())

    def test_wrong_target_slot_is_rejected(self):
        self.write(self.runtime1, report([record("runtime", "Entities[7].Inventory[0]")]))
        with self.assertRaisesRegex(ValueError, "protected slot mismatch"):
            ledger.verify(self.baseline, self.bindings())


if __name__ == "__main__":
    unittest.main()
