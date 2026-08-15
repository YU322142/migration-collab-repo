from __future__ import annotations

import sys
import unittest
from pathlib import Path

import nbtlib


TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import audit_candidate13_netherite_horse_armor as horse_audit
import audit_candidate13_scarecrow_schema as scarecrow_audit
from candidate13_nbt_audit_common import known_non_nbt_reason, path_text, tag_type


class Candidate13NbtAuditTests(unittest.TestCase):
    def test_tag_type_normalises_specialised_nbtlib_list(self):
        value = nbtlib.List[nbtlib.Compound]([])
        self.assertEqual(tag_type(value), "List")

    def test_path_text(self):
        self.assertEqual(path_text(["Entities", 0, "ArmorItems", 1]), "Entities[0].ArmorItems[1]")

    def test_bukkit_uid_is_explicit_known_non_nbt(self):
        self.assertIsNotNone(known_non_nbt_reason(Path("world/uid.dat")))
        self.assertIsNone(known_non_nbt_reason(Path("world/data/map_1.dat")))

    def test_horse_armor_requires_real_integer_count(self):
        fake = nbtlib.Compound({"id": nbtlib.String(horse_audit.TARGET_ITEM)})
        found = []
        horse_audit._walk(fake, [], [], found)
        self.assertEqual(found, [])

    def test_horse_armor_records_components_and_owner(self):
        stack = nbtlib.Compound(
            {
                "id": nbtlib.String(horse_audit.TARGET_ITEM),
                "count": nbtlib.Int(1),
                "components": nbtlib.Compound({"example:test": nbtlib.Int(7)}),
            }
        )
        entity = nbtlib.Compound(
            {
                "id": nbtlib.String("minecraft:horse"),
                "Pos": nbtlib.List[nbtlib.Double]([0.0, 64.0, 0.0]),
                "equipment": nbtlib.Compound({"body": stack}),
            }
        )
        found = []
        horse_audit._walk(entity, [], [], found)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["count"], 1)
        self.assertEqual(found[0]["components"], {"example:test": 7})
        self.assertEqual(found[0]["owner"]["id"], "minecraft:horse")

    def test_scarecrow_source_list_schema(self):
        entity = nbtlib.Compound(
            {
                "id": nbtlib.String(scarecrow_audit.SCARECROW_ID),
                "ArmorItems": nbtlib.List[nbtlib.Compound](
                    [
                        nbtlib.Compound(
                            {
                                "Slot": nbtlib.Int(3),
                                "id": nbtlib.String("minecraft:dragon_head"),
                                "count": nbtlib.Int(1),
                            }
                        )
                    ]
                ),
            }
        )
        summary = scarecrow_audit._slot_summary(entity, "ArmorItems")
        self.assertEqual(summary["tag_type"], "List")
        self.assertEqual(summary["list_length"], 1)
        self.assertEqual(summary["slots"], [3])
        self.assertTrue(summary["source_list_valid"])
        self.assertFalse(summary["target_handler_compound_valid"])

    def test_scarecrow_target_handler_schema(self):
        entity = nbtlib.Compound(
            {
                "ArmorItems": nbtlib.Compound(
                    {
                        "Size": nbtlib.Int(4),
                        "Items": nbtlib.List[nbtlib.Compound]([]),
                    }
                )
            }
        )
        summary = scarecrow_audit._slot_summary(entity, "ArmorItems")
        self.assertEqual(summary["tag_type"], "Compound")
        self.assertTrue(summary["target_handler_compound_valid"])


if __name__ == "__main__":
    unittest.main()
