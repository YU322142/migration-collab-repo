from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import nbtlib


MODULE_PATH = Path(__file__).with_name("sanitize_target_resources.py")
SPEC = importlib.util.spec_from_file_location("sanitize_target_resources", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
sanitizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sanitizer)


class SanitizeTargetResourcesTests(unittest.TestCase):
    def d_temp(self):
        root = Path(os.environ.get("MIGRATION_TEST_TMP", r"<AUDIT_ROOT>\tmp"))
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def make_mod_jar(self, path: Path, mod_id: str, entries: dict[str, bytes]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "fabric.mod.json",
                json.dumps({"schemaVersion": 1, "id": mod_id, "version": "1"}),
            )
            for name, payload in entries.items():
                archive.writestr(name, payload)

    def test_sanitizes_optional_resources_and_is_idempotent(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            world = root / "world"
            datapack = world / "datapacks" / "bukkit"
            datapack.mkdir(parents=True)
            (datapack / "pack.mcmeta").write_text(
                json.dumps(
                    {
                        "pack": {
                            "description": "bukkit",
                            "min_format": [88, 0],
                            "max_format": [88, 0],
                        }
                    }
                ),
                encoding="utf-8",
            )
            transfer = world / "datapacks" / "transfer" / "data" / "moon" / "function"
            transfer.mkdir(parents=True)
            (transfer / "go.mcfunction").write_text(
                "transfer aft125.top 25565 @p\n", encoding="utf-8"
            )
            properties = root / "server.properties"
            properties.write_text("function-permission-level=2\nonline-mode=false\n", encoding="ascii")
            nbtlib.File(
                {
                    "Data": nbtlib.Compound(
                        {
                            "DataPacks": nbtlib.Compound(
                                {
                                    "Enabled": nbtlib.List[nbtlib.String](
                                        [
                                            nbtlib.String("vanilla"),
                                            nbtlib.String("create"),
                                            nbtlib.String("easyauth"),
                                            nbtlib.String("file/transfer"),
                                            nbtlib.String("custom_pack"),
                                        ]
                                    ),
                                    "Disabled": nbtlib.List[nbtlib.String](),
                                }
                            )
                        }
                    )
                }
            ).save(world / "level.dat", gzipped=True)
            mods = root / "mods"
            mods.mkdir()
            global_list = json.dumps(
                {
                    "replace": False,
                    "entries": [
                        "kaleidoscope_nether:blaze",
                        "kaleidoscope_nether:integration/eternalnether/wex",
                    ],
                }
            ).encode()
            eternal = "data/kaleidoscope_nether/loot_modifiers/integration/eternalnether/wex.json"
            maps = {
                name: b"{}" for name in sanitizer.CREATE_DRAGONS_OPTIONAL_DATA_MAPS
            }
            self.make_mod_jar(
                mods / "kaleidoscope_nether-1.jar",
                "kaleidoscope_nether",
                {"data/neoforge/loot_modifiers/global_loot_modifiers.json": global_list, eternal: b"{}"},
            )
            self.make_mod_jar(mods / "CreateDragonsPlus-1.jar", "create_dragons_plus", maps)

            report = sanitizer.sanitize(world, properties, mods)
            self.assertEqual(report["status"], "SANITIZED")
            self.assertEqual(report["changed_files"], 5)
            self.assertEqual(report["runtime_mod_manifest"]["file_count"], 2)
            self.assertEqual(len(report["runtime_mod_manifest"]["bundle_sha256"]), 64)
            self.assertTrue(
                all(
                    len(row["sha256"]) == 64
                    for row in report["runtime_mod_manifest"]["files"]
                )
            )
            pack = json.loads((datapack / "pack.mcmeta").read_text(encoding="utf-8"))
            self.assertEqual(pack["pack"]["pack_format"], 48)
            self.assertNotIn("min_format", pack["pack"])
            self.assertIn("function-permission-level=3", properties.read_text(encoding="ascii"))
            level = nbtlib.load(world / "level.dat", gzipped=True)
            self.assertEqual(
                [str(item) for item in level["Data"]["DataPacks"]["Enabled"]],
                ["vanilla", "file/transfer", "custom_pack"],
            )
            with zipfile.ZipFile(mods / "kaleidoscope_nether-1.jar") as archive:
                values = json.loads(
                    archive.read("data/neoforge/loot_modifiers/global_loot_modifiers.json")
                )
                self.assertEqual(values["entries"], ["kaleidoscope_nether:blaze"])
                self.assertNotIn(eternal, archive.namelist())
            with zipfile.ZipFile(mods / "CreateDragonsPlus-1.jar") as archive:
                for name in maps:
                    self.assertNotIn(name, archive.namelist())

            second = sanitizer.sanitize(world, properties, mods)
            self.assertEqual(second["status"], "ALREADY_CLEAN")
            self.assertEqual(second["changed_files"], 0)
            self.assertEqual(
                report["runtime_mod_manifest"], second["runtime_mod_manifest"]
            )

    def test_keeps_create_dragons_maps_when_simulated_is_available(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            world = root / "world"
            (world / "datapacks").mkdir(parents=True)
            properties = root / "server.properties"
            properties.write_text("function-permission-level=2\n", encoding="ascii")
            mods = root / "mods"
            mods.mkdir()
            maps = {name: b"{}" for name in sanitizer.CREATE_DRAGONS_OPTIONAL_DATA_MAPS}
            self.make_mod_jar(mods / "CreateDragonsPlus-1.jar", "create_dragons_plus", maps)
            self.make_mod_jar(mods / "simulated-1.jar", "simulated", {})
            report = sanitizer.sanitize(world, properties, mods)
            self.assertEqual(report["create_dragons_plus"]["status"], "dependency-present")
            with zipfile.ZipFile(mods / "CreateDragonsPlus-1.jar") as archive:
                self.assertTrue(all(name in archive.namelist() for name in maps))


if __name__ == "__main__":
    unittest.main()
