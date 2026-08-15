from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest

import nbtlib


TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import audit_deferred_item_checkpoint as checkpoint


class DeferredItemCheckpointTests(unittest.TestCase):
    def test_empty_world_is_a_read_only_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = checkpoint.audit(Path(temporary), "runtime", 2)
        self.assertEqual("PASS", report["status"])
        self.assertTrue(report["read_only"])
        self.assertEqual(0, report["totals"]["files"])
        self.assertEqual([], report["matches"])

    def test_standalone_nbt_occurrence_is_found(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entity = nbtlib.Compound(
                {
                    "id": nbtlib.String("minecraft:horse"),
                    "UUID": nbtlib.IntArray([2122618487, 1093225455, -1230495970, -500396323]),
                    "body_armor_item": nbtlib.Compound(
                        {
                            "id": nbtlib.String(checkpoint.scanner.TARGET_ITEM),
                            "count": nbtlib.Int(1),
                        }
                    ),
                }
            )
            nbtlib.File({"Entity": entity}).save(root / "fixture.dat", gzipped=True)
            report = checkpoint.audit(root, "runtime", 2)
        self.assertEqual("PASS", report["status"])
        self.assertEqual(1, report["totals"]["matches"])
        self.assertEqual("runtime", report["matches"][0]["root_label"])
        self.assertEqual("Entity.body_armor_item", report["matches"][0]["path"])


if __name__ == "__main__":
    unittest.main()
