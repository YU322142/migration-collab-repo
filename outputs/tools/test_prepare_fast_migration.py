from __future__ import annotations

import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("prepare_fast_migration.py")
SPEC = importlib.util.spec_from_file_location("prepare_fast_migration", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class FastMigrationTest(unittest.TestCase):
    def d_temp(self):
        root = Path(os.environ.get("MIGRATION_TEST_TMP", r"D:\Trans\migration-audit-work\tmp"))
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def test_staging_cannot_be_inside_source(self):
        source = Path(r"D:\Trans\source")
        with self.assertRaisesRegex(ValueError, "must not be inside"):
            migration.ensure_distinct(source, source / "target")
        migration.ensure_distinct(source, Path(r"D:\Trans\target"))

    def test_source_cannot_be_inside_staging(self):
        staging = Path(r"D:\Trans\staging")
        with self.assertRaisesRegex(ValueError, "source-game-dir"):
            migration.ensure_distinct(staging / "source", staging)

    def test_target_sanitization_isolated_from_source_and_staging(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            target = base / "target"
            source.mkdir()
            staging.mkdir()
            (target / "world" / "datapacks" / "bukkit").mkdir(parents=True)
            (target / "mods").mkdir()
            (target / "server.properties").write_text(
                "function-permission-level=2\n", encoding="ascii"
            )
            (target / "world" / "datapacks" / "bukkit" / "pack.mcmeta").write_text(
                '{"pack":{"description":"bukkit","min_format":[88,0],"max_format":[88,0]}}',
                encoding="utf-8",
            )
            source_before = migration.critical_manifest(source, False)
            staging_before = migration.critical_manifest(staging, False)
            result = migration.sanitize_target_copy(source, staging, target)
            self.assertEqual(result["status"], "SANITIZED_TARGET_COPY")
            self.assertTrue(result["protected_tree_unchanged"])
            self.assertEqual(
                migration.critical_manifest(source, False), source_before
            )
            self.assertEqual(
                migration.critical_manifest(staging, False), staging_before
            )
            self.assertEqual(
                json.loads(
                    (target / "world" / "datapacks" / "bukkit" / "pack.mcmeta")
                    .read_text(encoding="utf-8")
                )["pack"]["pack_format"],
                48,
            )
            with self.assertRaisesRegex(ValueError, "overlaps"):
                migration.sanitize_target_copy(source, staging, staging)

    def test_non_d_work_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be on D"):
            migration.ensure_d_path(Path(r"C:\temp\target"), "target")

    def test_world_workers_must_not_exceed_logical_cpu_count(self):
        argv = [str(MODULE_PATH), "manifest", "--world-workers", "5"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(
            migration.os, "cpu_count", return_value=4
        ), mock.patch.object(sys, "stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                migration.main()
        self.assertEqual(raised.exception.code, 2)

    def test_world_verify_blocks_unsupported_create_fluids(self):
        with self.d_temp() as temporary:
            report = Path(temporary) / "world-verify.json"
            report.write_text(
                json.dumps(
                    {
                        "unsupported_create_fluids": [
                            {"id": "create:fluid_pipe", "reason": "unknown fluid schema"}
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = migration.world_verify_blockers(report, False)

            self.assertEqual(
                result["blockers"]["unsupported_create_fluids"][0]["id"],
                "create:fluid_pipe",
            )

    def test_copy_is_fresh_and_excludes_runtime_only_inputs(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            (source / "world" / "data").mkdir(parents=True)
            (source / "world" / "region").mkdir()
            (source / "world_nether").mkdir()
            (source / "config").mkdir()
            (source / "EasyAuth").mkdir()
            (source / "world" / "region" / "r.0.0.mca").write_bytes(b"region")
            (source / "world" / "ledger.sqlite").write_bytes(b"ledger")
            (source / "world" / "session.lock").write_bytes(b"lock")
            (source / "world_nether" / "level.dat").write_bytes(b"legacy")
            (source / "config" / "example.toml").write_text("x=1\n", encoding="ascii")
            (source / "EasyAuth" / "easyauth.db").write_bytes(b"sqlite")
            (source / "EasyAuth" / "easyauth.db-wal").write_bytes(b"wal")
            (source / "server.properties").write_text("online-mode=true\n", encoding="ascii")

            migration.copy_filtered(source, target)

            self.assertEqual(
                (target / "world" / "region" / "r.0.0.mca").read_bytes(), b"region"
            )
            self.assertFalse((target / "world" / "ledger.sqlite").exists())
            self.assertFalse((target / "world" / "session.lock").exists())
            self.assertEqual(
                (target / "migration-input" / "EasyAuth" / "easyauth.db").read_bytes(),
                b"sqlite",
            )
            self.assertEqual(
                (
                    target
                    / "migration-input"
                    / "EasyAuth"
                    / "easyauth.db-wal"
                ).read_bytes(),
                b"wal",
            )
            self.assertEqual(
                (
                    target
                    / "migration-input"
                    / "legacy-dimensions"
                    / "world_nether"
                    / "level.dat"
                ).read_bytes(),
                b"legacy",
            )
            with self.assertRaises(FileExistsError):
                migration.copy_filtered(source, target)

    def test_schematic_copy_gate_hashes_every_file(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            first = source / "schematics" / "uploaded" / "u" / "a.nbt"
            second = source / "schematics" / "b.nbt"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True, exist_ok=True)
            first.write_bytes(b"schematic-a")
            second.write_bytes(b"schematic-b")

            migration.copy_filtered(source, target)
            gate = migration.validate_schematic_tree_copy(source, target)

            self.assertEqual(gate["status"], "MATCH")
            self.assertEqual(gate["files"], 2)
            self.assertEqual(gate["bytes"], 22)
            self.assertEqual(
                [entry["path"] for entry in gate["entries"]],
                ["b.nbt", "uploaded/u/a.nbt"],
            )
            self.assertEqual(len(gate["content_sha256"]), 64)

    def test_schematic_copy_gate_blocks_missing_extra_and_mismatch(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            source_file = source / "schematics" / "uploaded" / "u" / "a.nbt"
            target_file = target / "schematics" / "uploaded" / "u" / "a.nbt"
            source_file.parent.mkdir(parents=True)
            target_file.parent.mkdir(parents=True)
            source_file.write_bytes(b"authority")
            target_file.write_bytes(b"different")
            (target / "schematics" / "extra.nbt").write_bytes(b"extra")

            with self.assertRaisesRegex(
                RuntimeError, "extra=.*extra.nbt.*mismatched=.*uploaded/u/a.nbt"
            ):
                migration.validate_schematic_tree_copy(source, target)

            (target / "schematics" / "extra.nbt").unlink()
            target_file.unlink()
            with self.assertRaisesRegex(
                RuntimeError, "missing=.*uploaded/u/a.nbt"
            ):
                migration.validate_schematic_tree_copy(source, target)

    def test_excluded_input_manifest_records_hashes(self):
        with self.d_temp() as temporary:
            source = Path(temporary) / "source"
            (source / "world").mkdir(parents=True)
            (source / "EasyAuth").mkdir()
            (source / "world" / "ledger.sqlite").write_bytes(b"ledger")
            (source / "EasyAuth" / "easyauth.db").write_bytes(b"auth")
            result = migration.excluded_input_manifest(source)
            self.assertEqual(set(result), {"world/ledger.sqlite", "EasyAuth/easyauth.db"})
            self.assertEqual(result["world/ledger.sqlite"]["bytes"], 6)
            self.assertEqual(len(result["EasyAuth/easyauth.db"]["sha256"]), 64)

    def test_full_hash_delta_detects_same_size_same_mtime_change(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            (source / "config").mkdir(parents=True)
            config = source / "config" / "value.toml"
            config.write_bytes(b"aaaa")
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)

            original = config.stat()
            config.write_bytes(b"bbbb")
            os.utime(config, ns=(original.st_atime_ns, original.st_mtime_ns))
            current = migration.source_input_snapshot(source)
            delta = migration.compare_snapshots(baseline, current)

            self.assertEqual(len(delta["modified"]), 1)
            self.assertEqual(
                delta["modified"][0]["after"]["source"], "config/value.toml"
            )
            self.assertEqual(delta["added"], [])
            self.assertEqual(delta["deleted"], [])

    def test_snapshot_detects_added_and_deleted_inputs(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            (source / "world" / "stats").mkdir(parents=True)
            old = source / "world" / "stats" / "old.json"
            old.write_text("{}\n", encoding="ascii")
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)

            old.unlink()
            (source / "world" / "stats" / "new.json").write_text(
                "{\"x\":1}\n", encoding="ascii"
            )
            delta = migration.compare_snapshots(
                baseline, migration.source_input_snapshot(source)
            )
            self.assertEqual(
                [entry["source"] for entry in delta["deleted"]],
                ["world/stats/old.json"],
            )
            self.assertEqual(
                [entry["source"] for entry in delta["added"]],
                ["world/stats/new.json"],
            )

    def test_region_selector_preserves_dimension_and_kind_path(self):
        entries = [
            {
                "source": "world/region/r.0.0.mca",
                "target": "world/region/r.0.0.mca",
                "kind": "world-region-nbt",
            },
            {
                "source": "world/DIM-1/entities/r.-2.3.mca",
                "target": "world/DIM-1/entities/r.-2.3.mca",
                "kind": "world-region-nbt",
            },
        ]
        self.assertEqual(
            [migration.region_selector(entry) for entry in entries],
            ["region/r.0.0.mca", "DIM-1/entities/r.-2.3.mca"],
        )
        self.assertEqual(
            migration.classify_input("world/DIM1/poi/r.0.0.mca"), "raw"
        )

    def test_vanilla_saveddata_paths_are_not_raw(self):
        expected = {
            "world/data/chunks.dat": "vanilla-saveddata-chunks",
            "world/DIM-1/data/chunks.dat": "vanilla-saveddata-chunks",
            "world/DIM1/data/raids_end.dat": "vanilla-saveddata-raids",
            "world/data/WorldUUID.dat": "vanilla-saveddata-world_uuid",
            "world/data/world_border.dat": "vanilla-saveddata-border",
            "world/data/scoreboard.dat": "vanilla-saveddata-scoreboard",
            "world/data/map_32.dat": "vanilla-saveddata-maps",
        }
        self.assertEqual(
            {path: migration.classify_input(path) for path in expected}, expected
        )

    def test_map_saveddata_is_selected_and_marker_bound(self):
        entries = [
            {
                "source": "world/data/map_32.dat",
                "target": "world/data/map_32.dat",
                "kind": "vanilla-saveddata-maps",
            }
        ]
        self.assertEqual(
            migration.vanilla_saveddata_kinds_for_sources(
                {"world/data/map_32.dat"}
            ),
            {"maps"},
        )
        self.assertEqual(
            migration.derived_output_paths(entries),
            [migration.MAP_BANNER_SIDECAR_RELATIVE, "world/data/map_32.dat"],
        )
        self.assertEqual(migration.derived_output_paths(entries, {"maps"}), [])

    def test_advancement_inputs_are_converter_owned_and_marker_bound(self):
        relative = (
            "world/advancements/00000000-0000-4000-8000-000000000001.json"
        )
        entry = {
            "source": relative,
            "target": relative,
            "kind": migration.ADVANCEMENT_INPUT_KIND,
        }
        self.assertEqual(
            migration.classify_input(relative), migration.ADVANCEMENT_INPUT_KIND
        )
        self.assertTrue(migration.is_converter_input(entry))
        self.assertEqual(
            migration.derived_output_paths([entry]),
            [migration.ADVANCEMENT_SIDECAR_RELATIVE, relative],
        )

    def test_advancement_converter_wrapper_rejects_escaped_output(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            target = base / "target"
            tools = base / "tools"
            report = base / "report.json"
            source.mkdir()
            target.mkdir()
            tools.mkdir()
            (tools / migration.ADVANCEMENT_CONVERTER_NAME).write_text(
                "# test\n", encoding="ascii"
            )
            (tools / migration.ADVANCEMENT_POLICY_NAME).write_text(
                "{}\n", encoding="ascii"
            )

            def fake_run(label, arguments, env, commands):
                migration.atomic_json(
                    report,
                    {
                        "status": "CONVERTED",
                        "outputs": [{"path": str(base / "escaped.json")}],
                    },
                )

            with mock.patch.object(migration, "run_tool", side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, "escaped its target"):
                    migration.convert_player_advancements(
                        source,
                        target,
                        tools,
                        {},
                        [],
                        report,
                        "test",
                    )

    def test_pending_chunks_are_excluded_from_preheat_marker_outputs(self):
        entries = [
            {"source": path, "target": path, "kind": migration.classify_input(path)}
            for path in (
                "world/data/chunks.dat",
                "world/DIM-1/data/chunks.dat",
                "world/data/WorldUUID.dat",
                "world/data/world_border.dat",
                "world/data/raids.dat",
                "world/data/scoreboard.dat",
            )
        ]
        outputs = migration.derived_output_paths(entries, {"chunks"})
        self.assertNotIn("world/data/chunks.dat", outputs)
        self.assertNotIn("world/DIM-1/data/chunks.dat", outputs)
        self.assertIn("world/data/WorldUUID.dat", outputs)
        self.assertIn("world/level.dat", outputs)
        self.assertIn("world/data/raids.dat", outputs)
        self.assertIn("world/data/scoreboard.dat", outputs)

    def test_final_conversion_gate_rejects_pending_saveddata(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            reports = base / "reports"
            (source / "config").mkdir(parents=True)
            (source / "config" / "plain.toml").write_text(
                "value=1\n", encoding="ascii"
            )
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            baseline_path = reports / "baseline.json"
            migration.atomic_json(baseline_path, baseline)
            conversion_report = reports / "convert.json"
            migration.atomic_json(conversion_report, {"status": "PREHEATED"})
            marker_path = migration.conversion_marker_path(staging)
            migration.atomic_json(
                marker_path,
                migration.make_conversion_marker(
                    source,
                    staging,
                    baseline,
                    conversion_report,
                    staging,
                    pending_saveddata={"chunks"},
                ),
            )

            with self.assertRaisesRegex(RuntimeError, "pending SavedData: chunks"):
                migration.validate_final_conversion_gate(
                    marker_path, source, staging, baseline_path
                )

    def test_final_conversion_gate_rejects_source_delta(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            reports = base / "reports"
            (source / "config").mkdir(parents=True)
            config = source / "config" / "plain.toml"
            config.write_text("value=1\n", encoding="ascii")
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            baseline_path = reports / "baseline.json"
            migration.atomic_json(baseline_path, baseline)
            conversion_report = reports / "convert.json"
            migration.atomic_json(conversion_report, {"status": "CONVERTED_STAGING"})
            marker_path = migration.conversion_marker_path(staging)
            migration.atomic_json(
                marker_path,
                migration.make_conversion_marker(
                    source, staging, baseline, conversion_report, staging
                ),
            )
            config.write_text("value=2\n", encoding="ascii")

            with self.assertRaisesRegex(RuntimeError, "source changed after staging"):
                migration.validate_final_conversion_gate(
                    marker_path, source, staging, baseline_path
                )

    def test_verify_main_rejects_pending_before_world_dry_run(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            reports = base / "reports"
            report = reports / "verify.json"
            baseline_path = reports / "baseline.json"
            (source / "config").mkdir(parents=True)
            (source / "config" / "plain.toml").write_text(
                "value=1\n", encoding="ascii"
            )
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            migration.atomic_json(baseline_path, baseline)
            conversion_report = reports / "convert.json"
            migration.atomic_json(conversion_report, {"status": "PREHEATED"})
            migration.atomic_json(
                migration.conversion_marker_path(staging),
                migration.make_conversion_marker(
                    source,
                    staging,
                    baseline,
                    conversion_report,
                    staging,
                    pending_saveddata={"chunks"},
                ),
            )
            argv = [
                str(MODULE_PATH),
                "verify",
                "--source-game-dir",
                str(source),
                "--staging-game-dir",
                str(staging),
                "--report",
                str(report),
                "--baseline-manifest",
                str(baseline_path),
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                migration, "run_tool"
            ) as run_tool:
                with self.assertRaisesRegex(RuntimeError, "pending SavedData"):
                    migration.main()
            run_tool.assert_not_called()
            value = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(value["status"], "BLOCKED_PENDING_SAVEDDATA")

    def test_refresh_preparation_passes_only_changed_region(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            transaction = base / "transaction"
            reports = base / "reports"
            (source / "world" / "region").mkdir(parents=True)
            (source / "world" / "level.dat").write_bytes(b"level-support")
            region = source / "world" / "region" / "r.0.0.mca"
            region.write_bytes(b"old-region")
            (source / "server.properties").write_text(
                "online-mode=true\n", encoding="ascii"
            )
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            region.write_bytes(b"new-region")
            current = migration.source_input_snapshot(source)
            delta = migration.compare_snapshots(baseline, current)

            fake_jar = base / "waypoint.jar"
            fake_jar.write_bytes(b"fake-audited-jar")
            (staging / "mods").mkdir()
            (staging / "mods" / fake_jar.name).write_bytes(fake_jar.read_bytes())
            commands = []

            def fake_run_tool(label, arguments, env, commands):
                if label == "player-advancements-refresh":
                    report_path = Path(arguments[arguments.index("--report") + 1])
                    migration.atomic_json(
                        report_path,
                        {
                            "status": "ALREADY_TARGET",
                            "outputs": [],
                        },
                    )

            with mock.patch.object(
                migration, "run_tool", side_effect=fake_run_tool
            ) as run_tool:
                replacements, deletions, summary = (
                    migration.prepare_refresh_transaction(
                        source,
                        staging,
                        transaction,
                        current,
                        delta,
                        MODULE_PATH.parent,
                        os.environ.copy(),
                        commands,
                        reports,
                        fake_jar,
                        migration.sha256(fake_jar),
                        False,
                        world_workers=4,
                    )
                )

            self.assertEqual(deletions, set())
            self.assertIn("world/region/r.0.0.mca", replacements)
            self.assertEqual(summary["selected_regions"], ["region/r.0.0.mca"])
            converter_args = run_tool.call_args.args[1]
            only_index = converter_args.index("--only-region")
            self.assertEqual(converter_args[only_index + 1], "region/r.0.0.mca")
            self.assertEqual(converter_args.count("--only-region"), 1)
            workers_index = converter_args.index("--workers")
            self.assertEqual(converter_args[workers_index + 1], "4")

    def test_refresh_preparation_reconciles_all_world_inputs_without_delta(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            transaction = base / "transaction"
            reports = base / "reports"
            (source / "world" / "region").mkdir(parents=True)
            (source / "world" / "entities").mkdir()
            (source / "world" / "playerdata").mkdir()
            (source / "world" / "level.dat").write_bytes(b"level")
            (source / "world" / "region" / "r.-1.-1.mca").write_bytes(
                b"block-region"
            )
            (source / "world" / "entities" / "r.0.0.mca").write_bytes(
                b"entity-region"
            )
            (source / "world" / "playerdata" / "player.dat").write_bytes(
                b"player"
            )
            (source / "server.properties").write_text(
                "online-mode=true\n", encoding="ascii"
            )
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            current = migration.source_input_snapshot(source)
            delta = migration.compare_snapshots(baseline, current)
            self.assertFalse(delta["added"] or delta["modified"] or delta["deleted"])

            fake_jar = base / "waypoint.jar"
            fake_jar.write_bytes(b"fake-audited-jar")
            (staging / "mods").mkdir()
            (staging / "mods" / fake_jar.name).write_bytes(fake_jar.read_bytes())

            def fake_run_tool(label, arguments, env, commands):
                if label == "player-advancements-refresh":
                    report_path = Path(arguments[arguments.index("--report") + 1])
                    migration.atomic_json(
                        report_path,
                        {"status": "ALREADY_TARGET", "outputs": []},
                    )

            with mock.patch.object(
                migration, "run_tool", side_effect=fake_run_tool
            ) as run_tool:
                replacements, deletions, summary = (
                    migration.prepare_refresh_transaction(
                        source,
                        staging,
                        transaction,
                        current,
                        delta,
                        MODULE_PATH.parent,
                        os.environ.copy(),
                        [],
                        reports,
                        fake_jar,
                        migration.sha256(fake_jar),
                        False,
                        reconcile_converters=True,
                    )
                )

            self.assertEqual(deletions, set())
            self.assertEqual(
                set(replacements),
                {
                    "server.properties",
                    "world/level.dat",
                    "world/playerdata/player.dat",
                    "world/entities/r.0.0.mca",
                    "world/region/r.-1.-1.mca",
                },
            )
            self.assertEqual(
                summary["selected_regions"],
                ["entities/r.0.0.mca", "region/r.-1.-1.mca"],
            )
            self.assertEqual(
                summary["converter_reconciliation"],
                {"required": True, "inputs": 5, "world_inputs": 5},
            )
            world_call = next(
                call for call in run_tool.call_args_list
                if call.args[0] == "world-refresh-convert"
            )
            converter_args = world_call.args[1]
            selectors = [
                converter_args[index + 1]
                for index, value in enumerate(converter_args)
                if value == "--only-region"
            ]
            self.assertEqual(
                selectors, ["entities/r.0.0.mca", "region/r.-1.-1.mca"]
            )
            workers_index = converter_args.index("--workers")
            self.assertEqual(converter_args[workers_index + 1], "1")

    def test_validation_overlay_never_mutates_hardlinked_staging_file(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            staging = base / "staging"
            prepared = base / "prepared"
            validation = base / "validation"
            staging_file = staging / "schematics" / "uploaded" / "u" / "x.nbt"
            prepared_file = prepared / "schematics" / "uploaded" / "u" / "x.nbt"
            staging_file.parent.mkdir(parents=True)
            prepared_file.parent.mkdir(parents=True)
            staging_file.write_bytes(b"old-schematic")
            prepared_file.write_bytes(b"new-schematic")
            waypoint = base / "waypoint.jar"
            waypoint.write_bytes(b"jar")
            entry = {
                "source": "schematics/uploaded/u/x.nbt",
                "target": "schematics/uploaded/u/x.nbt",
                "kind": "raw",
            }

            migration.build_validation_target(
                staging,
                prepared,
                validation,
                [entry],
                [],
                waypoint,
            )

            self.assertEqual(staging_file.read_bytes(), b"old-schematic")
            self.assertEqual(
                (validation / entry["target"]).read_bytes(), b"new-schematic"
            )

    def test_transaction_commit_replaces_and_deletes(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            staging = base / "staging"
            prepared = base / "prepared"
            backup = base / "backup"
            discard = base / "discard"
            (staging / "world").mkdir(parents=True)
            (prepared / "world").mkdir(parents=True)
            (staging / "world" / "replace.dat").write_bytes(b"old")
            (staging / "world" / "delete.dat").write_bytes(b"gone")
            replacement = prepared / "world" / "replace.dat"
            replacement.write_bytes(b"new")

            journal = migration.commit_transaction(
                staging,
                {"world/replace.dat": replacement},
                {"world/delete.dat"},
                backup,
                discard,
            )

            self.assertEqual(
                (staging / "world" / "replace.dat").read_bytes(), b"new"
            )
            self.assertFalse((staging / "world" / "delete.dat").exists())
            self.assertEqual(len(journal), 2)

    def test_transaction_failure_restores_every_original(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            staging = base / "staging"
            prepared = base / "prepared"
            backup = base / "backup"
            discard = base / "discard"
            (staging / "world").mkdir(parents=True)
            (prepared / "world").mkdir(parents=True)
            first = staging / "world" / "a.dat"
            second = staging / "world" / "b.dat"
            first.write_bytes(b"old-a")
            second.write_bytes(b"old-b")
            prepared_first = prepared / "world" / "a.dat"
            prepared_second = prepared / "world" / "b.dat"
            prepared_first.write_bytes(b"new-a")
            prepared_second.write_bytes(b"new-b")
            real_replace = os.replace
            failed = False

            def fail_second_install(source, target):
                nonlocal failed
                if (
                    not failed
                    and Path(source) == prepared_second
                    and Path(target) == second
                ):
                    failed = True
                    raise OSError("injected commit failure")
                return real_replace(source, target)

            with mock.patch.object(migration.os, "replace", fail_second_install):
                with self.assertRaisesRegex(RuntimeError, "rolled back"):
                    migration.commit_transaction(
                        staging,
                        {
                            "world/a.dat": prepared_first,
                            "world/b.dat": prepared_second,
                        },
                        set(),
                        backup,
                        discard,
                    )

            self.assertEqual(first.read_bytes(), b"old-a")
            self.assertEqual(second.read_bytes(), b"old-b")

    def test_first_backup_rename_failure_keeps_original_and_rolls_back_cleanly(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            staging = base / "staging"
            prepared = base / "prepared"
            (staging / "world").mkdir(parents=True)
            (prepared / "world").mkdir(parents=True)
            target = staging / "world" / "x.dat"
            replacement = prepared / "world" / "x.dat"
            target.write_bytes(b"old")
            replacement.write_bytes(b"new")
            real_replace = os.replace
            failed = False

            def fail_backup(source, destination):
                nonlocal failed
                if not failed and Path(source) == target:
                    failed = True
                    raise OSError("injected first backup failure")
                return real_replace(source, destination)

            journal = base / "transaction-journal.json"
            with mock.patch.object(migration.os, "replace", fail_backup):
                with self.assertRaisesRegex(RuntimeError, "rolled back"):
                    migration.commit_transaction(
                        staging,
                        {"world/x.dat": replacement},
                        set(),
                        base / "backup",
                        base / "discard",
                        journal,
                    )
            self.assertEqual(target.read_bytes(), b"old")
            state = json.loads(
                migration.transaction_state_path(journal).read_text(encoding="utf-8")
            )
            self.assertEqual(state["status"], "ROLLED_BACK")

    def test_source_stability_check_fails_closed(self):
        with self.d_temp() as temporary:
            source = Path(temporary) / "source"
            (source / "config").mkdir(parents=True)
            path = source / "config" / "value.toml"
            path.write_text("x=1\n", encoding="ascii")
            snapshot = migration.source_input_snapshot(source)
            path.write_text("x=2\n", encoding="ascii")
            with self.assertRaisesRegex(
                migration.SourceChangedError, "changed after the full-hash"
            ):
                migration.assert_source_snapshot_stable(source, snapshot)

    def test_session_lock_probe_is_read_only_and_accepts_unlocked_file(self):
        with self.d_temp() as temporary:
            world = Path(temporary) / "world"
            world.mkdir()
            self.assertEqual(migration.probe_session_lock(world)["status"], "ABSENT")
            lock = world / "session.lock"
            lock.write_bytes(b"12345678")
            before = lock.read_bytes()
            result = migration.probe_session_lock(world)
            self.assertEqual(result["status"], "UNLOCKED_READ_ONLY_PROBE")
            self.assertEqual(lock.read_bytes(), before)

    @unittest.skipUnless(os.name == "nt", "Windows lock semantics")
    def test_session_lock_probe_rejects_held_lock(self):
        import msvcrt

        with self.d_temp() as temporary:
            world = Path(temporary) / "world"
            world.mkdir()
            lock = world / "session.lock"
            lock.write_bytes(b"12345678")
            with lock.open("r+b") as held:
                held.seek(0)
                msvcrt.locking(held.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    with self.assertRaisesRegex(RuntimeError, "session.lock is held"):
                        migration.probe_session_lock(world)
                finally:
                    held.seek(0)
                    msvcrt.locking(held.fileno(), msvcrt.LK_UNLCK, 1)

    def test_unchanged_passthrough_corruption_is_blocked(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            (source / "config").mkdir(parents=True)
            (source / "config" / "plain.toml").write_bytes(b"source")
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            current = migration.source_input_snapshot(source)
            delta = migration.compare_snapshots(baseline, current)
            (staging / "config" / "plain.toml").write_bytes(b"damage")

            with self.assertRaisesRegex(RuntimeError, "passthrough_mismatches"):
                migration.verify_unchanged_staging_inputs(
                    staging, baseline["entries"], delta
                )

    def test_stage_main_writes_exact_baseline(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            report = base / "reports" / "stage.json"
            baseline_path = base / "reports" / "baseline.json"
            (source / "world" / "region").mkdir(parents=True)
            (source / "world" / "region" / "r.0.0.mca").write_bytes(b"region")
            argv = [
                str(MODULE_PATH),
                "stage",
                "--source-game-dir",
                str(source),
                "--staging-game-dir",
                str(staging),
                "--report",
                str(report),
                "--baseline-manifest",
                str(baseline_path),
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(migration.main(), 0)

            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            self.assertEqual(baseline["files"], 1)
            self.assertEqual(
                baseline["entries"][0]["sha256"],
                migration.sha256(staging / "world" / "region" / "r.0.0.mca"),
            )

    def test_refresh_main_blocks_deletion_without_touching_staging(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            reports = base / "reports"
            baseline_path = reports / "baseline.json"
            report = reports / "refresh.json"
            (source / "config").mkdir(parents=True)
            source_file = source / "config" / "removed.toml"
            source_file.write_bytes(b"original")
            migration.copy_filtered(source, staging)
            migration.atomic_json(
                baseline_path,
                migration.staged_baseline_manifest(source, staging),
            )
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            conversion_report = reports / "convert.json"
            migration.atomic_json(conversion_report, {"status": "CONVERTED_STAGING"})
            migration.atomic_json(
                migration.conversion_marker_path(staging),
                migration.make_conversion_marker(
                    source,
                    staging,
                    baseline,
                    conversion_report,
                    staging,
                ),
            )
            staging_file = staging / "config" / "removed.toml"
            before = staging_file.read_bytes()
            source_file.unlink()
            argv = [
                str(MODULE_PATH),
                "refresh",
                "--source-game-dir",
                str(source),
                "--staging-game-dir",
                str(staging),
                "--report",
                str(report),
                "--baseline-manifest",
                str(baseline_path),
            ]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(RuntimeError, "deletions blocked"):
                    migration.main()

            self.assertEqual(staging_file.read_bytes(), before)
            refresh_report = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(refresh_report["status"], "BLOCKED_SOURCE_DELETIONS")

    def test_refresh_main_no_change_requires_and_validates_marker(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            reports = base / "reports"
            baseline_path = reports / "baseline.json"
            report = reports / "refresh.json"
            (source / "config").mkdir(parents=True)
            (source / "config" / "plain.toml").write_text(
                "value=1\n", encoding="ascii"
            )
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            migration.atomic_json(baseline_path, baseline)
            conversion_report = reports / "convert.json"
            migration.atomic_json(conversion_report, {"status": "CONVERTED_STAGING"})
            migration.atomic_json(
                migration.conversion_marker_path(staging),
                migration.make_conversion_marker(
                    source,
                    staging,
                    baseline,
                    conversion_report,
                    staging,
                ),
            )
            argv = [
                str(MODULE_PATH),
                "refresh",
                "--source-game-dir",
                str(source),
                "--staging-game-dir",
                str(staging),
                "--report",
                str(report),
                "--baseline-manifest",
                str(baseline_path),
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(migration.main(), 0)
            value = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(value["status"], "REFRESH_NO_CONTENT_CHANGES")
            self.assertEqual(len(value["source_stop_probes"]), 2)
            self.assertEqual(len(value["staging_stop_probes"]), 2)

    def test_refresh_main_reconciles_legacy_marker_without_source_delta(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            reports = base / "reports"
            baseline_path = reports / "baseline.json"
            report = reports / "refresh.json"
            (source / "world" / "region").mkdir(parents=True)
            (source / "world" / "level.dat").write_bytes(b"level")
            (source / "world" / "region" / "r.0.0.mca").write_bytes(b"region")
            (source / "server.properties").write_text(
                "online-mode=true\n", encoding="ascii"
            )
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            migration.atomic_json(baseline_path, baseline)
            conversion_report = reports / "convert.json"
            migration.atomic_json(conversion_report, {"status": "CONVERTED_STAGING"})
            legacy_marker = migration.make_conversion_marker(
                source, staging, baseline, conversion_report, staging
            )
            legacy_marker["schema"] = 1
            legacy_marker.pop("converter_fingerprints")
            migration.atomic_json(
                migration.conversion_marker_path(staging), legacy_marker
            )

            fake_jar = base / "waypoint.jar"
            fake_jar.write_bytes(b"fake-audited-jar")
            (staging / "mods").mkdir()
            (staging / "mods" / fake_jar.name).write_bytes(fake_jar.read_bytes())
            argv = [
                str(MODULE_PATH),
                "refresh",
                "--source-game-dir",
                str(source),
                "--staging-game-dir",
                str(staging),
                "--report",
                str(report),
                "--baseline-manifest",
                str(baseline_path),
                "--waypoint-fire-jar",
                str(fake_jar),
                "--waypoint-fire-sha256",
                migration.sha256(fake_jar),
            ]
            def fake_run_tool(label, arguments, env, commands):
                if label == "player-advancements-refresh":
                    report_path = Path(arguments[arguments.index("--report") + 1])
                    migration.atomic_json(
                        report_path,
                        {
                            "status": "ALREADY_TARGET",
                            "outputs": [],
                        },
                    )

            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                migration, "run_tool", side_effect=fake_run_tool
            ) as run_tool:
                self.assertEqual(migration.main(), 0)

            value = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(value["status"], "REFRESHED_INCREMENTALLY")
            self.assertTrue(
                value["conversion_marker_before"]["converter_reconciliation"][
                    "required"
                ]
            )
            self.assertEqual(
                value["transaction"]["converter_reconciliation"],
                {"required": True, "inputs": 3, "world_inputs": 3},
            )
            self.assertIn(
                "world-refresh-convert",
                [call.args[0] for call in run_tool.call_args_list],
            )
            refreshed_marker = json.loads(
                migration.conversion_marker_path(staging).read_text(encoding="utf-8")
            )
            self.assertEqual(
                refreshed_marker["schema"], migration.CONVERSION_MARKER_SCHEMA
            )
            self.assertEqual(
                migration.converter_reconciliation_status(refreshed_marker)["required"],
                False,
            )

    def test_commit_persists_applied_and_rolled_back_journals(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            staging = base / "staging"
            prepared = base / "prepared"
            (staging / "world").mkdir(parents=True)
            (prepared / "world").mkdir(parents=True)
            target = staging / "world" / "x.dat"
            replacement = prepared / "world" / "x.dat"
            target.write_bytes(b"old")
            replacement.write_bytes(b"new")
            journal_path = base / "transaction-journal.json"
            migration.commit_transaction(
                staging,
                {"world/x.dat": replacement},
                set(),
                base / "backup",
                base / "discard",
                journal_path,
            )
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            state = json.loads(
                migration.transaction_state_path(journal_path).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(journal["status"], "PREPARED")
            self.assertEqual(state["status"], "APPLIED")
            self.assertEqual(state["operation_state"], "REPLACEMENT_INSTALLED")

            second_prepared = base / "prepared2" / "world" / "x.dat"
            second_prepared.parent.mkdir(parents=True)
            second_prepared.write_bytes(b"newer")
            failed_journal = base / "failed-journal.json"
            real_replace = os.replace
            failed = False

            def fail_install(source, destination):
                nonlocal failed
                if not failed and Path(source) == second_prepared:
                    failed = True
                    raise OSError("injected")
                return real_replace(source, destination)

            with mock.patch.object(migration.os, "replace", fail_install):
                with self.assertRaisesRegex(RuntimeError, "rolled back"):
                    migration.commit_transaction(
                        staging,
                        {"world/x.dat": second_prepared},
                        set(),
                        base / "backup2",
                        base / "discard2",
                        failed_journal,
                    )
            failed_value = json.loads(
                migration.transaction_state_path(failed_journal).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(failed_value["status"], "ROLLED_BACK")
            self.assertEqual(target.read_bytes(), b"new")

    def test_orphan_transaction_is_discovered_fail_closed(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            staging = base / "server-copy"
            staging.mkdir()
            orphan = base / ".server-copy-refresh-crash"
            orphan.mkdir()
            journal = orphan / "transaction-journal.json"
            migration.atomic_json(
                journal,
                {"schema": 1, "status": "PREPARED", "operations": []},
            )
            migration.atomic_json(
                migration.transaction_state_path(journal),
                {"schema": 1, "status": "APPLYING"},
            )
            result = migration.orphan_refresh_transactions(staging)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["status"], "APPLYING")

    def test_conversion_marker_blocks_missing_or_damaged_output(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            (source / "config").mkdir(parents=True)
            (source / "config" / "mineastr-common.json").write_text(
                "{}\n", encoding="ascii"
            )
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            output = staging / "config" / "mineastr-common.toml"
            output.write_text("enabled=false\n", encoding="ascii")
            report = base / "convert.json"
            migration.atomic_json(report, {"status": "CONVERTED_STAGING"})
            marker_path = migration.conversion_marker_path(staging)
            migration.atomic_json(
                marker_path,
                migration.make_conversion_marker(
                    source, staging, baseline, report, staging
                ),
            )
            migration.validate_conversion_marker(
                marker_path, source, staging, baseline
            )
            output.write_text("damaged=true\n", encoding="ascii")
            with self.assertRaisesRegex(RuntimeError, "integrity check failed"):
                migration.validate_conversion_marker(
                    marker_path, source, staging, baseline
                )

    def test_conversion_marker_requires_reconciliation_for_legacy_or_stale_tool(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            (source / "config").mkdir(parents=True)
            (source / "config" / "plain.toml").write_text(
                "value=1\n", encoding="ascii"
            )
            migration.copy_filtered(source, staging)
            baseline = migration.staged_baseline_manifest(source, staging)
            report = base / "convert.json"
            migration.atomic_json(report, {"status": "CONVERTED_STAGING"})
            marker = migration.make_conversion_marker(
                source, staging, baseline, report, staging
            )
            self.assertEqual(
                set(marker["converter_fingerprints"]),
                {
                    *migration.LOCAL_CONVERTER_NAMES,
                    "xiyuslogin/migrate_easyauth.py",
                },
            )
            marker_path = migration.conversion_marker_path(staging)

            legacy = dict(marker)
            legacy["schema"] = 1
            legacy.pop("converter_fingerprints")
            migration.atomic_json(marker_path, legacy)
            with self.assertRaisesRegex(RuntimeError, "fingerprint is stale or missing"):
                migration.validate_conversion_marker(
                    marker_path, source, staging, baseline
                )
            accepted_for_refresh = migration.validate_conversion_marker(
                marker_path,
                source,
                staging,
                baseline,
                allow_converter_reconciliation=True,
            )
            self.assertEqual(accepted_for_refresh["schema"], 1)

            stale = dict(marker)
            stale["converter_fingerprints"] = {
                migration.WORLD_CONVERTER_NAME: {
                    "bytes": 1,
                    "sha256": "0" * 64,
                }
            }
            migration.atomic_json(marker_path, stale)
            with self.assertRaisesRegex(RuntimeError, "fingerprint is stale or missing"):
                migration.validate_conversion_marker(
                    marker_path, source, staging, baseline
                )

    def test_unknown_dimension_region_is_explicit_blocker(self):
        relative = "world/dimensions/example/moon/region/r.0.0.mca"
        self.assertEqual(
            migration.classify_input(relative), "unsupported-world-region"
        )
        self.assertEqual(
            migration.unsupported_region_inputs(
                [{"source": relative, "kind": "unsupported-world-region"}]
            ),
            [relative],
        )

    def test_derived_target_collision_is_fail_closed(self):
        with self.d_temp() as temporary:
            path = Path(temporary) / "prepared" / "config.toml"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"raw")
            replacements = {"config/mineastr-common.toml": path}
            with self.assertRaisesRegex(RuntimeError, "conflicts"):
                migration.require_free_derived_target(
                    replacements,
                    "config/mineastr-common.toml",
                    "MineAstr config migration",
                )

    def test_sqlite_snapshot_includes_wal_and_passes_integrity(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            database = base / "input" / "easyauth.db"
            database.parent.mkdir(parents=True)
            connection = sqlite3.connect(database)
            try:
                connection.execute("pragma journal_mode=wal")
                connection.execute(
                    "create table easyauth (id integer primary key, username text)"
                )
                connection.execute("insert into easyauth(username) values ('u')")
                connection.commit()
                snapshot = base / "output" / "snapshot.db"
                report = base / "reports" / "sqlite.json"
                result = migration.snapshot_easyauth_database(
                    database, snapshot, report
                )
            finally:
                connection.close()
            self.assertEqual(result["source_integrity_check"], ["ok"])
            self.assertEqual(result["snapshot_integrity_check"], ["ok"])
            self.assertEqual(result["records"], 1)
            verification = sqlite3.connect(snapshot)
            try:
                self.assertEqual(
                    verification.execute("select count(*) from easyauth").fetchone()[0],
                    1,
                )
            finally:
                verification.close()

    def test_sanitize_target_phase_only_mutates_assembled_target_copy(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            target = base / "target"
            for root in (source, staging):
                (root / "world").mkdir(parents=True)
                (root / "world" / "sentinel.dat").write_bytes(
                    f"{root.name}-sentinel".encode("ascii")
                )
            (target / "world" / "datapacks" / "bukkit").mkdir(parents=True)
            (target / "world" / "datapacks" / "bukkit" / "pack.mcmeta").write_text(
                json.dumps(
                    {
                        "pack": {
                            "description": "Bukkit",
                            "min_format": [88, 0],
                            "max_format": [88, 0],
                        }
                    }
                ),
                encoding="utf-8",
            )
            function = (
                target
                / "world"
                / "datapacks"
                / "moon"
                / "data"
                / "moon"
                / "function"
                / "go.mcfunction"
            )
            function.parent.mkdir(parents=True)
            function.write_text("transfer 127.0.0.1 25565\n", encoding="ascii")
            (target / "server.properties").write_text(
                "function-permission-level=2\n", encoding="ascii"
            )
            (target / "mods").mkdir()

            argv = [
                "prepare_fast_migration.py",
                "sanitize-target",
                "--source-game-dir",
                str(source),
                "--staging-game-dir",
                str(staging),
                "--target-game-dir",
                str(target),
                "--hash-all",
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(migration.main(), 0)

            report_path = target / "migration-reports" / "resource-sanitization.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "SANITIZED_TARGET_COPY")
            self.assertTrue(report["protected_tree_unchanged"])
            self.assertEqual(
                report["resource_sanitization"]["status"], "SANITIZED"
            )
            self.assertGreaterEqual(
                report["resource_sanitization"]["changed_files"], 2
            )
            self.assertEqual(
                (source / "world" / "sentinel.dat").read_bytes(),
                b"source-sentinel",
            )
            self.assertEqual(
                (staging / "world" / "sentinel.dat").read_bytes(),
                b"staging-sentinel",
            )
            bukkit = json.loads(
                (
                    target
                    / "world"
                    / "datapacks"
                    / "bukkit"
                    / "pack.mcmeta"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(bukkit["pack"]["pack_format"], 48)
            self.assertNotIn("min_format", bukkit["pack"])
            self.assertEqual(
                (target / "server.properties").read_text(encoding="utf-8"),
                "function-permission-level=3\n",
            )

    def test_sanitize_target_copy_rejects_protected_or_external_mod_paths(self):
        with self.d_temp() as temporary:
            base = Path(temporary)
            source = base / "source"
            staging = base / "staging"
            target = base / "target"
            (source / "world").mkdir(parents=True)
            (staging / "world").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "overlaps"):
                migration.ensure_target_copy_isolated(
                    source,
                    staging,
                    staging / "nested-target",
                    staging / "nested-target" / "mods",
                )

            (target / "world").mkdir(parents=True)
            (target / "server.properties").write_text("\n", encoding="ascii")
            (target / "mods").mkdir()
            with self.assertRaisesRegex(ValueError, "inside target-game-dir"):
                migration.ensure_target_copy_isolated(
                    source,
                    staging,
                    target,
                    base / "external-mods",
                )
            argv = [
                "prepare_fast_migration.py",
                "sanitize-target",
                "--source-game-dir",
                str(source),
                "--staging-game-dir",
                str(staging),
                "--target-game-dir",
                str(target),
                "--report",
                str(staging / "reports" / "unsafe.json"),
            ]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(ValueError, "report must not overlap"):
                    migration.main()


if __name__ == "__main__":
    unittest.main()
