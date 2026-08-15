from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import nbtlib


MODULE_PATH = Path(__file__).with_name("probe_cutover_chunks.py")
SPEC = importlib.util.spec_from_file_location("probe_cutover_chunks", MODULE_PATH)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


def save(path: Path, data: nbtlib.Compound, version: int = 4671) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nbtlib.File(
        {"DataVersion": nbtlib.Int(version), "data": data}, gzipped=True
    ).save(path, gzipped=True)


class ProbeCutoverChunksTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = os.environ.get("MIGRATION_TEST_TMPDIR")
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.world = Path(self.temp.name) / "world"
        self.write_modern("data/chunks.dat", forced=[(1, 2)])
        self.write_modern("DIM-1/data/chunks.dat", forced=[])
        self.write_modern("DIM1/data/chunks.dat", forced=[])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_modern(
        self,
        relative: str,
        *,
        forced: list[tuple[int, int]],
        portal: list[tuple[int, int, int]] | None = None,
    ) -> None:
        tickets: list[nbtlib.Compound] = []
        for x, z in forced:
            tickets.append(
                nbtlib.Compound(
                    {
                        "type": nbtlib.String("minecraft:forced"),
                        "chunk_pos": nbtlib.IntArray([x, z]),
                        "level": nbtlib.Int(31),
                    }
                )
            )
        for x, z, ticks_left in portal or []:
            tickets.append(
                nbtlib.Compound(
                    {
                        "type": nbtlib.String("minecraft:portal"),
                        "chunk_pos": nbtlib.IntArray([x, z]),
                        "level": nbtlib.Int(30),
                        "ticks_left": nbtlib.Long(ticks_left),
                    }
                )
            )
        save(self.world / relative, nbtlib.Compound({"tickets": nbtlib.List(tickets)}))

    def test_zero_portal_is_ready_and_reports_all_dimensions(self) -> None:
        report = probe.probe_world(self.world)
        self.assertEqual(report["status"], "READY_PORTAL_ZERO")
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual([item["dimension"] for item in report["dimensions"]], [
            "overworld", "the_nether", "the_end"
        ])
        self.assertEqual(report["totals"], {"ticket_count": 1, "forced_count": 1, "portal_count": 0})
        self.assertTrue(all(item["status"] == "OK" for item in report["dimensions"]))
        self.assertTrue(all(item.get("sha256") for item in report["dimensions"]))

    def test_portal_ticket_blocks_and_cli_returns_two(self) -> None:
        self.write_modern("DIM-1/data/chunks.dat", forced=[], portal=[(7, -2, 17)])
        report = probe.probe_world(self.world)
        self.assertEqual(report["status"], "BLOCKED_PORTAL_TICKETS")
        self.assertEqual(report["totals"]["portal_count"], 1)
        nether = next(item for item in report["dimensions"] if item["dimension"] == "the_nether")
        self.assertEqual(nether["portal"][0]["ticks_left"], 17)
        completed = subprocess.run(
            [sys.executable, str(MODULE_PATH), str(self.world)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "BLOCKED_PORTAL_TICKETS")

    def test_unknown_data_version_and_missing_dimension_block(self) -> None:
        save(self.world / "data/chunks.dat", nbtlib.Compound({"tickets": nbtlib.List()}), 9999)
        (self.world / "DIM1/data/chunks.dat").unlink()
        report = probe.probe_world(self.world)
        self.assertEqual(report["status"], "BLOCKED_SCHEMA")
        self.assertEqual(report["exit_code"], 2)
        self.assertTrue(any("DataVersion" in blocker for blocker in report["blockers"]))
        self.assertTrue(any("missing" in blocker for blocker in report["blockers"]))

    def test_unknown_ticket_shape_blocks_without_touching_source(self) -> None:
        path = self.world / "data/chunks.dat"
        save(
            path,
            nbtlib.Compound(
                {
                    "tickets": nbtlib.List(
                        [
                            nbtlib.Compound(
                                {
                                    "type": nbtlib.String("minecraft:custom"),
                                    "chunk_pos": nbtlib.IntArray([0, 0]),
                                    "level": nbtlib.Int(31),
                                }
                            )
                        ]
                    )
                }
            ),
        )
        before_probe = path.read_bytes()
        report = probe.probe_world(self.world)
        self.assertEqual(report["status"], "BLOCKED_SCHEMA")
        self.assertTrue(any("unsupported ticket type" in blocker for blocker in report["blockers"]))
        self.assertEqual(path.read_bytes(), before_probe)

    def test_target_schema_and_mod_forced_are_counted(self) -> None:
        save(
            self.world / "data/chunks.dat",
            nbtlib.Compound(
                {
                    "Forced": nbtlib.LongArray([123]),
                    "ModForced": nbtlib.List(
                        [
                            nbtlib.Compound(
                                {
                                    "Controller": nbtlib.String("example:loader"),
                                    "ModForced": nbtlib.List(),
                                }
                            )
                        ]
                    ),
                }
            ),
            3955,
        )
        report = probe.probe_world(self.world)
        overworld = report["dimensions"][0]
        self.assertEqual(overworld["schema"], "target-forced")
        self.assertEqual(overworld["forced_count"], 1)
        self.assertEqual(overworld["mod_forced_controllers"], 1)
        self.assertEqual(report["status"], "READY_PORTAL_ZERO")

    def test_report_inside_source_is_rejected_before_any_write(self) -> None:
        destination = self.world / "probe-report.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                str(self.world),
                "--report",
                str(destination),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(destination.exists())
        self.assertEqual(json.loads(completed.stdout)["status"], "BLOCKED_SCHEMA")


if __name__ == "__main__":
    unittest.main()
