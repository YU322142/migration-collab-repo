from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("probe_cutover_delta.py")
SPEC = importlib.util.spec_from_file_location("probe_cutover_delta", MODULE_PATH)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


def entry(name: str, *, kind: str = "world-region-nbt", digest: str = "a" * 64) -> dict:
    return {
        "source": name,
        "target": name,
        "kind": kind,
        "bytes": 4,
        "sha256": digest,
    }


class ProbeCutoverDeltaTest(unittest.TestCase):
    def report(self, delta: dict) -> dict:
        baseline = {
            "staging_root": "D:\\audit\\staging",
            "files": 1,
            "bytes": 4,
            "snapshot_sha256": "b" * 64,
        }
        current = {
            "files": 1,
            "bytes": 4,
            "snapshot_sha256": "c" * 64,
        }
        return probe.build_report(
            Path("D:\\source"),
            Path("D:\\audit\\baseline.json"),
            baseline,
            current,
            delta,
            first_pass_seconds=1.25,
            stability_pass_seconds=1.5,
            lock_probe={"status": "UNLOCKED_READ_ONLY_PROBE"},
        )

    def test_unchanged_snapshot_is_stable_and_ready(self) -> None:
        report = self.report(
            {"added": [], "modified": [], "deleted": [], "metadata_only": [], "unchanged": 1}
        )
        self.assertEqual(report["status"], "STABLE_NO_CONTENT_DELTA")
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["timing"]["total_seconds"], 2.75)
        self.assertEqual(report["delta"]["selected_regions"], [])

    def test_modified_region_is_selected_for_incremental_refresh(self) -> None:
        old = entry("world/entities/r.1.-2.mca", digest="a" * 64)
        new = entry("world/entities/r.1.-2.mca", digest="d" * 64)
        report = self.report(
            {
                "added": [],
                "modified": [{"before": old, "after": new}],
                "deleted": [],
                "metadata_only": [],
                "unchanged": 0,
            }
        )
        self.assertEqual(report["status"], "STABLE_DELTA_READY_FOR_REFRESH")
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["delta"]["selected_regions"], ["entities/r.1.-2.mca"])
        self.assertEqual(report["delta"]["changed_kinds"], {"world-region-nbt": 1})

    def test_any_source_deletion_fails_closed(self) -> None:
        lost = entry("world/data/scoreboard.dat", kind="world-level")
        report = self.report(
            {
                "added": [],
                "modified": [],
                "deleted": [lost],
                "metadata_only": [],
                "unchanged": 0,
            }
        )
        self.assertEqual(report["status"], "BLOCKED_SOURCE_DELETIONS")
        self.assertEqual(report["exit_code"], 2)
        self.assertTrue(report["blockers"])


if __name__ == "__main__":
    unittest.main()
