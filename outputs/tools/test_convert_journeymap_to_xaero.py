from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
TEST_TEMP_ROOT = TOOLS_DIR.parent / "tmp" / "test-jm-xaero"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

import convert_journeymap_to_xaero as converter


SOURCE_ZIP = Path(r"D:\Down\journeymap_export_yu_2026-06-19_22.45.13 (1).zip")
SOURCE_ROOT = Path(
    r"D:\Trans\migration-audit-work\journeymap-export-audit-20260813"
)
MINIMAP_JAR = Path(
    r"D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3"
    r"\instances\Mechanomania-Ultimate-Aeronautics-1.1.11.1"
    r"\minecraft\mods\xaerominimap-neoforge-1.21.1-26.1.0.jar"
)
WORLD_MAP_JAR = Path(
    r"D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3"
    r"\instances\Mechanomania-Ultimate-Aeronautics-1.1.11.1"
    r"\minecraft\mods\xaeroworldmap-neoforge-1.21.1-1.41.2.jar"
)
VANILLA_STATES = Path(
    r"D:\Trans\migration-audit-work\xaero-javap-20260813\vanilla_states.dat"
)


def nbt_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">H", len(encoded)) + encoded


def named_tag(tag_type: int, name: str, payload: bytes) -> bytes:
    return bytes((tag_type,)) + nbt_string(name) + payload


def compound_payload(entries: list[bytes]) -> bytes:
    return b"".join(entries) + b"\x00"


def named_compound(name: str, entries: list[bytes]) -> bytes:
    return named_tag(10, name, compound_payload(entries))


class ConverterUnitTests(unittest.TestCase):
    def test_nbt_reader_unicode_nested_and_arrays(self) -> None:
        data = named_compound(
            "root",
            [
                named_tag(8, "name", nbt_string("村庄：北")),
                named_tag(3, "x", struct.pack(">i", -123)),
                named_tag(
                    10,
                    "pos",
                    compound_payload(
                        [
                            named_tag(4, "seed", struct.pack(">q", 9876543210)),
                            named_tag(8, "dimension", nbt_string("minecraft:overworld")),
                        ]
                    ),
                ),
                named_tag(9, "values", b"\x03" + struct.pack(">i", 3) + struct.pack(">iii", 1, 2, 3)),
                named_tag(11, "ints", struct.pack(">i", 2) + struct.pack(">ii", -1, 9)),
            ],
        )
        parsed = converter.read_nbt_bytes(data)
        self.assertEqual(parsed["name"], "村庄：北")
        self.assertEqual(parsed["x"], -123)
        self.assertEqual(parsed["pos"]["seed"], 9876543210)
        self.assertEqual(parsed["values"], [1, 2, 3])
        self.assertEqual(parsed["ints"], [-1, 9])
        with self.assertRaises(converter.ConversionError):
            converter.read_nbt_bytes(data + b"trailing")

    def test_json_output_is_ascii_safe_and_unicode_round_trips(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp_text:
            path = Path(temp_text) / "report.json"
            value = {"group": "死亡", "escape": converter.WAYPOINT_ESCAPE}
            converter.atomic_write_json(path, value)
            raw = path.read_bytes()
            self.assertTrue(raw.isascii())
            self.assertIn(b"\\u6b7b\\u4ea1", raw)
            self.assertEqual(json.loads(raw), value)

    def test_load_vanilla_states_and_palette_tie_break(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp_text:
            root = Path(temp_text)
            states_path = root / "states.dat"
            states_path.write_bytes(
                struct.pack(">i", 0)
                + named_compound("", [named_tag(8, "Name", nbt_string("minecraft:air"))])
                + struct.pack(">i", 2)
                + named_compound("", [named_tag(8, "Name", nbt_string("minecraft:grass_block"))])
                + struct.pack(">i", 2)
                + named_compound("", [named_tag(8, "Name", nbt_string("minecraft:dirt"))])
                + struct.pack(">i", 3)
                + named_compound("", [named_tag(8, "Name", nbt_string("minecraft:dirt"))])
                + struct.pack(">i", 5)
                + named_compound("", [named_tag(8, "Name", nbt_string("minecraft:oak_planks"))])
                + struct.pack(">i", 5)
                + named_compound("", [named_tag(8, "Name", nbt_string("minecraft:oak_planks"))])
            )
            table = converter.load_vanilla_state_table(states_path)
            states = table.states
            self.assertEqual(states[0], "minecraft:air")
            self.assertEqual(states[2], "minecraft:dirt")
            audit = table.audit()
            self.assertEqual(audit["record_count"], 6)
            self.assertEqual(audit["unique_composite_state_ids"], 4)
            self.assertEqual(audit["duplicate_record_count"], 2)
            self.assertEqual(audit["duplicate_composite_state_ids"], [2, 5])
            self.assertEqual(audit["conflicting_duplicate_record_count"], 1)
            self.assertEqual(
                audit["overwrites_in_file_order"][0]["replacement_name"],
                "minecraft:dirt",
            )
            mapping = root / "mapping.txt"
            # The lower legacy state ID must win duplicate-colour ties.
            mapping.write_text("5,-16711936\n3,-16711936\n", encoding="utf-8")
            palette = converter.load_block_palette(mapping, states)
            self.assertEqual(palette.source_rows, 2)
            self.assertEqual(palette.state_ids.tolist(), [3])

    def test_server_identity_and_xaero_root(self) -> None:
        converter.verify_server_identity("play.example.invalid", 12341)
        converter.verify_port_separation(12341, 25566)
        self.assertEqual(
            converter.xaero_root_id("play.example.invalid:12341"),
            "Multiplayer_play.example.invalid",
        )
        with self.assertRaises(converter.ConversionError):
            converter.verify_server_identity("play.example.invalid:12341", 12341)
        with self.assertRaises(converter.ConversionError):
            converter.verify_server_identity("play.example.invalid", 70000)
        with self.assertRaises(converter.ConversionError):
            converter.verify_port_separation(25566, 25566)

    def test_waypoint_escape_and_reserved_escape_failure(self) -> None:
        self.assertEqual(
            converter.safe_waypoint_field("甲:乙"),
            "甲" + converter.WAYPOINT_ESCAPE + "乙",
        )
        with self.assertRaises(converter.ConversionError):
            converter.safe_waypoint_field("甲" + converter.WAYPOINT_ESCAPE + "乙")

    def test_synthetic_source_zip_binding(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp_text:
            root = Path(temp_text)
            extracted = root / "extracted"
            (extracted / "a").mkdir(parents=True)
            (extracted / "a" / "one.txt").write_bytes(b"one")
            (extracted / "two.bin").write_bytes(bytes(range(16)))
            archive_path = root / "source.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.write(extracted / "a" / "one.txt", "a/one.txt")
                archive.write(extracted / "two.bin", "two.bin")
            result = converter.verify_source_zip_matches_extracted(
                archive_path, extracted, workers=2
            )
            self.assertTrue(result["all_sizes_and_crc32_match"])
            self.assertEqual(result["zip_file_entries"], 2)
            (extracted / "two.bin").write_bytes(b"changed")
            with self.assertRaises(converter.ConversionError):
                converter.verify_source_zip_matches_extracted(
                    archive_path, extracted, workers=2
                )

    def test_region_v4_round_trip_and_deterministic_zip(self) -> None:
        rgba = np.zeros((512, 512, 4), dtype=np.uint8)
        rgba[0, 0] = (0x11, 0x22, 0x33, 255)
        rgba[1, 0] = (0x11, 0x22, 0x33, 127)
        colors = np.asarray([0x112233], dtype=np.uint32)
        states = np.asarray([2], dtype=np.uint32)
        payload, writer = converter.build_region_payload(rgba, colors, states, light=0)
        self.assertEqual(writer["nonempty_map_tiles"], 1)
        self.assertEqual(writer["empty_map_tiles"], 1023)
        self.assertEqual(writer["explicit_air_pixels_in_nonempty_tiles"], 254)
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp_text:
            root = Path(temp_text)
            first = root / "first.zip"
            second = root / "second.zip"
            source_sha = "a" * 64
            conversion_sha = "b" * 64
            converter.write_region_zip(first, payload, source_sha, conversion_sha)
            converter.write_region_zip(second, payload, source_sha, conversion_sha)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            validation = converter.validate_region_zip(
                first, {0, 2}, source_sha, conversion_sha
            )
            self.assertEqual(validation["nonempty_map_tiles"], 1)
            self.assertEqual(validation["empty_map_tiles"], 1023)
            self.assertEqual(validation["explicit_air_pixels_in_nonempty_tiles"], 254)
            with self.assertRaises(converter.ConversionError):
                converter.validate_region_zip(first, {0, 2}, source_sha, "c" * 64)

    def test_world_map_config_pins_default_slot(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp_text:
            root = Path(temp_text)
            converter.write_world_map_configs(root, "Multiplayer_play.example.invalid")
            base = root / "staging" / "xaero" / "world-map" / "Multiplayer_play.example.invalid"
            server_config = (base / "server_config.txt").read_text(encoding="utf-8")
            self.assertIn("ignoreServerLevelId:true", server_config)
            for dimension in converter.DIMENSIONS:
                config = (base / dimension["world_map_dir"] / "dimension_config.txt").read_text(
                    encoding="utf-8"
                )
                self.assertIn("confirmedMultiworld:mw$default", config)
                self.assertIn("MWName:mw$default:JourneyMap Import", config)

    def test_prepare_output_root_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp_text:
            root = Path(temp_text)
            output = root / "output"
            output.mkdir()
            (output / "foreign.txt").write_text("foreign", encoding="utf-8")
            identity = {"fingerprint_sha256": "a" * 64}
            with self.assertRaises(converter.ConversionError):
                converter.prepare_output_root(output, False, identity)

    def test_prepare_output_root_binds_resume_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp_text:
            output = Path(temp_text) / "output"
            first = {"fingerprint_sha256": "a" * 64, "bound_inputs": {}}
            second = {"fingerprint_sha256": "b" * 64, "bound_inputs": {}}
            converter.prepare_output_root(output, False, first)
            converter.prepare_output_root(output, True, first)
            with self.assertRaises(converter.ConversionError):
                converter.prepare_output_root(output, True, second)


@unittest.skipUnless(
    SOURCE_ROOT.is_dir() and SOURCE_ZIP.is_file(),
    "audited JourneyMap source is not available",
)
class SourceIntegrationTests(unittest.TestCase):
    def test_actual_waypoints_and_native_paths(self) -> None:
        parsed = converter.parse_waypoints(SOURCE_ROOT / "waypoints" / "WaypointData.dat")
        self.assertEqual(len(parsed["groups"]), 5)
        self.assertEqual(len(parsed["waypoints"]), 50)
        self.assertEqual(
            Counter(
                dimension
                for waypoint in parsed["waypoints"].values()
                for dimension in waypoint["dimensions"]
            ),
            Counter(
                {
                    "minecraft:overworld": 45,
                    "minecraft:the_nether": 2,
                    "minecraft:the_end": 3,
                }
            ),
        )
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp_text:
            root = Path(temp_text)
            audit = converter.convert_waypoints(
                SOURCE_ROOT / "waypoints" / "WaypointData.dat",
                root,
                "Multiplayer_play.example.invalid",
            )
            self.assertEqual(audit["source_unique_waypoints"], 50)
            self.assertEqual(audit["output_waypoint_records"], 50)
            self.assertEqual(audit["native_world_node"], "mw$default")
            for resource, relative in audit["native_files"].items():
                path = root / relative
                self.assertEqual(path.name, "mw$default.txt")
                lines = path.read_text(encoding="utf-8").splitlines()
                waypoint_lines = [line for line in lines if line.startswith("waypoint:")]
                self.assertEqual(len(waypoint_lines), audit["dimension_counts"][resource])
                self.assertTrue(all(len(line.split(":")) == 14 for line in waypoint_lines))
            config = (
                root
                / "staging"
                / "xaero"
                / "minimap"
                / "Multiplayer_play.example.invalid"
                / "config.txt"
            ).read_text(encoding="utf-8")
            self.assertIn("defaultMultiworldId:mw$default", config)
            self.assertIn("ignoreServerLevelId:true", config)

    def test_actual_day_tile_inventory(self) -> None:
        records = converter.discover_day_tiles(SOURCE_ROOT)
        self.assertEqual(len(records), 531)
        self.assertEqual(
            Counter(record["dimension"] for record in records),
            Counter({"overworld": 453, "the_nether": 27, "the_end": 51}),
        )


@unittest.skipUnless(
    MINIMAP_JAR.is_file() and WORLD_MAP_JAR.is_file() and VANILLA_STATES.is_file(),
    "audited Xaero jars are not available",
)
class XaeroJarIntegrationTests(unittest.TestCase):
    def test_target_jars_and_embedded_state_table(self) -> None:
        result = converter.verify_xaero_jars(
            MINIMAP_JAR, WORLD_MAP_JAR, VANILLA_STATES
        )
        self.assertEqual(result["minimap_version"], "26.1.0")
        self.assertEqual(result["world_map_version"], "1.41.2")
        self.assertTrue(result["embedded_vanilla_states_matches_reference"])
        self.assertEqual(result["waypoint_escape_token_utf8_hex"], "c2a7c2a7")

        table = converter.load_vanilla_state_table(VANILLA_STATES)
        audit = table.audit()
        self.assertGreater(audit["record_count"], audit["unique_composite_state_ids"])
        self.assertGreater(audit["duplicate_record_count"], 0)
        self.assertEqual(table.states[0], "minecraft:air")


if __name__ == "__main__":
    unittest.main(verbosity=2)
