from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("convert_player_advancements.py")
SPEC = importlib.util.spec_from_file_location("convert_player_advancements", MODULE_PATH)
converter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(converter)


class AdvancementConverterTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = os.environ.get("MIGRATION_TEST_TMPDIR")
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.target = root / "target"
        self.report = root / "report.json"
        self.policy = root / "policy.json"
        self.player = "00000000-0000-4000-8000-000000000001"
        self.source_file = self.source / "world" / "advancements" / f"{self.player}.json"
        self.target_file = self.target / "world" / "advancements" / f"{self.player}.json"
        self.source_file.parent.mkdir(parents=True)
        self.target_file.parent.mkdir(parents=True)
        self.progress = {
            "criteria": {"has_item": "2026-08-01 12:00:00 +0800"},
            "done": True,
        }
        self.write_policy()
        self.write_source()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_policy(self, rules=None) -> None:
        if rules is None:
            rules = [
                {
                    "old_id": "example:old",
                    "action": "map",
                    "target_id": "example:new",
                    "reason": "exact rename",
                },
                {
                    "old_id": "example:waive",
                    "action": "sidecar",
                    "reason": "no proven equivalent",
                },
            ]
        self.policy.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "policy_id": "test-policy",
                    "expected_rule_count": len(rules),
                    "rules": rules,
                }
            ),
            encoding="utf-8",
        )

    def write_source(self, extra=None) -> dict:
        value = {
            "minecraft:story/root": {
                "criteria": {"crafting_table": "2026-02-24 09:21:11 +0800"},
                "done": True,
            },
            "example:old": self.progress,
            "example:waive": {
                "criteria": {"legacy": "2026-07-01 08:00:00 +0800"},
                "done": True,
            },
            "DataVersion": 4671,
        }
        if extra:
            value.update(extra)
        self.source_file.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.target_file.write_bytes(self.source_file.read_bytes())
        return value

    def args(self, *, dry_run=False):
        values = [
            "--source-game-dir",
            str(self.source),
            "--target-game-dir",
            str(self.target),
            "--policy",
            str(self.policy),
            "--report",
            str(self.report),
        ]
        if dry_run:
            values.append("--dry-run")
        return converter.parse_args(values)

    def test_exact_mapping_sidecar_and_idempotence(self) -> None:
        self.assertEqual(converter.run(self.args()), 0)
        target = json.loads(self.target_file.read_text(encoding="utf-8"))
        self.assertNotIn("example:old", target)
        self.assertNotIn("example:waive", target)
        self.assertEqual(target["example:new"], self.progress)
        self.assertIn("minecraft:story/root", target)
        self.assertEqual(target["DataVersion"], 4671)

        sidecar = self.target / converter.SIDECAR_RELATIVE
        lines = sidecar.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["old_id"], "example:waive")
        self.assertEqual(record["progress"]["criteria"]["legacy"], "2026-07-01 08:00:00 +0800")
        before = {self.target_file: self.target_file.read_bytes(), sidecar: sidecar.read_bytes()}

        self.assertEqual(converter.run(self.args()), 0)
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "ALREADY_TARGET")

    def test_mapping_merges_criteria_and_uses_earlier_timestamp(self) -> None:
        target_progress = {
            "criteria": {
                "has_item": "2026-08-02 12:00:00 +0800",
                "has_the_recipe": "2026-08-03 12:00:00 +0800",
            },
            "done": False,
        }
        self.write_source({"example:new": target_progress})
        converter.run(self.args())
        target = json.loads(self.target_file.read_text(encoding="utf-8"))
        self.assertEqual(
            target["example:new"]["criteria"]["has_item"],
            "2026-08-01 12:00:00 +0800",
        )
        self.assertIn("has_the_recipe", target["example:new"]["criteria"])
        self.assertTrue(target["example:new"]["done"])

    def test_dry_run_writes_report_only(self) -> None:
        before = self.target_file.read_bytes()
        self.assertEqual(converter.run(self.args(dry_run=True)), 0)
        self.assertEqual(self.target_file.read_bytes(), before)
        self.assertFalse((self.target / converter.SIDECAR_RELATIVE).exists())
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "WOULD_CONVERT")

    def test_malformed_progress_blocks_without_writes(self) -> None:
        value = json.loads(self.source_file.read_text(encoding="utf-8"))
        value["example:old"]["done"] = "yes"
        self.source_file.write_text(json.dumps(value), encoding="utf-8")
        before = self.target_file.read_bytes()
        with self.assertRaisesRegex(converter.AdvancementConversionError, "done boolean"):
            converter.run(self.args())
        self.assertEqual(self.target_file.read_bytes(), before)
        self.assertFalse((self.target / converter.SIDECAR_RELATIVE).exists())

    def test_target_divergence_blocks(self) -> None:
        value = json.loads(self.target_file.read_text(encoding="utf-8"))
        value["minecraft:story/root"]["criteria"]["crafting_table"] = (
            "2026-08-13 00:00:00 +0800"
        )
        self.target_file.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(converter.AdvancementConversionError, "target advancement file"):
            converter.run(self.args())

    def test_stale_transaction_artifact_blocks_and_is_retained(self) -> None:
        stale = self.target_file.with_name(self.target_file.name + ".migration.bak")
        stale.write_bytes(b"recovery")
        with self.assertRaisesRegex(converter.AdvancementConversionError, "stale"):
            converter.run(self.args())
        self.assertEqual(stale.read_bytes(), b"recovery")

    def test_commit_failure_rolls_back_player_and_sidecar(self) -> None:
        original = self.target_file.read_bytes()
        original_replace = converter.os.replace
        commits = 0

        def fail_second(source, target):
            nonlocal commits
            if str(source).endswith(".migration.tmp"):
                commits += 1
                if commits == 2:
                    raise OSError("planned failure")
            return original_replace(source, target)

        with mock.patch.object(converter.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                converter.run(self.args())
        self.assertEqual(self.target_file.read_bytes(), original)
        self.assertFalse((self.target / converter.SIDECAR_RELATIVE).exists())

    def test_policy_duplicates_are_rejected(self) -> None:
        rule = {
            "old_id": "example:old",
            "action": "sidecar",
            "reason": "duplicate",
        }
        self.write_policy([rule, rule])
        with self.assertRaisesRegex(converter.AdvancementConversionError, "duplicate"):
            converter.run(self.args())


if __name__ == "__main__":
    unittest.main()
