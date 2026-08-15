from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import nbtlib


MODULE_PATH = Path(__file__).with_name("convert_vanilla_saveddata.py")
SPEC = importlib.util.spec_from_file_location("convert_vanilla_saveddata", MODULE_PATH)
converter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(converter)


def save(path: Path, data: nbtlib.Compound, version: int = 4671) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nbtlib.File(
        {"DataVersion": nbtlib.Int(version), "data": data}, gzipped=True
    ).save(path, gzipped=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VanillaSavedDataTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = os.environ.get("MIGRATION_TEST_TMPDIR")
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        root = Path(self.temp.name)
        self.source = root / "source" / "world"
        self.target = root / "target" / "world"
        self.source.mkdir(parents=True)
        self.target.mkdir(parents=True)
        nbtlib.File({"Data": nbtlib.Compound({})}, gzipped=True).save(
            self.target / "level.dat", gzipped=True
        )
        self.write_valid_source()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_valid_source(self) -> None:
        tickets = nbtlib.List[nbtlib.Compound](
            [
                nbtlib.Compound(
                    {
                        "type": nbtlib.String("minecraft:forced"),
                        "chunk_pos": nbtlib.IntArray([-15, -8]),
                        "level": nbtlib.Int(31),
                    }
                )
            ]
        )
        save(self.source / "data" / "chunks.dat", nbtlib.Compound({"tickets": tickets}))
        save(
            self.source / "data" / "WorldUUID.dat",
            nbtlib.Compound({"world_uuid": nbtlib.String("7ab3bc33-5355-4b97-b4a5-994b3456eda0")}),
            4556,
        )
        save(
            self.source / "data" / "world_border.dat",
            nbtlib.Compound(
                {
                    "center_x": nbtlib.Double(0),
                    "center_z": nbtlib.Double(1),
                    "size": nbtlib.Double(59999968),
                    "lerp_target": nbtlib.Double(59999968),
                    "lerp_time": nbtlib.Long(0),
                    "safe_zone": nbtlib.Double(5),
                    "damage_per_block": nbtlib.Double(0.2),
                    "warning_blocks": nbtlib.Int(5),
                    "warning_time": nbtlib.Int(6000),
                }
            ),
        )
        save(
            self.source / "data" / "raids.dat",
            nbtlib.Compound({"next_id": nbtlib.Int(3), "tick": nbtlib.Int(42)}),
        )
        save(
            self.source / "data" / "scoreboard.dat",
            nbtlib.Compound(
                {
                    "PlayerScores": nbtlib.List[nbtlib.Compound](
                        [
                            nbtlib.Compound(
                                {
                                    "Objective": nbtlib.String("damage"),
                                    "Locked": nbtlib.Byte(1),
                                    "Score": nbtlib.Int(9),
                                    "Name": nbtlib.String("stone"),
                                }
                            )
                        ]
                    ),
                    "Objectives": nbtlib.List[nbtlib.Compound](
                        [
                            nbtlib.Compound(
                                {
                                    "DisplayName": nbtlib.String("Damage"),
                                    "Name": nbtlib.String("damage"),
                                }
                            )
                        ]
                    ),
                }
            ),
            4556,
        )
        save(
            self.source / "data" / "map_32.dat",
            nbtlib.Compound(
                {
                    "zCenter": nbtlib.Int(-64),
                    "create:stations": nbtlib.List[nbtlib.Compound]([]),
                    "frames": nbtlib.List[nbtlib.Compound](
                        [
                            nbtlib.Compound(
                                {
                                    "pos": nbtlib.IntArray([-247, 64, -95]),
                                    "rotation": nbtlib.Int(270),
                                    "entity_id": nbtlib.Int(133),
                                }
                            )
                        ]
                    ),
                    "dimension": nbtlib.String("minecraft:overworld"),
                    "xCenter": nbtlib.Int(-192),
                    "colors": nbtlib.ByteArray([0] * (128 * 128)),
                }
            ),
        )

    def args(self, *only: str):
        return converter.parse_args(
            [
                "--source-world",
                str(self.source),
                "--target-world",
                str(self.target),
                "--report",
                str(self.target.parent / "report.json"),
                *[value for kind in only for value in ("--only", kind)],
            ]
        )

    def test_full_conversion_and_idempotence(self) -> None:
        self.assertEqual(converter.run(self.args()), 0)
        chunks = nbtlib.load(self.target / "data" / "chunks.dat", gzipped=True)
        self.assertEqual(list(map(int, chunks["data"]["Forced"])), [-30064771087])
        world_uuid = nbtlib.load(self.target / "data" / "WorldUUID.dat", gzipped=True)
        self.assertEqual(
            str(world_uuid["data"]["WorldUUID"]["world_uuid"]),
            "7ab3bc33-5355-4b97-b4a5-994b3456eda0",
        )
        level = nbtlib.load(self.target / "level.dat", gzipped=True)
        self.assertEqual(float(level["Data"]["BorderWarningTime"]), 6000)
        raids = nbtlib.load(self.target / "data" / "raids.dat", gzipped=True)
        self.assertEqual(int(raids["data"]["NextAvailableID"]), 3)
        scoreboard = nbtlib.load(self.target / "data" / "scoreboard.dat", gzipped=True)
        objective = scoreboard["data"]["Objectives"][0]
        self.assertEqual(str(objective["CriteriaName"]), "dummy")
        self.assertEqual(str(objective["DisplayName"]), '"Damage"')
        map_data = nbtlib.load(
            self.target / "data" / "map_32.dat", gzipped=True
        )["data"]
        self.assertIsInstance(map_data["banners"], nbtlib.List)
        self.assertEqual(len(map_data["banners"]), 0)
        self.assertEqual(len(map_data["frames"]), 1)
        self.assertIn("create:stations", map_data)
        before = {
            path: sha(path)
            for path in [
                self.target / "level.dat",
                *sorted((self.target / "data").glob("*.dat")),
            ]
        }
        self.assertEqual(converter.run(self.args()), 0)
        self.assertEqual(before, {path: sha(path) for path in before})

    def test_missing_optional_saveddata_is_reported_and_skipped(self) -> None:
        for relative in (
            "data/WorldUUID.dat",
            "data/world_border.dat",
            "data/scoreboard.dat",
            "data/raids.dat",
            "DIM-1/data/raids.dat",
        ):
            (self.source / relative).unlink(missing_ok=True)
        self.assertEqual(converter.run(self.args()), 0)
        report = nbtlib.load(self.target / "data" / "chunks.dat", gzipped=True)
        self.assertEqual(list(map(int, report["data"]["Forced"])), [-30064771087])
        value = json.loads((self.target.parent / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(value["skipped_missing"]), {"border", "raids", "scoreboard", "world_uuid"}
        )

    def test_typed_compounds_are_key_order_insensitive(self) -> None:
        first = nbtlib.Compound(
            {"b": nbtlib.Int(2), "a": nbtlib.String("one")}
        )
        second = nbtlib.Compound(
            {"a": nbtlib.String("one"), "b": nbtlib.Int(2)}
        )
        self.assertEqual(converter.typed(first), converter.typed(second))

    def test_portal_ticket_blocks_without_writes(self) -> None:
        chunks_path = self.source / "data" / "chunks.dat"
        root = nbtlib.load(chunks_path, gzipped=True)
        root["data"]["tickets"].append(
            nbtlib.Compound(
                {
                    "type": nbtlib.String("minecraft:portal"),
                    "chunk_pos": nbtlib.IntArray([1, 2]),
                    "level": nbtlib.Int(30),
                    "ticks_left": nbtlib.Long(100),
                }
            )
        )
        root.save(chunks_path, gzipped=True)
        sentinel = self.target / "sentinel"
        sentinel.write_bytes(b"unchanged")
        with self.assertRaises(converter.ConversionError):
            converter.run(self.args())
        self.assertEqual(sentinel.read_bytes(), b"unchanged")
        self.assertFalse((self.target / "data" / "WorldUUID.dat").exists())

    def test_active_modern_raid_blocks(self) -> None:
        raid_path = self.source / "data" / "raids.dat"
        root = nbtlib.load(raid_path, gzipped=True)
        root["data"]["raids"] = nbtlib.List[nbtlib.Compound]([nbtlib.Compound({})])
        root.save(raid_path, gzipped=True)
        with self.assertRaises(converter.ConversionError):
            converter.run(self.args("raids"))

    def test_formal_1211_target_schema_is_preserved(self) -> None:
        chunks = nbtlib.Compound({"Forced": nbtlib.LongArray([converter.pack_chunk(4, 5)])})
        save(self.source / "data" / "chunks.dat", chunks, 3955)
        raids = nbtlib.Compound(
            {
                "NextAvailableID": nbtlib.Int(7),
                "Tick": nbtlib.Int(8),
                "Raids": nbtlib.List[nbtlib.Compound]([nbtlib.Compound({"Id": nbtlib.Int(1)})]),
            }
        )
        save(self.source / "data" / "raids.dat", raids, 3955)
        self.assertEqual(converter.run(self.args("chunks", "raids")), 0)
        target_raids = nbtlib.load(self.target / "data" / "raids.dat", gzipped=True)
        self.assertEqual(len(target_raids["data"]["Raids"]), 1)

    def test_unknown_scoreboard_schema_blocks(self) -> None:
        path = self.source / "data" / "scoreboard.dat"
        root = nbtlib.load(path, gzipped=True)
        root["data"]["Objectives"][0]["Unknown"] = nbtlib.Int(1)
        root.save(path, gzipped=True)
        with self.assertRaises(converter.ConversionError):
            converter.run(self.args("scoreboard"))

    def test_map_existing_banners_and_unknown_payload_are_preserved(self) -> None:
        path = self.source / "data" / "map_32.dat"
        root = nbtlib.load(path, gzipped=True)
        root["data"]["banners"] = nbtlib.List[nbtlib.Compound](
            [
                nbtlib.Compound(
                    {
                        "pos": nbtlib.IntArray([1, 64, 2]),
                        "color": nbtlib.String("red"),
                        "unknown_payload": nbtlib.Long(9),
                    }
                )
            ]
        )
        root["data"]["mod:opaque"] = nbtlib.ByteArray([1, 2, 3])
        before = converter.typed(root)
        root.save(path, gzipped=True)

        self.assertEqual(converter.run(self.args("maps")), 0)
        target = nbtlib.load(self.target / "data" / "map_32.dat", gzipped=True)
        self.assertEqual(converter.typed(target), before)
        report = json.loads(
            (self.target.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["metrics"]["maps"]["normalized_missing_banners"], 0)

    def test_map_malformed_banner_list_blocks_all_map_writes(self) -> None:
        bad = self.source / "data" / "map_33.dat"
        save(
            bad,
            nbtlib.Compound(
                {
                    "dimension": nbtlib.String("minecraft:overworld"),
                    "colors": nbtlib.ByteArray([0] * (128 * 128)),
                    "banners": nbtlib.String("not-a-list"),
                }
            ),
        )
        sentinel = self.target / "data" / "map_32.dat"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_bytes(b"unchanged")
        with self.assertRaisesRegex(converter.ConversionError, "banners must be a list"):
            converter.run(self.args("maps"))
        self.assertEqual(sentinel.read_bytes(), b"unchanged")
        self.assertFalse((self.target / "data" / "map_33.dat").exists())

    def test_map_report_records_field_level_repair_and_hashes(self) -> None:
        source = self.source / "data" / "map_32.dat"
        source_hash = sha(source)
        self.assertEqual(converter.run(self.args("maps")), 0)
        report = json.loads(
            (self.target.parent / "report.json").read_text(encoding="utf-8")
        )
        record = report["metrics"]["maps"]["records"]["map_32.dat"]
        output = report["outputs"][0]
        self.assertEqual(record["source_sha256"].lower(), source_hash)
        self.assertTrue(record["banners_added"])
        self.assertEqual(record["frames"], 1)
        self.assertTrue(record["other_fields_preserved"])
        self.assertEqual(output["sha256"].lower(), sha(self.target / "data" / "map_32.dat"))
        sidecar = self.target.parent / converter.MAP_SIDECAR_RELATIVE
        rows = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["map_id"], 32)
        self.assertIsNone(rows[0]["banner_index"])
        self.assertEqual(rows[0]["source_sha256"].lower(), source_hash)
        self.assertEqual(rows[0]["repair"], "add-empty-banners-list")

    def test_portal_ticket_in_nether_blocks_all_dimensions(self) -> None:
        path = self.source / "DIM-1" / "data" / "chunks.dat"
        save(
            path,
            nbtlib.Compound(
                {
                    "tickets": nbtlib.List[nbtlib.Compound](
                        [
                            nbtlib.Compound(
                                {
                                    "type": nbtlib.String("minecraft:portal"),
                                    "chunk_pos": nbtlib.IntArray([3, 4]),
                                    "level": nbtlib.Int(30),
                                    "ticks_left": nbtlib.Long(10),
                                }
                            )
                        ]
                    )
                }
            ),
        )
        with self.assertRaisesRegex(converter.ConversionError, "portal ticket"):
            converter.run(self.args("chunks"))
        self.assertFalse((self.target / "data" / "chunks.dat").exists())

    def test_divergent_dimension_border_blocks(self) -> None:
        source = self.source / "data" / "world_border.dat"
        nether = self.source / "DIM-1" / "data" / "world_border.dat"
        nether.parent.mkdir(parents=True)
        root = nbtlib.load(source, gzipped=True)
        root["data"]["warning_time"] = nbtlib.Int(17)
        root.save(nether, gzipped=True)
        before = sha(self.target / "level.dat")
        with self.assertRaisesRegex(converter.ConversionError, "borders differ"):
            converter.run(self.args("border"))
        self.assertEqual(sha(self.target / "level.dat"), before)

    def test_keyboard_interrupt_rolls_back_all_committed_files(self) -> None:
        first = self.target / "a.dat"
        second = self.target / "b.dat"
        save(first, nbtlib.Compound({"value": nbtlib.Int(1)}))
        save(second, nbtlib.Compound({"value": nbtlib.Int(2)}))
        before = {first: sha(first), second: sha(second)}
        plans = {
            first: converter.new_file(nbtlib.Compound({"value": nbtlib.Int(3)})),
            second: converter.new_file(nbtlib.Compound({"value": nbtlib.Int(4)})),
        }
        original_replace = converter.os.replace
        commit_calls = 0

        def interrupt_second_commit(source, target):
            nonlocal commit_calls
            if str(source).endswith(".migration.tmp"):
                commit_calls += 1
                if commit_calls == 2:
                    raise KeyboardInterrupt()
            return original_replace(source, target)

        with mock.patch.object(converter.os, "replace", side_effect=interrupt_second_commit):
            with self.assertRaises(KeyboardInterrupt):
                converter.write_transaction(plans)
        self.assertEqual(before, {first: sha(first), second: sha(second)})
        self.assertEqual(list(self.target.glob("*.migration.bak")), [])

    def test_interrupt_after_replace_rolls_back_replaced_destination(self) -> None:
        first = self.target / "a.dat"
        second = self.target / "b.dat"
        save(first, nbtlib.Compound({"value": nbtlib.Int(1)}))
        save(second, nbtlib.Compound({"value": nbtlib.Int(2)}))
        before = {first: sha(first), second: sha(second)}
        plans = {
            first: converter.new_file(nbtlib.Compound({"value": nbtlib.Int(3)})),
            second: converter.new_file(nbtlib.Compound({"value": nbtlib.Int(4)})),
        }
        original_replace = converter.os.replace
        commit_calls = 0

        def interrupt_after_second_replace(source, target):
            nonlocal commit_calls
            result = original_replace(source, target)
            if str(source).endswith(".migration.tmp"):
                commit_calls += 1
                if commit_calls == 2:
                    raise KeyboardInterrupt()
            return result

        with mock.patch.object(
            converter.os, "replace", side_effect=interrupt_after_second_replace
        ):
            with self.assertRaises(KeyboardInterrupt):
                converter.write_transaction(plans)
        self.assertEqual(before, {first: sha(first), second: sha(second)})
        self.assertEqual(list(self.target.glob("*.migration.bak")), [])

    def test_target_cannot_be_inside_source(self) -> None:
        args = self.args("chunks")
        args.target_world = self.source / "nested"
        with self.assertRaises(converter.ConversionError):
            converter.run(args)

    def test_target_cannot_be_ancestor_of_source(self) -> None:
        args = self.args("chunks")
        args.target_world = self.source.parent
        with self.assertRaises(converter.ConversionError):
            converter.run(args)

    def test_formal_neoforge_mod_forced_is_preserved(self) -> None:
        mod_forced = nbtlib.List[nbtlib.Compound](
            [
                nbtlib.Compound(
                    {
                        "Controller": nbtlib.String("example:loader"),
                        "ModForced": nbtlib.List[nbtlib.Compound](
                            [
                                nbtlib.Compound(
                                    {
                                        "Chunk": nbtlib.Long(converter.pack_chunk(1, 2)),
                                        "Blocks": nbtlib.List[nbtlib.Compound](
                                            [
                                                nbtlib.Compound(
                                                    {
                                                        "X": nbtlib.Int(1),
                                                        "Y": nbtlib.Int(64),
                                                        "Z": nbtlib.Int(2),
                                                    }
                                                )
                                            ]
                                        ),
                                    }
                                )
                            ]
                        ),
                    }
                )
            ]
        )
        save(
            self.source / "data" / "chunks.dat",
            nbtlib.Compound(
                {"Forced": nbtlib.LongArray([]), "ModForced": mod_forced}
            ),
            3955,
        )
        converter.run(self.args("chunks"))
        target = nbtlib.load(self.target / "data" / "chunks.dat", gzipped=True)
        self.assertEqual(
            str(target["data"]["ModForced"][0]["Controller"]), "example:loader"
        )

    def test_stale_backup_blocks_without_deleting_recovery_file(self) -> None:
        path = self.target / "a.dat"
        save(path, nbtlib.Compound({"value": nbtlib.Int(1)}))
        backup = path.with_name(path.name + ".migration.bak")
        backup.write_bytes(b"recovery")
        with self.assertRaisesRegex(converter.ConversionError, "stale"):
            converter.write_transaction(
                {path: converter.new_file(nbtlib.Compound({"value": nbtlib.Int(2)}))}
            )
        self.assertEqual(backup.read_bytes(), b"recovery")

    def test_existing_conversion_lock_blocks_and_is_left_untouched(self) -> None:
        lock = converter.conversion_lock_path(self.target.resolve())
        contents = (
            b'{"pid": 9876, "created_at_utc": "2026-08-09T00:00:00+00:00", '
            b'"target_world": "held", "token": "existing"}\n'
        )
        lock.write_bytes(contents)
        with self.assertRaisesRegex(converter.ConversionLockError, "left untouched"):
            converter.run(self.args("chunks"))
        self.assertEqual(lock.read_bytes(), contents)
        self.assertFalse((self.target / "data" / "chunks.dat").exists())
        self.assertFalse((self.target.parent / "report.json").exists())

    def test_conversion_lock_is_released_after_success(self) -> None:
        lock = converter.conversion_lock_path(self.target.resolve())
        self.assertEqual(converter.run(self.args("chunks")), 0)
        self.assertFalse(lock.exists())

    def test_conversion_lock_is_released_after_conversion_error(self) -> None:
        lock = converter.conversion_lock_path(self.target.resolve())
        with mock.patch.object(
            converter,
            "_run_locked",
            side_effect=converter.ConversionError("planned conversion failure"),
        ):
            with self.assertRaisesRegex(converter.ConversionError, "planned"):
                converter.run(self.args("chunks"))
        self.assertFalse(lock.exists())
        report = json.loads(
            (self.target.parent / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "BLOCKED")

    def test_conversion_lock_is_released_after_keyboard_interrupt(self) -> None:
        lock = converter.conversion_lock_path(self.target.resolve())
        with mock.patch.object(converter, "_run_locked", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                converter.run(self.args("chunks"))
        self.assertFalse(lock.exists())

    def test_concurrent_process_is_blocked_by_conversion_lock(self) -> None:
        lock = converter.conversion_lock_path(self.target.resolve())
        second_report = self.target.parent / "second-report.json"
        command = [
            sys.executable,
            str(MODULE_PATH),
            "--source-world",
            str(self.source),
            "--target-world",
            str(self.target),
            "--report",
            str(second_report),
            "--only",
            "chunks",
        ]
        with converter.TargetConversionLock(self.target.resolve()):
            contents = lock.read_bytes()
            metadata = json.loads(contents.decode("utf-8"))
            self.assertEqual(metadata["pid"], os.getpid())
            self.assertEqual(metadata["target_world"], str(self.target.resolve()))
            self.assertIn("created_at_utc", metadata)
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("conversion lock already exists", completed.stderr)
            self.assertIn("operator recovery", completed.stderr)
            self.assertEqual(lock.read_bytes(), contents)
            self.assertFalse(second_report.exists())
        self.assertFalse(lock.exists())


if __name__ == "__main__":
    unittest.main()
