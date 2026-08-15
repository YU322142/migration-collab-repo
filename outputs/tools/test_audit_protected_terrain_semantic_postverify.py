from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_protected_terrain_semantic_postverify as audit


def pack(values: list[int], bits: int) -> list[int]:
    per_long = 64 // bits
    result = [0] * ((len(values) + per_long - 1) // per_long)
    mask = (1 << bits) - 1
    for index, value in enumerate(values):
        result[index // per_long] |= (value & mask) << ((index % per_long) * bits)
    return result


def chunk(block_states: dict, heightmaps: dict | None = None) -> dict:
    return {
        "xPos": 1,
        "zPos": 2,
        "sections": [
            {
                "Y": 0,
                "block_states": block_states,
                "biomes": {"palette": ["minecraft:plains"]},
            }
        ],
        "structures": {"starts": {}, "References": {}},
        "Heightmaps": heightmaps or {},
    }


class SemanticPostverifyTest(unittest.TestCase):
    def test_palette_order_and_packing_are_semantically_equal(self) -> None:
        first_indices = [index & 1 for index in range(4096)]
        second_indices = [1 - value for value in first_indices]
        first = chunk(
            {
                "palette": [{"Name": "minecraft:stone"}, {"Name": "minecraft:air"}],
                "data": pack(first_indices, 4),
            }
        )
        second = chunk(
            {
                "palette": [{"Name": "minecraft:air"}, {"Name": "minecraft:stone"}],
                "data": pack(second_indices, 4),
            }
        )
        self.assertEqual([], audit.compare_chunk(first, second))

    def test_real_block_change_is_detected(self) -> None:
        stone = chunk({"palette": [{"Name": "minecraft:stone"}]})
        dirt = chunk({"palette": [{"Name": "minecraft:dirt"}]})
        self.assertEqual(["blocks"], audit.compare_chunk(stone, dirt))

    def test_37_and_43_long_heightmaps_compare_by_values(self) -> None:
        values = [(index * 3) & 0x1FF for index in range(256)]
        old = chunk(
            {"palette": [{"Name": "minecraft:stone"}]},
            {"WORLD_SURFACE": pack(values, 9)},
        )
        new = chunk(
            {"palette": [{"Name": "minecraft:stone"}]},
            {"WORLD_SURFACE": pack(values, 10)},
        )
        self.assertEqual(37, len(old["Heightmaps"]["WORLD_SURFACE"]))
        self.assertEqual(43, len(new["Heightmaps"]["WORLD_SURFACE"]))
        self.assertEqual([], audit.compare_chunk(old, new))

    def test_tick_and_light_bookkeeping_are_ignored(self) -> None:
        first = chunk({"palette": [{"Name": "minecraft:stone"}]})
        second = chunk({"palette": [{"Name": "minecraft:stone"}]})
        first["block_ticks"] = [{"i": "minecraft:water"}]
        first["fluid_ticks"] = [{"i": "minecraft:water"}]
        first["sections"][0]["BlockLight"] = [1, 2, 3]
        self.assertEqual([], audit.compare_chunk(first, second))


if __name__ == "__main__":
    unittest.main()
