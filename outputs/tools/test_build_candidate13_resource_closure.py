from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from outputs.tools.build_candidate13_resource_closure import (
    FACINGS,
    MATERIALS,
    audio_blockstate,
    build_local_pack,
    canonical_json,
)


class Candidate13ResourceClosureTests(unittest.TestCase):
    def test_audio_fallback_defines_exact_three_forms(self) -> None:
        for kind in ("audio", "audio_large"):
            value = audio_blockstate(kind, "oak")["variants"]
            self.assertEqual(12, len(value))
            for facing, rotation in FACINGS.items():
                for form in range(3):
                    key = f"facing={facing},form={form}"
                    self.assertIn(key, value)
                self.assertEqual(
                    value[f"facing={facing},form=0"],
                    value[f"facing={facing},form=2"],
                )
                self.assertEqual(rotation, value[f"facing={facing},form=2"].get("y"))

    def test_all_54_audio_blockstates_are_unique_and_complete(self) -> None:
        generated = {
            f"{kind}_a_{material}_blindwall": audio_blockstate(kind, material)
            for kind in ("audio", "audio_large")
            for material in MATERIALS
        }
        self.assertEqual(54, len(generated))
        self.assertEqual(648, sum(len(v["variants"]) for v in generated.values()))

    def test_canonical_json_is_stable(self) -> None:
        self.assertEqual(b'{\n  "a": 1\n}\n', canonical_json({"a": 1}))

    def test_local_pack_derivation_changes_only_two_entries(self) -> None:
        source_state = {
            "variants": {
                **{
                    f"axis={axis},creaking_heart_state={state}": {"model": f"m:{axis}/{state}"}
                    for axis in "xyz" for state in ("awake", "dormant", "uprooted")
                },
                **{
                    f"active={active},axis={axis}": {"model": f"legacy:{active}/{axis}"}
                    for active in ("false", "true") for axis in "xyz"
                },
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", canonical_json({"pack": {"min_format": 1, "max_format": 9999, "description": "x"}}))
                archive.writestr("assets/minecraft/blockstates/creaking_heart.json", canonical_json(source_state))
                archive.writestr("assets/demo/unchanged.bin", b"unchanged")
            output, evidence = build_local_pack(source, root / "out")
            self.assertEqual(
                ["assets/minecraft/blockstates/creaking_heart.json", "pack.mcmeta"],
                evidence["changed_entries"],
            )
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(b"unchanged", archive.read("assets/demo/unchanged.bin"))
                metadata = json.loads(archive.read("pack.mcmeta"))
                state = json.loads(archive.read("assets/minecraft/blockstates/creaking_heart.json"))
            self.assertEqual(34, metadata["pack"]["pack_format"])
            self.assertEqual(9, len(state["variants"]))
            self.assertFalse(any(k.startswith("active=") for k in state["variants"]))


if __name__ == "__main__":
    unittest.main()
