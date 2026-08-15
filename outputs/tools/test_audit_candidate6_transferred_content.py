import json
import tempfile
import unittest
from pathlib import Path

from outputs.tools.audit_candidate6_transferred_content import (
    marker_outputs,
    markdown,
    source_key_check,
)


class Candidate6TransferredContentTests(unittest.TestCase):
    def test_marker_outputs_detects_missing_and_hash_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.dat").write_bytes(b"ok")
            report = marker_outputs(
                root,
                {
                    "outputs": {
                        "a.dat": {"sha256": "2689367B205C16CE32ED4200942B8B8B1E262DFC70D9BC9FBC77C49699A4F1DF"},
                        "missing.dat": {"sha256": "00"},
                    }
                },
            )
            self.assertEqual(report["checked"], 2)
            self.assertEqual(report["missing"], 1)
            self.assertEqual(report["mismatched"], 1)

    def test_source_key_check_is_read_only_and_compares_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.properties").write_text("x=1\n", encoding="utf-8")
            import hashlib

            expected = hashlib.sha256((root / "server.properties").read_bytes()).hexdigest().upper()
            result = source_key_check(
                root,
                {"source_manifest_before": {"files": {"server.properties": {"sha256": expected}}}},
            )
            self.assertEqual(result["checked"], 1)
            self.assertEqual(result["mismatched"], 0)

    def test_markdown_keeps_historical_warning_and_blocker(self):
        report = {
            "status": "INSPECTION_PASS_WITH_CUTOVER_BLOCKERS",
            "world_conversion": {"status": "CONVERTED", "players": 1, "counts": {"player_item_stacks_scanned": 2, "entity_item_stacks_scanned": 3}, "inherited_missing_schematic_files": 1},
            "world_second_pass": {"exists": True, "player_item_stacks_scanned": 2, "entity_item_stacks_scanned": 3, "players_changed": 0, "regions_reported": 0, "unsupported_total": 0},
            "villager_conversion": {"villagers": 1, "preflight": {"attribute_aliases": 2}, "second_pass": {"regions_changed": 0, "chunks_changed": 0}},
            "poi": {"status": "PASS", "records": 1, "region_files": 1},
            "bundle": {"server": {"bundle_sha256": "S"}, "client": {"bundle_sha256": "C"}},
            "conversion_marker": {"output_hash_check": {"checked": 1, "mismatched": 0, "missing": 0}},
            "warnings": [{"detail": "source reference was already missing"}],
            "blockers": [{"severity": "P0", "id": "live_snapshot_missing", "detail": "remote snapshot required"}],
            "decision": "Do not stop.",
        }
        text = markdown(report)
        self.assertIn("historical backup", text)
        self.assertIn("live_snapshot_missing", text)


if __name__ == "__main__":
    unittest.main()
