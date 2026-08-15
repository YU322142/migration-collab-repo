from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from outputs.tools import apply_attempt11_followup_fixes_20260814 as followup


class Attempt11FollowupTests(unittest.TestCase):
    def test_mutation_allowlist_is_exact(self) -> None:
        self.assertTrue(followup.allowed_mutation("server", Path("mods") / followup.DNT_NAME))
        self.assertTrue(followup.allowed_mutation("client", Path("mods") / followup.TRACKS_NAME))
        self.assertTrue(followup.allowed_mutation("server", followup.RING_REL))
        self.assertFalse(followup.allowed_mutation("client", followup.RING_REL))
        self.assertFalse(followup.allowed_mutation("server", Path("world/level.dat")))
        self.assertFalse(followup.allowed_mutation("server", Path("config/server.properties")))
        self.assertFalse(followup.allowed_mutation("server", followup.MAID_REL))

    def test_empty_function_scan_is_recursive_and_exact(self) -> None:
        value = {
            "functions": [{}, {"function": "minecraft:set_count"}],
            "nested": [{"functions": [{}]}],
            "unrelated": {},
        }
        self.assertEqual(
            followup.empty_function_paths(value),
            ["$.functions[0]", "$.nested[0].functions[0]"],
        )

    def test_tracks_semantics_requires_only_registered_block(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            jar = Path(raw) / "fixture.jar"
            with zipfile.ZipFile(jar, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in sorted(followup.TRACKS_CHANGED_ENTRIES):
                    archive.writestr(name, json.dumps({"values": ["tracks:track_mount"]}))
            result = followup.verify_tracks_semantics(jar)
            self.assertEqual(result["entry_count"], 2)
            self.assertEqual(
                set(result["corrected_tags"]), followup.TRACKS_CHANGED_ENTRIES
            )

    def test_tracks_semantics_rejects_item_only_ids_in_block_tag(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            jar = Path(raw) / "fixture.jar"
            with zipfile.ZipFile(jar, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in sorted(followup.TRACKS_CHANGED_ENTRIES):
                    archive.writestr(name, json.dumps({"values": followup.TRACKS_OLD_VALUES}))
            with self.assertRaisesRegex(followup.FollowupError, "unexpected semantics"):
                followup.verify_tracks_semantics(jar)

    def test_zip_change_set_detects_only_changed_entry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            old = root / "old.jar"
            new = root / "new.jar"
            with zipfile.ZipFile(old, "w") as archive:
                archive.writestr("a.txt", b"same")
                archive.writestr("b.json", b"old")
            with zipfile.ZipFile(new, "w") as archive:
                archive.writestr("a.txt", b"same")
                archive.writestr("b.json", b"new")
            self.assertEqual(followup.zip_changed_entries(old, new), ["b.json"])

    def test_relative_target_cannot_escape_root(self) -> None:
        with self.assertRaisesRegex(followup.FollowupError, "escapes root"):
            followup.relative_target("server", Path("../outside.txt"))


if __name__ == "__main__":
    unittest.main()
