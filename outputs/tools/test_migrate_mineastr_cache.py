import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from nbt.nbt import NBTFile, TAG_Byte, TAG_Compound, TAG_Int, TAG_List, TAG_String


MODULE_PATH = Path(__file__).with_name("migrate_mineastr_cache.py")
SPEC = importlib.util.spec_from_file_location("migrate_mineastr_cache", MODULE_PATH)
mineastr = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mineastr)


def legacy_entry(identifier: str = "minecraft:overworld/1,2,3/front") -> TAG_Compound:
    entry = TAG_Compound()
    entry["id"] = TAG_String(identifier)
    entry["fingerprint"] = TAG_String("a" * 64)
    entry["source"] = TAG_String("Welcome")
    entry["show_original"] = TAG_Byte(1)
    translations = TAG_Compound()
    translations["zh_cn"] = TAG_String("Welcome translated")
    entry["translations"] = translations
    return entry


def write_legacy(path: Path, duplicate: bool = False) -> None:
    root = NBTFile()
    root["version"] = TAG_Int(1)
    entries = TAG_List(type=TAG_Compound)
    entries.append(legacy_entry())
    if duplicate:
        entries.append(legacy_entry())
    root["entries"] = entries
    root.write_file(str(path))


class MineAstrCacheMigrationTest(unittest.TestCase):
    def test_promotes_legacy_automatic_entry_without_changing_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.dat"
            output = root / "output.dat"
            write_legacy(source)

            report = mineastr.migrate(source, output, None, True)
            converted = NBTFile(filename=str(output))
            entry = converted["entries"][0]

            self.assertEqual("CHANGED", report["status"])
            self.assertEqual(1, report["promoted_automatic_entries"])
            self.assertEqual(2, converted["version"].value)
            self.assertEqual(2, entry["policy_version"].value)
            self.assertEqual("Welcome", entry["source"].value)
            self.assertEqual("Welcome translated", entry["translations"]["zh_cn"].value)
            self.assertEqual(0, len(entry["manual_languages"]))
            self.assertEqual(1, report["automatic_entries"])
            self.assertEqual(1, report["translation_value_count"])
            self.assertEqual(1, report["output_usable_entries"])
            report_text = json.dumps(report)
            self.assertNotIn("minecraft:overworld/1,2,3/front", report_text)
            self.assertNotIn("Welcome", report_text)
            self.assertTrue(report["entry_identifiers_redacted"])
            self.assertTrue(report["content_values_redacted"])

    def test_second_pass_is_semantically_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.dat"
            first = root / "first.dat"
            second = root / "second.dat"
            write_legacy(source)
            mineastr.migrate(source, first, None, True)

            report = mineastr.migrate(first, second, None, True)

            self.assertEqual("ALREADY_TARGET", report["status"])
            self.assertEqual(report["source_semantic_sha256"], report["target_semantic_sha256"])
            self.assertTrue(second.exists())
            self.assertEqual(
                mineastr.semantic_hash(NBTFile(filename=str(first))),
                mineastr.semantic_hash(NBTFile(filename=str(second))),
            )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(report["source_file_sha256"], report["target_file_sha256"])
            self.assertTrue(report["deterministic_gzip"])

    def test_requires_explicit_promotion_for_automatic_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.dat"
            output = root / "output.dat"
            write_legacy(source)

            report = mineastr.migrate(source, output, None, False)
            converted = NBTFile(filename=str(output))

            self.assertEqual(0, report["promoted_automatic_entries"])
            self.assertEqual(1, converted["entries"][0]["policy_version"].value)

    def test_duplicate_identity_fails_without_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.dat"
            output = root / "output.dat"
            write_legacy(source, duplicate=True)

            with self.assertRaisesRegex(ValueError, "duplicate sign id"):
                mineastr.migrate(source, output, None, True)
            self.assertFalse(output.exists())

    def test_in_place_conversion_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.dat"
            write_legacy(source)
            with self.assertRaisesRegex(ValueError, "in-place"):
                mineastr.migrate(source, source, None, True)


if __name__ == "__main__":
    unittest.main()
