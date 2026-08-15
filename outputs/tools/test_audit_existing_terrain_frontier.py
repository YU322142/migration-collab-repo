#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_existing_terrain_frontier.py")
SPEC = importlib.util.spec_from_file_location("audit_existing_terrain_frontier", MODULE_PATH)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def write_region(path: Path, slots: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    locations = bytearray(4096)
    timestamps = bytearray(4096)
    records: list[bytes] = []
    next_sector = 2
    for slot in slots:
        payload = b"\x03\x0a\x00\x00\x00"  # uncompressed empty root compound
        record = struct.pack(">I", len(payload)) + payload
        record += b"\0" * (4096 - len(record))
        locations[slot * 4 : slot * 4 + 3] = next_sector.to_bytes(3, "big")
        locations[slot * 4 + 3] = 1
        records.append(record)
        next_sector += 1
    path.write_bytes(bytes(locations) + bytes(timestamps) + b"".join(records))


class FrontierTests(unittest.TestCase):
    def test_scan_counts_all_edges_and_verify_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            world = root / "world"
            # Two horizontally adjacent chunks: (0,0) and (1,0).
            write_region(world / "region" / "r.0.0.mca", [0, 1])
            baseline = root / "baseline.json"
            result = mod.audit(world, baseline)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["terrain"]["occupied_chunk_count"], 2)
            self.assertEqual(result["frontier"]["edge_count"], 6)
            self.assertEqual(result["frontier"]["adjacent_ungenerated_chunk_count"], 6)
            check = mod.verify(world, baseline, root / "check.json")
            self.assertEqual(check["status"], "PASS")
            path = world / "region" / "r.0.0.mca"
            path.write_bytes(path.read_bytes() + b"drift")
            check = mod.verify(world, baseline, root / "check2.json")
            self.assertEqual(check["status"], "BLOCKED")

    def test_invalid_allocation_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            world = root / "world"
            path = world / "region" / "r.0.0.mca"
            path.parent.mkdir(parents=True)
            table = bytearray(8192)
            table[:3] = (99).to_bytes(3, "big")
            table[3] = 1
            path.write_bytes(table)
            result = mod.audit(world, root / "baseline.json")
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(result["blockers"])


if __name__ == "__main__":
    unittest.main()
