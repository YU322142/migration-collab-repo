from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from outputs.tools import mechanomania_release_runtime_common as subject


class DigestParityTest(unittest.TestCase):
    def make_directory_link(self, target: Path, source: Path) -> None:
        if os.name == "nt":
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(target), str(source)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.skipTest(f"junction creation unavailable: {result.stdout} {result.stderr}")
        else:
            target.symlink_to(source, target_is_directory=True)

    def test_mod_digest_binds_size_and_uses_casefold_sort(self) -> None:
        rows = [
            {"file": "z.jar", "bytes": 2, "sha256": "B" * 64},
            {"file": "A.jar", "bytes": 1, "sha256": "A" * 64},
        ]
        payload = (
            f"A.jar\0{1}\0{'A' * 64}\n"
            f"z.jar\0{2}\0{'B' * 64}\n"
        ).encode("utf-8")
        self.assertEqual(subject.bundle_digest(rows), hashlib.sha256(payload).hexdigest().upper())
        mutated = [dict(row) for row in rows]
        mutated[0]["bytes"] = 3
        self.assertNotEqual(subject.bundle_digest(rows), subject.bundle_digest(mutated))

    def test_overlay_digest_matches_release_builder_fields(self) -> None:
        rows = [
            {
                "target_rel": "config/z.toml",
                "bytes": 2,
                "sha256": "B" * 64,
                "layer": "pack",
                "merge_mode": "replace",
            },
            {
                "target_rel": "config/A.toml",
                "bytes": 1,
                "sha256": "A" * 64,
                "layer": "base",
                "merge_mode": "copy_if_absent",
            },
        ]
        payload = (
            f"config/A.toml\0{1}\0{'A' * 64}\0base\0copy_if_absent\n"
            f"config/z.toml\0{2}\0{'B' * 64}\0pack\0replace\n"
        ).encode("utf-8")
        self.assertEqual(subject.overlay_digest(rows), hashlib.sha256(payload).hexdigest().upper())

    def test_overlay_rejects_linked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "release" / "server" / "overlay" / "config"
            source.mkdir(parents=True)
            payload = source / "x.toml"
            payload.write_text("safe", encoding="ascii")
            target = root / "target"
            outside = root / "outside"
            target.mkdir()
            outside.mkdir()
            self.make_directory_link(target / "config", outside)
            binding = {
                "root": str(root / "release"),
                "server_overlay": {
                    "files": 1,
                    "overlay_sha256": "A" * 64,
                    "rows": [
                        {
                            "target_rel": "config/x.toml",
                            "bytes": 4,
                            "sha256": subject.sha256(payload),
                            "layer": "pack",
                            "merge_mode": "replace",
                        }
                    ],
                },
            }
            with self.assertRaisesRegex(subject.ReleaseRuntimeError, "parent is linked"):
                subject.apply_overlay(binding, "server", target)

    def test_journeymap_match_uses_mod_id_not_only_filename(self) -> None:
        manifest = {
            "rows": [
                {
                    "file": "renamed-map.jar",
                    "mod_ids": ["journeymap"],
                }
            ]
        }
        self.assertEqual(
            subject.journeymap_mod_matches(manifest),
            [{"file": "renamed-map.jar", "mod_ids": "journeymap"}],
        )
        self.assertEqual(
            subject.journeymap_mod_matches(
                {"rows": [{"file": "xaero.jar", "mod_ids": ["xaeroworldmap"]}]}
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
