import importlib.util
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("migrate_mineastr_config.py")
SPEC = importlib.util.spec_from_file_location("migrate_mineastr_config", MODULE_PATH)
mineastr = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = mineastr
SPEC.loader.exec_module(mineastr)


def valid_values() -> dict:
    values = {}
    for key, field in mineastr.FIELDS.items():
        if field.kind == "bool":
            values[key] = False
        elif field.kind == "int":
            values[key] = field.minimum if field.minimum is not None else 0
        elif field.kind == "string":
            values[key] = f"value-{key}"
        elif field.kind == "string_list":
            values[key] = [f"value-{key}"]
    values["token"] = "private-test-token"
    return values


class MineAstrConfigMigrationTest(unittest.TestCase):
    def test_full_schema_round_trips_to_toml(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            output = root / "target.toml"
            values = valid_values()
            source.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")

            report = mineastr.migrate(source, output, None)

            self.assertEqual(values, tomllib.loads(output.read_text(encoding="utf-8")))
            self.assertEqual(len(mineastr.FIELDS), report["target_key_count"])
            self.assertNotIn(values["token"], json.dumps(report))
            self.assertTrue(report["sensitive_values_redacted"])

    def test_two_new_command_limits_are_defaulted(self):
        values = valid_values()
        values.pop("commandApprovalTimeoutSeconds")
        values.pop("commandMaxPendingApprovals")

        converted, defaults = mineastr.validate(values)

        self.assertEqual(300, converted["commandApprovalTimeoutSeconds"])
        self.assertEqual(128, converted["commandMaxPendingApprovals"])
        self.assertEqual(
            ["commandApprovalTimeoutSeconds", "commandMaxPendingApprovals"],
            defaults,
        )

    def test_unknown_key_is_rejected(self):
        values = valid_values()
        values["futureSecret"] = "do-not-ignore"
        with self.assertRaisesRegex(ValueError, "unknown configuration keys"):
            mineastr.validate(values)

    def test_out_of_range_value_is_rejected(self):
        values = valid_values()
        values["commandPermissionLevel"] = 5
        with self.assertRaisesRegex(ValueError, "above 4"):
            mineastr.validate(values)

    def test_in_place_conversion_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.json"
            source.write_text(json.dumps(valid_values()), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "in-place"):
                mineastr.migrate(source, source, None)

    def test_repeated_conversion_is_byte_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            first = root / "first.toml"
            second = root / "second.toml"
            source.write_text(json.dumps(valid_values(), ensure_ascii=False), encoding="utf-8")

            mineastr.migrate(source, first, None)
            mineastr.migrate(source, second, None)

            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
