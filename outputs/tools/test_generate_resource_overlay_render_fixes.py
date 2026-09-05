from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from outputs.tools.generate_resource_overlay_render_fixes import (
    ender_dragon_tea_variants,
    generate,
)


WORKSPACE = Path(__file__).resolve().parents[2]
PROJECT = WORKSPACE / "outputs" / "projects" / "resource-error-overlay-1.21.1"
END_JAR = Path(
    r"<AUDIT_ROOT>\KaleidoscopeEnd-1.21.1-equivalence\build\libs\kaleidoscope_end-1.0.14-migration.7-neoforge+mc1.21.1.jar"
)
NETHER_JAR = Path(
    r"<AUDIT_ROOT>\world-migration-smoke1\mods\kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar"
)


class RenderFixGenerationTests(unittest.TestCase):
    def test_all_144_dragon_tea_states_are_defined(self) -> None:
        variants = ender_dragon_tea_variants()
        self.assertEqual(144, len(variants))
        for cup_count in range(1, 7):
            for facing in ("east", "north", "south", "west"):
                for tea_count in range(1, 7):
                    key = (
                        f"cup_count={cup_count},facing={facing},"
                        f"tea_count={tea_count}"
                    )
                    self.assertIn(key, variants)

    def test_fallback_uses_only_existing_four_cup_models(self) -> None:
        variants = ender_dragon_tea_variants()
        referenced = {value["model"] for value in variants.values()}
        expected = {
            "kaleidoscope_end:block/teacup/ender_dragon_tea/"
            f"count{cups}_{tea}"
            for cups in range(1, 5)
            for tea in range(1, cups + 1)
        }
        self.assertEqual(expected, referenced)
        self.assertEqual(
            "kaleidoscope_end:block/teacup/ender_dragon_tea/count4_4",
            variants["cup_count=6,facing=north,tea_count=6"]["model"],
        )

    def test_generated_files_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = Path(first_dir)
            second = Path(second_dir)
            first_files = generate(first)
            second_files = generate(second)
            self.assertEqual(
                [path.relative_to(first) for path in first_files],
                [path.relative_to(second) for path in second_files],
            )
            for left, right in zip(first_files, second_files, strict=True):
                self.assertEqual(left.read_bytes(), right.read_bytes())

    def test_checked_in_resources_match_generator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            temporary = Path(temporary_dir)
            generated = generate(temporary)
            for path in generated:
                relative = path.relative_to(temporary)
                checked_in = PROJECT / relative
                self.assertTrue(checked_in.is_file(), relative.as_posix())
                self.assertEqual(path.read_bytes(), checked_in.read_bytes())

    @unittest.skipUnless(END_JAR.is_file() and NETHER_JAR.is_file(), "locked dependency JARs unavailable")
    def test_locked_dependency_resource_closure(self) -> None:
        state_path = (
            PROJECT
            / "src"
            / "main"
            / "resources"
            / "assets"
            / "kaleidoscope_end"
            / "blockstates"
            / "ender_dragon_tea.json"
        )
        variants = json.loads(state_path.read_text(encoding="utf-8"))["variants"]
        with zipfile.ZipFile(END_JAR) as end_zip:
            names = set(end_zip.namelist())
            for value in variants.values():
                namespace, model = value["model"].split(":", 1)
                entry = f"assets/{namespace}/models/{model}.json"
                self.assertIn(entry, names)

        with zipfile.ZipFile(NETHER_JAR) as nether_zip:
            self.assertIn(
                "assets/kaleidoscope_nether/textures/item/blowgun.png",
                nether_zip.namelist(),
            )
        for index in range(3):
            path = (
                PROJECT
                / "src"
                / "main"
                / "resources"
                / "assets"
                / "kaleidoscope_nether"
                / "models"
                / "item"
                / f"blowgun_pulling_{index}.json"
            )
            model = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("item/handheld", model["parent"])
            self.assertEqual(
                "kaleidoscope_nether:item/blowgun",
                model["textures"]["layer0"],
            )


if __name__ == "__main__":
    unittest.main()
