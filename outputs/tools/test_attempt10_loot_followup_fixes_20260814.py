from __future__ import annotations

import copy
import unittest

from outputs.tools import build_attempt10_loot_followup_fixes_20260814 as fix


def table(functions: list[dict[str, object]], weight: int = 60) -> dict[str, object]:
    return {
        "type": "minecraft:chest",
        "pools": [
            {},
            {},
            {
                "entries": [
                    {},
                    {},
                    {
                        "type": "minecraft:item",
                        "name": "minecraft:book",
                        "weight": weight,
                        "functions": functions,
                    },
                ]
            },
        ],
        "functions": [
            {"function": "minecraft:reference", "name": "nova_structures:loot_modifier"}
        ],
    }


SPEC = {"pool_index": 2, "entry_index": 2, "weight": 60}


class Attempt10LootFollowupTests(unittest.TestCase):
    def test_attempt10_empty_function_property_is_removed_only(self) -> None:
        source = table([{}])
        expected = copy.deepcopy(source)
        del expected["pools"][2]["entries"][2]["functions"]
        actual = fix.remove_attempt10_empty_function(source, SPEC, "fixture")
        self.assertEqual(actual, expected)
        self.assertEqual(source["pools"][2]["entries"][2]["functions"], [{}])

    def test_original_and_attempt10_transforms_converge(self) -> None:
        current = table([{}])
        original = table(
            [
                {
                    "options": "nova_structures:illagers_bane",
                    "function": "minecraft:enchant_randomly",
                }
            ]
        )
        self.assertEqual(
            fix.remove_attempt10_empty_function(current, SPEC, "current"),
            fix.expected_from_original(original, SPEC, "original"),
        )

    def test_wrong_function_shape_fails_closed(self) -> None:
        with self.assertRaisesRegex(fix.AuditError, "expected exactly"):
            fix.remove_attempt10_empty_function(
                table([{"function": "minecraft:set_count"}]), SPEC, "fixture"
            )

    def test_wrong_target_weight_fails_closed(self) -> None:
        with self.assertRaisesRegex(fix.AuditError, "target weight changed"):
            fix.remove_attempt10_empty_function(table([{}], weight=59), SPEC, "fixture")

    def test_empty_function_path_scan_is_exact(self) -> None:
        value = {
            "functions": [{}, {"function": "minecraft:set_count"}],
            "nested": [{"functions": [{}]}],
            "unrelated": {},
        }
        self.assertEqual(
            fix.empty_function_paths(value),
            ["$.functions[0]", "$.nested[0].functions[0]"],
        )

    def test_original_wrong_enchantment_fails_closed(self) -> None:
        wrong = table(
            [
                {
                    "options": "minecraft:smite",
                    "function": "minecraft:enchant_randomly",
                }
            ]
        )
        with self.assertRaisesRegex(fix.AuditError, "original unavailable enchant function changed"):
            fix.expected_from_original(wrong, SPEC, "fixture")


if __name__ == "__main__":
    unittest.main()
