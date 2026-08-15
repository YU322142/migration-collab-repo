from __future__ import annotations

import unittest

import audit_loaded_region_losses as audit


class AttachedEntityClassificationTests(unittest.TestCase):
    def test_hanging_entity_ids_are_complete_and_super_glue_is_excluded(self):
        expected = {
            "minecraft:painting",
            "minecraft:item_frame",
            "minecraft:glow_item_frame",
            "minecraft:leash_knot",
            "immersive_paintings:painting",
            "immersive_paintings:glow_painting",
            "immersive_paintings:graffiti",
            "immersive_paintings:glow_graffiti",
        }
        self.assertEqual(audit.ATTACHED_IDS, expected)
        self.assertNotIn("create:super_glue", audit.ATTACHED_IDS)


if __name__ == "__main__":
    unittest.main()
