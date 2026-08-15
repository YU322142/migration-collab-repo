from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


BUILD_PATH = Path(__file__).with_name("build_vanilla_and_known_bug_ledger.py")
BUILD_SPEC = importlib.util.spec_from_file_location("vanilla_known_bug_builder_test", BUILD_PATH)
assert BUILD_SPEC is not None and BUILD_SPEC.loader is not None
builder = importlib.util.module_from_spec(BUILD_SPEC)
sys.modules[BUILD_SPEC.name] = builder
BUILD_SPEC.loader.exec_module(builder)

VALIDATE_PATH = Path(__file__).with_name("validate_vanilla_and_known_bug_ledger.py")
VALIDATE_SPEC = importlib.util.spec_from_file_location("vanilla_known_bug_validator_test", VALIDATE_PATH)
assert VALIDATE_SPEC is not None and VALIDATE_SPEC.loader is not None
validator = importlib.util.module_from_spec(VALIDATE_SPEC)
sys.modules[VALIDATE_SPEC.name] = validator
VALIDATE_SPEC.loader.exec_module(validator)


class VanillaKnownBugLedgerTests(unittest.TestCase):
    def test_model_has_exact_50_and_required_three_classes(self) -> None:
        ledger = builder.make_ledger([])
        builder.validate_model(ledger)
        self.assertEqual(50, len(ledger["new_vanilla_identifiers"]))
        self.assertEqual(
            ["minecraft:netherite_horse_armor"],
            [row["id"] for row in ledger["new_vanilla_identifiers"] if row["coverage"] == "protected_carrier_only"],
        )
        self.assertEqual(
            {builder.CLASS_FIXED, builder.CLASS_DATA_SAFE, builder.CLASS_UNFINISHED},
            {row["classification"] for row in ledger["items"]},
        )

    def test_missing_identifier_fails(self) -> None:
        ledger = builder.make_ledger([])
        ledger["new_vanilla_identifiers"].pop()
        with self.assertRaisesRegex(ValueError, "exactly 50"):
            builder.validate_model(ledger)

    def test_wrong_carrier_fails(self) -> None:
        ledger = builder.make_ledger([])
        carrier = next(row for row in ledger["new_vanilla_identifiers"] if row["id"] == "minecraft:netherite_horse_armor")
        carrier["coverage"] = "functional_backport_present"
        with self.assertRaisesRegex(ValueError, "49 functional"):
            builder.validate_model(ledger)

    def test_missing_required_issue_fails(self) -> None:
        ledger = builder.make_ledger([])
        ledger["items"] = [row for row in ledger["items"] if row["id"] != "server.map_banner"]
        with self.assertRaisesRegex(ValueError, "missing required issue"):
            builder.validate_model(ledger)

    def test_end_to_end_without_host_evidence_rehash(self) -> None:
        ledger = builder.make_ledger([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger_path = root / "ledger.json"
            markdown_path = root / "ledger.md"
            ledger_path.write_bytes(builder.stable_json(ledger))
            markdown_path.write_text(builder.render_markdown(ledger), encoding="utf-8", newline="\n")
            result = validator.validate(ledger_path, markdown_path, verify_evidence=False)
            self.assertEqual("PASS", result["status"])
            self.assertEqual(50, result["identifiers"])
            self.assertGreater(result["issues"], 15)

    def test_summary_drift_fails_validator(self) -> None:
        ledger = builder.make_ledger([])
        ledger["summary"]["known_issue_rows"] += 1
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger_path = root / "ledger.json"
            markdown_path = root / "ledger.md"
            ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
            markdown_path.write_text(builder.render_markdown(ledger), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "known_issue_rows drift"):
                validator.validate(ledger_path, markdown_path, verify_evidence=False)


if __name__ == "__main__":
    unittest.main()
