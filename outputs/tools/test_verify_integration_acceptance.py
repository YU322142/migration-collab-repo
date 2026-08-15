from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load("integration_acceptance_test_module", "verify_integration_acceptance.py")
migration = load("integration_acceptance_migration", "prepare_fast_migration.py")
final_gate = load("integration_acceptance_final_gate", "final_release_gate.py")


class IntegrationAcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = os.environ.get("MIGRATION_TEST_TMPDIR")
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.staging = self.root / "staging"
        self.target = self.root / "target"
        self.evidence = self.root / "evidence"
        self.mods = self.target / "mods"
        for path in (
            self.source / "config",
            self.source / "world/data",
            self.staging / "config",
            self.staging / "world/data",
            self.target / "config",
            self.target / "world/data",
            self.target / "logs",
            self.target / "migration-reports",
            self.mods,
            self.evidence,
        ):
            path.mkdir(parents=True, exist_ok=True)
        (self.source / "server.properties").write_text("online-mode=false\n", encoding="ascii")
        (self.staging / "server.properties").write_text("online-mode=false\n", encoding="ascii")
        (self.target / "server.properties").write_text("online-mode=false\n", encoding="ascii")
        self.make_jar(self.mods / "mineastr-0.6.25.jar")
        self.make_core_inputs()
        self.write_config()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def make_jar(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("META-INF/neoforge.mods.toml", 'modId="mineastr"\n')

    def make_core_inputs(self) -> None:
        runtime = gate.scan_runtime_mods(self.mods)
        self.runtime_manifest = self.evidence / "runtime.json"
        self.write_json(
            self.runtime_manifest,
            {
                "schema": 1,
                "world": str((self.target / "world").resolve()),
                "mods": str(self.mods.resolve()),
                "runtime_mod_manifest": runtime,
            },
        )
        self.prepare = self.evidence / "prepare.json"
        self.write_json(
            self.prepare,
            {
                "schema": 1,
                "status": "PREPARED",
                "output": str(self.target.resolve()),
                "staging": str(self.staging.resolve()),
            },
        )
        cold = (
            "[Server thread/INFO]: Done (1.0s)!\n"
            "[Server thread/INFO]: [Rcon: Reloading!]\n"
            "[Server thread/INFO]: ThreadedAnvilChunkStorage: All dimensions are saved\n"
            "[Server thread/INFO]: [Rcon: Saved the game]\n"
            "[Server thread/INFO]: Stopping server\n"
        )
        restart = (
            "[Server thread/INFO]: Done (1.0s)!\n"
            "[Server thread/INFO]: [Rcon: Saved the game]\n"
            "minecraft:overworld minecraft:the_nether minecraft:the_end\n"
            "[Server thread/INFO]: Stopping server\n"
        )
        self.cold_log = self.target / "logs/cold.log"
        self.restart_log = self.target / "logs/restart.log"
        self.cold_log.write_text(cold, encoding="ascii")
        self.restart_log.write_text(restart, encoding="ascii")

        self.loaded_reports = []
        loaded = {
            "schema": 1,
            "source": str(self.staging.resolve()),
            "target": str(self.target.resolve()),
            "counts": {
                "source_block_entities": 7031,
                "target_block_entities": 7031,
                "source_attached_entities": 122,
                "target_attached_entities": 122,
            },
            "missing_block_entities": [],
            "missing_attached_entities": [],
            "changed_attached_entities": [],
            "suspicious_attached_entities": [],
        }
        for number in (1, 2):
            path = self.evidence / f"loaded-{number}.json"
            self.write_json(path, loaded)
            self.loaded_reports.append(path)

        comparisons = {
            f"v{index:04d}": {
                "status": "PASS",
                "sections": {"offers": True, "attributes": True},
            }
            for index in range(1193)
        }
        self.villager = self.evidence / "villager.json"
        self.write_json(
            self.villager,
            {
                "status": "PASS",
                "source_root": str(self.source.resolve()),
                "target_game_dir": str(self.target.resolve()),
                "summary": {
                    "expected": 1193,
                    "compared": 1193,
                    "passed": 1193,
                    "failed": 0,
                    "section_failures": {},
                },
                "source": {
                    "missing_slots": [],
                    "missing_entities": [],
                    "baseline_mismatches": [],
                },
                "target": {"duplicate_uuids": [], "missing": [], "extra": []},
                "comparisons": comparisons,
            },
        )
        self.poi_runtime = self.evidence / "poi-runtime.json"
        self.write_json(
            self.poi_runtime,
            {
                "schema": 1,
                "status": "PASS",
                "world": str((self.target / "world").resolve()),
                "records": 17606,
                "errors": [],
                "duplicates": [],
                "allowed_data_versions": [3839, 3955, 4556, 4671],
                "data_versions": {"3839": 1, "3955": 1, "4556": 1, "4671": 1},
            },
        )
        self.poi_compare = self.evidence / "poi-compare.json"
        self.write_json(
            self.poi_compare,
            {
                "status": "PASS",
                "source_records": 17606,
                "target_records": 17606,
                "missing_count": 0,
                "extra_count": 0,
                "changed_count": 0,
                "missing": [],
                "extra": [],
                "changed": [],
            },
        )

        tracks_bytes = b"tracks"
        logistics_bytes = b"logistics"
        for root in (self.staging, self.target):
            (root / "world/data/create_tracks.dat").write_bytes(tracks_bytes)
            (root / "world/data/create_logistics.dat").write_bytes(logistics_bytes)
        self.create_tracks = self.evidence / "create-tracks.json"
        self.write_json(
            self.create_tracks,
            {
                "status": "CONVERTED",
                "blockers": [],
                "rail_graphs": 4,
                "signal_groups": 79,
                "trains": 4,
                "dimensions": 2,
                "item_stacks_scanned": 1670,
                "schema_counts": {"conditions": 6},
            },
        )
        self.create_logistics = self.evidence / "create-logistics.json"
        self.write_json(
            self.create_logistics,
            {
                "status": "CONVERTED",
                "blockers": [],
                "networks": 1,
                "links": 1,
                "promises": 41,
                "item_stacks_scanned": 41,
            },
        )
        self.create_runtime = self.evidence / "create-runtime.json"
        self.write_json(
            self.create_runtime,
            {
                "left": str((self.staging / "world/data/create_tracks.dat").resolve()),
                "right": str((self.target / "world/data/create_tracks.dat").resolve()),
                "equivalent": True,
                "left_semantic_sha256": "A" * 64,
                "right_semantic_sha256": "A" * 64,
                "counts": {"left": {"graphs": 4, "signals": 79, "trains": 4}, "right": {"graphs": 4, "signals": 79, "trains": 4}},
                "differences": [],
            },
        )
        self.saved_verify = self.evidence / "saved-verify.json"
        self.write_json(self.saved_verify, {"schema": 1, "phase": "verify", "status": "VERIFIED_READ_ONLY", "pending_saveddata": []})
        self.chunks = self.evidence / "chunks.json"
        self.write_json(
            self.chunks,
            {
                "schema": 1,
                "status": "READY_PORTAL_ZERO",
                "exit_code": 0,
                "source_world": str((self.target / "world").resolve()),
                "blockers": [],
                "totals": {"ticket_count": 7, "forced_count": 7, "portal_count": 0},
            },
        )

        guard_source = {"root": str(self.source.resolve()), "files": {}, "trees": {}}
        guard_staging = {"root": str(self.staging.resolve()), "files": {}, "trees": {}}
        self.sanitizer = self.target / "migration-reports/sanitizer.json"
        self.write_json(
            self.sanitizer,
            {
                "schema": 1,
                "status": "SANITIZED_TARGET_COPY",
                "target_game_dir": str(self.target.resolve()),
                "target_mods_dir": str(self.mods.resolve()),
                "protected_tree_unchanged": True,
                "source_guard_before": guard_source,
                "source_guard_after": guard_source,
                "staging_guard_before": guard_staging,
                "staging_guard_after": guard_staging,
                "resource_sanitization": {
                    "schema": 1,
                    "status": "ALREADY_CLEAN",
                    "world": str((self.target / "world").resolve()),
                    "mods": str(self.mods.resolve()),
                    "server_properties": str((self.target / "server.properties").resolve()),
                    "changes": [],
                    "changed_files": 0,
                    "runtime_mod_manifest": gate.scan_runtime_mods(self.mods),
                },
            },
        )

        source_config = self.source / "config/mineastr-common.json"
        source_config.write_text("{}\n", encoding="ascii")
        keys = [f"key{index}" for index in range(32)] + ["commandApprovalTimeoutSeconds", "commandMaxPendingApprovals"]
        toml = "\n".join(f'{key} = {300 if key == "commandApprovalTimeoutSeconds" else 128 if key == "commandMaxPendingApprovals" else index}' for index, key in enumerate(keys)) + "\n"
        staged_toml = self.staging / "config/mineastr-common.toml"
        target_toml = self.target / "config/mineastr-common.toml"
        staged_toml.write_text(toml, encoding="ascii")
        target_toml.write_text(toml, encoding="ascii")
        self.mine_config = self.evidence / "mine-config.json"
        self.write_json(
            self.mine_config,
            {
                "status": "CHANGED",
                "source_key_count": 32,
                "target_key_count": 34,
                "preserved_keys": [f"key{index}" for index in range(32)],
                "defaulted_keys": ["commandApprovalTimeoutSeconds", "commandMaxPendingApprovals"],
                "sensitive_values_redacted": True,
                "source_sha256": gate.sha256(source_config),
                "target_sha256": gate.sha256(staged_toml),
            },
        )
        for root, content in ((self.source, b"source-cache"), (self.staging, b"target-cache"), (self.target, b"runtime-cache")):
            (root / "world/data/mineastr_sign_translations.dat").write_bytes(content)
        self.mine_cache = self.evidence / "mine-cache.json"
        self.write_json(
            self.mine_cache,
            {
                "status": "CHANGED",
                "target_version": 2,
                "entries": 40,
                "automatic_entries": 40,
                "manual_entries": 0,
                "skipped_entries": 0,
                "output_usable_entries": 40,
                "translation_value_count": 40,
                "deterministic_gzip": True,
                "entry_identifiers_redacted": True,
                "content_values_redacted": True,
                "source_file_sha256": gate.sha256(self.source / "world/data/mineastr_sign_translations.dat"),
                "target_file_sha256": gate.sha256(self.staging / "world/data/mineastr_sign_translations.dat"),
                "target_semantic_sha256": "A" * 64,
            },
        )

        self.baseline = self.evidence / "baseline.json"
        self.write_json(self.baseline, migration.staged_baseline_manifest(self.source, self.staging))

    def write_config(self) -> None:
        self.config = self.evidence / "inputs.json"
        self.capsules = self.evidence / "capsules"
        self.report = self.evidence / "integration.json"
        self.write_json(
            self.config,
            {
                "schema": 1,
                "source_game_dir": str(self.source.resolve()),
                "staging_game_dir": str(self.staging.resolve()),
                "target_game_dir": str(self.target.resolve()),
                "target_mods_dir": str(self.mods.resolve()),
                "runtime_manifest": str(self.runtime_manifest.resolve()),
                "evidence_dir": str(self.capsules.resolve()),
                "expected_mineastr_jar_sha256": gate.sha256(self.mods / "mineastr-0.6.25.jar"),
                "artifacts": {
                    "candidate_prepare_report": str(self.prepare.resolve()),
                    "cold_start_log": str(self.cold_log.resolve()),
                    "restart_log": str(self.restart_log.resolve()),
                    "loaded_region_reports": [str(path.resolve()) for path in self.loaded_reports],
                    "villager_report": str(self.villager.resolve()),
                    "poi_runtime_report": str(self.poi_runtime.resolve()),
                    "poi_compare_report": str(self.poi_compare.resolve()),
                    "create_tracks_conversion_report": str(self.create_tracks.resolve()),
                    "create_logistics_conversion_report": str(self.create_logistics.resolve()),
                    "create_tracks_runtime_report": str(self.create_runtime.resolve()),
                    "saveddata_verify_report": str(self.saved_verify.resolve()),
                    "target_chunks_report": str(self.chunks.resolve()),
                    "sanitizer_report": str(self.sanitizer.resolve()),
                    "mineastr_config_report": str(self.mine_config.resolve()),
                    "mineastr_cache_report": str(self.mine_cache.resolve()),
                    "source_baseline": str(self.baseline.resolve()),
                },
            },
        )

    def build(self):
        ctx = gate.load_context(self.config)
        with mock.patch.object(gate, "load_nbt_cache_semantics", return_value=("A" * 64, 2, 40)):
            return gate.build_report(ctx, self.report)

    def test_complete_matrix_matches_final_release_contract(self) -> None:
        report, code = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], gate.PASS)
        self.assertEqual({row["name"] for row in report["checks"]}, set(gate.CHECK_NAMES))
        self.assertTrue(all(row["status"] == "PASS" for row in report["checks"]))
        with (
            mock.patch.object(
                final_gate,
                "_load_tool",
                return_value=gate,
            ),
            mock.patch.object(
                gate,
                "load_nbt_cache_semantics",
                return_value=("A" * 64, 2, 40),
            ),
        ):
            accepted = final_gate.validate_integration_report(
                self.report,
                self.source,
                self.staging,
                self.target,
                report["runtime_bundle_sha256"],
            )
        self.assertEqual(set(accepted["checks"]), set(gate.CHECK_NAMES))
        with mock.patch.object(gate, "load_nbt_cache_semantics", return_value=("A" * 64, 2, 40)):
            verified, verify_code = gate.validate_bound_report(
                self.report,
                self.source,
                self.staging,
                self.target,
                report["runtime_bundle_sha256"],
            )
        self.assertEqual(verify_code, 0)
        self.assertEqual(verified["status"], "VERIFIED_PASS")

    def test_existing_report_rehashes_every_input(self) -> None:
        self.build()
        self.cold_log.write_text(self.cold_log.read_text(encoding="ascii") + "unchanging-semantics\n", encoding="ascii")
        ctx = gate.load_context(self.config)
        with (
            mock.patch.object(
                gate, "load_nbt_cache_semantics", return_value=("A" * 64, 2, 40)
            ),
            self.assertRaises(gate.GateError) as caught,
        ):
            gate.validate_existing_report(ctx, self.report)
        self.assertEqual(caught.exception.code, "INTEGRATION_INPUT_DRIFT")

    def test_villager_evidence_from_other_target_is_no_go(self) -> None:
        value = json.loads(self.villager.read_text(encoding="utf-8"))
        value["target_game_dir"] = str((self.root / "other-target").resolve())
        self.write_json(self.villager, value)
        report, code = self.build()
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], gate.NO_GO)
        codes = {item["code"] for item in report["blockers"]}
        self.assertIn("VILLAGER_TARGET_MISMATCH", codes)

    def test_runtime_jar_drift_fails_all_eight_checks(self) -> None:
        self.make_jar(self.mods / "drift.jar")
        report, code = self.build()
        self.assertEqual(code, 2)
        self.assertEqual(len(report["checks"]), 8)
        self.assertTrue(all(row["status"] == "FAIL" for row in report["checks"]))
        self.assertEqual({item["code"] for item in report["blockers"]}, {"RUNTIME_JAR_DRIFT"})

    def test_missing_artifact_is_no_go_not_synthetic_pass(self) -> None:
        self.poi_compare.unlink()
        report, code = self.build()
        self.assertEqual(code, 2)
        row = next(row for row in report["checks"] if row["name"] == "villager_poi_gate")
        self.assertEqual(row["status"], "FAIL")
        self.assertIn("ARTIFACT_MISSING", {item["code"] for item in row["blockers"]})


if __name__ == "__main__":
    unittest.main()
