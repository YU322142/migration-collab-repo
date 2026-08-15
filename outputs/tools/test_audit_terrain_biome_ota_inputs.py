#!/usr/bin/env python3

from __future__ import annotations

import gzip
import importlib.util
import io
import math
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

import nbtlib


MODULE_PATH = Path(__file__).with_name("audit_terrain_biome_ota_inputs.py")
SPEC = importlib.util.spec_from_file_location("audit_terrain_biome_ota_inputs", MODULE_PATH)
assert SPEC and SPEC.loader
ota = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ota
SPEC.loader.exec_module(ota)


def nbt_bytes(root: nbtlib.File) -> bytes:
    stream = io.BytesIO()
    root.write(stream, byteorder="big")
    return stream.getvalue()


def write_level(world: Path, seed: int = 1234) -> None:
    world.mkdir(parents=True, exist_ok=True)
    root = nbtlib.File(
        {
            "Data": nbtlib.Compound(
                {
                    "DataVersion": nbtlib.Int(3955),
                    "WorldGenSettings": nbtlib.Compound(
                        {
                            "seed": nbtlib.Long(seed),
                            "dimensions": nbtlib.Compound(
                                {
                                    "minecraft:overworld": nbtlib.Compound(
                                        {
                                            "generator": nbtlib.Compound(
                                                {"type": nbtlib.String("minecraft:noise")}
                                            )
                                        }
                                    )
                                }
                            ),
                        }
                    ),
                }
            )
        }
    )
    (world / "level.dat").write_bytes(gzip.compress(nbt_bytes(root)))


def chunk_nbt(block: str) -> nbtlib.File:
    return nbtlib.File(
        {
            "DataVersion": nbtlib.Int(3955),
            "xPos": nbtlib.Int(0),
            "zPos": nbtlib.Int(0),
            "Status": nbtlib.String("minecraft:full"),
            "sections": nbtlib.List[nbtlib.Compound](
                [
                    nbtlib.Compound(
                        {
                            "Y": nbtlib.Byte(0),
                            "block_states": nbtlib.Compound(
                                {
                                    "palette": nbtlib.List[nbtlib.Compound](
                                        [nbtlib.Compound({"Name": nbtlib.String(block)})]
                                    )
                                }
                            ),
                            "biomes": nbtlib.Compound(
                                {
                                    "palette": nbtlib.List[nbtlib.String](
                                        [nbtlib.String("minecraft:plains")]
                                    )
                                }
                            ),
                        }
                    )
                ]
            ),
            "block_entities": nbtlib.List[nbtlib.Compound]([]),
            "structures": nbtlib.Compound({}),
            "block_ticks": nbtlib.List[nbtlib.Compound]([]),
            "fluid_ticks": nbtlib.List[nbtlib.Compound]([]),
            "PostProcessing": nbtlib.List[nbtlib.List]([]),
            "Heightmaps": nbtlib.Compound({}),
        }
    )


def write_chunk(world: Path, block: str) -> None:
    path = world / "region" / "r.0.0.mca"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = zlib.compress(nbt_bytes(chunk_nbt(block)))
    record = struct.pack(">I", len(payload) + 1) + b"\x02" + payload
    record += b"\0" * ((4096 - len(record) % 4096) % 4096)
    location = bytearray(4096)
    location[0:3] = (2).to_bytes(3, "big")
    location[3] = len(record) // 4096
    path.write_bytes(bytes(location) + b"\0" * 4096 + record)


def make_world(root: Path, name: str, block: str) -> Path:
    world = root / name
    write_level(world)
    write_chunk(world, block)
    return world


class GeometryTests(unittest.TestCase):
    def test_protected_selection(self) -> None:
        core = set(ota.selected_chunks(10_192, -1_574, 1_000))
        freeze = set(ota.selected_chunks(10_192, -1_574, 1_536))
        legacy_center_rule = {
            (x, z)
            for x in range((10_192 >> 4) - 96, (10_192 >> 4) + 97)
            for z in range((-1_574 >> 4) - 96, (-1_574 >> 4) + 97)
            if math.hypot(x * 16 + 8 - 10_192, z * 16 + 8 + 1_574) <= 1_536
        }
        self.assertEqual(len(core), 12_500)
        self.assertEqual(len(freeze), 29_305)
        self.assertEqual(len(legacy_center_rule), 28_950)
        self.assertEqual(len(freeze - legacy_center_rule), 355)
        self.assertEqual(len({(x // 32, z // 32) for x, z in freeze}), 40)
        self.assertTrue(core <= freeze)

    def test_boundary_chunk_is_selected_by_integer_block_intersection(self) -> None:
        # Chunk (1, 0) contains x=16..31.  Its centre (24, 8) lies outside a
        # radius-16 circle around (0, 0), but block (16, 0) lies on the circle.
        self.assertIn((1, 0), ota.selected_chunks(0, 0, 16))


class ClassificationTests(unittest.TestCase):
    def test_safe_replace_when_current_equals_bad_base(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            current = make_world(root, "current", "minecraft:dirt")
            base = make_world(root, "base", "minecraft:dirt")
            desired = make_world(root, "desired", "minecraft:stone")
            report = ota.audit(current, desired, base, 8, 8, 1, False)
            self.assertEqual(
                report["classification_counts"],
                {"SAFE_COMPONENT_REPLACE_UNTOUCHED_BAD_BASE": 1},
            )
            self.assertEqual(report["status"], "INPUTS_CLASSIFIED_FOR_PATCH_BUILD")

    def test_changed_current_requires_three_way(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            current = make_world(root, "current", "minecraft:cobblestone")
            base = make_world(root, "base", "minecraft:dirt")
            desired = make_world(root, "desired", "minecraft:stone")
            report = ota.audit(current, desired, base, 8, 8, 1, False)
            self.assertEqual(
                report["classification_counts"],
                {"THREE_WAY_REQUIRED_CURRENT_WINS_ON_CONFLICT": 1},
            )
            self.assertEqual(report["status"], "REQUIRES_REGISTRY_AWARE_THREE_WAY_ENGINE")

    def test_missing_base_blocks_automatic_repair(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            current = make_world(root, "current", "minecraft:dirt")
            desired = make_world(root, "desired", "minecraft:stone")
            report = ota.audit(current, desired, None, 8, 8, 1, False)
            self.assertEqual(
                report["classification_counts"],
                {"BLOCKED_NO_EXACT_BAD_BASE": 1},
            )
            self.assertEqual(report["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
