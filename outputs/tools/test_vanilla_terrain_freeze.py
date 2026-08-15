#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

import nbtlib


MODULE_PATH = Path(__file__).with_name("vanilla_terrain_freeze.py")
SPEC = importlib.util.spec_from_file_location("vanilla_terrain_freeze", MODULE_PATH)
assert SPEC and SPEC.loader
vtf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vtf)


def write_empty_region(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * 8192)


def write_single_chunk(path: Path, slot: int, chunk_x: int, chunk_z: int, data_version: int = 3955) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    root = nbtlib.File(
        {
            "DataVersion": nbtlib.Int(data_version),
            "xPos": nbtlib.Int(chunk_x),
            "zPos": nbtlib.Int(chunk_z),
            "Status": nbtlib.String("minecraft:full"),
        }
    )
    import io
    import zlib

    raw_stream = io.BytesIO()
    root.write(raw_stream, byteorder="big")
    payload = zlib.compress(raw_stream.getvalue())
    record = struct.pack(">I", len(payload) + 1) + b"\x02" + payload
    record += b"\0" * ((4096 - len(record) % 4096) % 4096)
    sectors = len(record) // 4096
    location = bytearray(4096)
    location[slot * 4 : slot * 4 + 3] = (2).to_bytes(3, "big")
    location[slot * 4 + 3] = sectors
    path.write_bytes(bytes(location) + b"\0" * 4096 + record)


class GeometryTests(unittest.TestCase):
    def test_constants_and_chunk_counts(self) -> None:
        self.assertEqual((vtf.CENTER_X >> 4, vtf.CENTER_Z >> 4), (637, -99))
        self.assertEqual(len(vtf.chunky_chunks(1000)), 12260)
        self.assertEqual(len(vtf.chunky_chunks(1536)), 28950)
        self.assertEqual(len(vtf.regions_for_chunks(vtf.chunky_chunks(1536))), 40)

    def test_freeze_radius_covers_every_core_intersection(self) -> None:
        freeze = set(vtf.chunky_chunks(vtf.FREEZE_RADIUS))
        core_intersections = set(vtf.intersecting_chunks(vtf.CORE_RADIUS))
        self.assertTrue(core_intersections <= freeze)
        self.assertGreater(len(freeze), len(core_intersections))

    def test_negative_region_and_slot_math(self) -> None:
        self.assertEqual(vtf.floor_div(-1, 32), -1)
        self.assertEqual(vtf.slot_for_chunk(637, -99), (637 & 31) + (-99 & 31) * 32)

    def test_ring_sampling_density(self) -> None:
        points = vtf.sample_ring_points()
        self.assertGreaterEqual(len(points), 3500)
        self.assertEqual({row[0] for row in points}, {1504, 1520, 1536, 1552, 1568})

    def test_compact_array_round_trip(self) -> None:
        bits = 9
        values = [(index * 17) & ((1 << bits) - 1) for index in range(256)]
        values_per_long = 64 // bits
        packed = [0] * ((len(values) + values_per_long - 1) // values_per_long)
        for index, value in enumerate(values):
            packed[index // values_per_long] |= value << ((index % values_per_long) * bits)
        self.assertEqual(vtf.unpack_compact_array(packed, bits, len(values)), values)

    def test_decode_signed_chunk_pos(self) -> None:
        x, z = -123, 456
        encoded = (x & 0xFFFFFFFF) | ((z & 0xFFFFFFFF) << 32)
        self.assertEqual(vtf.decode_chunk_pos(encoded), (x, z))


class RegionTests(unittest.TestCase):
    def test_empty_region_has_no_slots(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "r.0.0.mca"
            write_empty_region(path)
            self.assertEqual(vtf.read_location_table(path), {})

    def test_single_chunk_round_trip_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "r.19.-4.mca"
            chunk_x, chunk_z = 637, -99
            slot = vtf.slot_for_chunk(chunk_x, chunk_z)
            write_single_chunk(path, slot, chunk_x, chunk_z)
            rows = list(vtf.iter_region_chunks(path))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], slot)
            self.assertEqual(int(rows[0][1]["DataVersion"]), 3955)

    def test_reject_external_chunk_stream(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "r.0.0.mca"
            location = bytearray(8192)
            location[:3] = (2).to_bytes(3, "big")
            location[3] = 1
            location.extend(struct.pack(">I", 1) + b"\x82" + b"\0" * (4096 - 5))
            path.write_bytes(location)
            with self.assertRaisesRegex(ValueError, "external"):
                list(vtf.iter_region_chunks(path))


class GateTests(unittest.TestCase):
    def test_manifest_hash_drift_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            world = root / "world"
            path = world / "region" / "r.0.0.mca"
            write_empty_region(path)
            manifest = {
                "status": "PASS",
                "files": [
                    {
                        "relative_path": "region/r.0.0.mca",
                        "sha256": vtf.sha256(path),
                    }
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(vtf.manifest_gate(world, manifest_path)["status"], "PASS")
            path.write_bytes(path.read_bytes() + b"drift")
            result = vtf.manifest_gate(world, manifest_path)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertIn("hash drift", result["blockers"][0]["reason"])

    def test_boundary_gate_pass_and_fail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base_samples = []
            full_samples = []
            for index in range(100):
                row = {
                    "x": index,
                    "z": 0,
                    "heightmaps": {name: 70 for name in vtf.HEIGHTMAPS},
                    "ocean": False,
                    "unsupported_fluid_columns": 0,
                    "missing_structure_references": 0,
                }
                base_samples.append(dict(row))
                full_row = json.loads(json.dumps(row))
                full_row["boundary_adjacent_step"] = 1
                full_samples.append(full_row)
            base_path = root / "base.json"
            full_path = root / "full.json"
            out_path = root / "gate.json"
            base_path.write_text(json.dumps({"seed": vtf.EXPECTED_SEED, "samples": base_samples}), encoding="utf-8")
            full_path.write_text(json.dumps({"seed": vtf.EXPECTED_SEED, "samples": full_samples}), encoding="utf-8")
            self.assertEqual(vtf.boundary_gate(base_path, full_path, out_path)["status"], "PASS")
            full_samples[0]["heightmaps"]["WORLD_SURFACE"] = 100
            full_path.write_text(json.dumps({"seed": vtf.EXPECTED_SEED, "samples": full_samples}), encoding="utf-8")
            self.assertEqual(vtf.boundary_gate(base_path, full_path, out_path)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
