from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import nbtlib

ROOT = Path(__file__).parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load("final_release_gate_test_module", "final_release_gate.py")
migration = load("final_release_gate_migration", "prepare_fast_migration.py")
probe = load("final_release_gate_probe", "probe_cutover_chunks.py")
sanitizer = load("final_release_gate_sanitizer", "sanitize_target_resources.py")
legacy_archiver = load("final_release_gate_legacy_archiver", "archive_legacy_roots.py")
client_verifier = load(
    "final_release_gate_client_verifier", "verify_client_acceptance.py"
)


class FinalReleaseGateTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = os.environ.get("MIGRATION_TEST_TMPDIR")
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.staging = self.root / "staging"
        self.target = self.root / "target"
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.source_world = self.source / "world"
        for relative in (
            "data/chunks.dat",
            "DIM-1/data/chunks.dat",
            "DIM1/data/chunks.dat",
        ):
            self.write_chunks(relative)
        (self.source / "server.properties").write_text(
            "online-mode=false\n", encoding="ascii"
        )
        (self.source / "EasyAuth").mkdir()
        (self.source / "EasyAuth/easyauth.db").write_bytes(b"fixture-auth-snapshot")
        for name in gate.LEGACY_ROOTS:
            legacy = self.source / name
            (legacy / "region").mkdir(parents=True)
            (legacy / "empty").mkdir()
            (legacy / "level.dat").write_bytes((name + "-level").encode("ascii"))
            (legacy / "region/r.0.0.mca").write_bytes(
                (name + "-region").encode("ascii")
            )
        # A clean stop commonly leaves the file.  It is accepted only when the
        # OS lock probe proves that no Minecraft process still owns it.
        (self.source_world / "session.lock").write_bytes(b"stopped")

        migration.copy_filtered(self.source, self.staging)
        baseline = migration.staged_baseline_manifest(self.source, self.staging)
        self.baseline_path = self.evidence / "source-baseline.json"
        self.write_json(self.baseline_path, baseline)
        conversion_report = self.evidence / "refresh.json"
        self.write_json(conversion_report, {"schema": 1, "status": "REFRESHED"})
        (self.staging / "world/xiyus_player_data.json").write_text(
            '{"fixture":{"passwordHash":"redacted"}}\n', encoding="utf-8"
        )
        marker = migration.make_conversion_marker(
            self.source,
            self.staging,
            baseline,
            conversion_report,
            self.staging,
            pending_saveddata=[],
        )
        self.marker_path = migration.conversion_marker_path(self.staging)
        migration.atomic_json(self.marker_path, marker)

        self.chunks_report = self.evidence / "chunks-probe.json"
        self.write_json(self.chunks_report, probe.probe_world(self.source_world))

        (self.target / "world").mkdir(parents=True)
        self.target_mods = self.target / "mods"
        self.target_mods.mkdir()
        (self.target / "server.properties").write_text(
            "online-mode=false\n", encoding="ascii"
        )
        auth_output = self.target / "world/xiyus_player_data.json"
        auth_output.write_text(
            '{"fixture":{"passwordHash":"redacted"}}\n', encoding="utf-8"
        )
        runtime_jar = self.target_mods / "xiyuslogin-test.jar"
        self.make_jar(runtime_jar)
        runtime = sanitizer.runtime_mod_manifest(self.target_mods)
        inner = {
            "schema": 1,
            "world": str((self.target / "world").resolve()),
            "server_properties": str((self.target / "server.properties").resolve()),
            "mods": str(self.target_mods.resolve()),
            "changes": [],
            "runtime_mod_manifest": runtime,
            "changed_files": 0,
            "status": "ALREADY_CLEAN",
        }
        guard = {"root": str(self.root), "files": {}, "trees": {}}
        self.sanitizer_report = (
            self.target / "migration-reports" / "resource-sanitization.json"
        )
        self.write_json(
            self.sanitizer_report,
            {
                "schema": 1,
                "status": "SANITIZED_TARGET_COPY",
                "target_game_dir": str(self.target.resolve()),
                "target_mods_dir": str(self.target_mods.resolve()),
                "resource_sanitization": inner,
                "protected_tree_unchanged": True,
                "source_guard_before": guard,
                "source_guard_after": guard,
                "staging_guard_before": guard,
                "staging_guard_after": guard,
            },
        )
        self.expected_manifest = self.evidence / "expected-runtime.json"
        self.write_json(self.expected_manifest, {"runtime_mod_manifest": runtime})

        self.assembly_report = self.evidence / "production-target-assembly.json"
        self.target_ready_marker = self.target / gate.TARGET_READY_MARKER_RELATIVE
        transaction_id = "0123456789abcdef0123456789abcdef"
        self.write_json(
            self.assembly_report,
            {
                "schema": 1,
                "status": "ASSEMBLED_PRODUCTION_TARGET",
                "transaction_id": transaction_id,
                "target_game_dir": str(self.target.resolve()),
                "target_ready_marker": str(self.target_ready_marker.resolve()),
                "sanitizer_report": str(self.sanitizer_report.resolve()),
                "ready_to_start": True,
            },
        )
        self.write_json(
            self.target_ready_marker,
            {
                "schema": 1,
                "status": "ASSEMBLED_PRODUCTION_TARGET",
                "transaction_id": transaction_id,
                "target_game_dir": str(self.target.resolve()),
                "external_report": str(self.assembly_report.resolve()),
                "sanitizer_report": str(self.sanitizer_report.resolve()),
                "assembly_report_sha256": gate.sha256(self.assembly_report),
                "ready_to_start": True,
            },
        )

        legacy_audit = self.evidence / "legacy-audit.md"
        legacy_audit.write_text(
            "# Legacy audit\n\nStatus: **BLOCKED_LEGACY_WORLD_POLICY_REQUIRED**\n",
            encoding="utf-8",
        )
        legacy_output = self.evidence / "legacy-archives"
        self.legacy_marker = legacy_output / "legacy-policy.json"
        legacy_archiver.build_archives(
            self.source,
            legacy_output,
            legacy_audit,
            self.legacy_marker,
        )
        bundle = runtime["bundle_sha256"]
        client_path = self.make_client_report(bundle)
        auth_source = self.staging / "migration-input/EasyAuth/easyauth.db"
        live_path = self.evidence / "auth-live.json"
        live_scenarios = {}
        for name in sorted(gate.REQUIRED_AUTH_SCENARIOS):
            artifact = self.evidence / "auth-live-evidence" / f"{name}.json"
            self.write_json(
                artifact,
                {
                    "schema": 1,
                    "status": "PASS",
                    "scenario": name,
                    "contains_secrets": False,
                },
            )
            live_scenarios[name] = {
                "status": "PASS",
                "artifacts": [
                    {
                        "path": artifact.relative_to(live_path.parent).as_posix(),
                        "sha256": gate.sha256(artifact),
                        "kind": "redacted-login-transcript",
                        "contains_secrets": False,
                    }
                ],
            }
        self.write_json(
            live_path,
            {
                "schema": 1,
                "status": "PASS",
                "contains_secrets": False,
                "tested_with_secrets": False,
                "source_sha256": gate.sha256(auth_source),
                "output_sha256": gate.sha256(auth_output),
                "candidate_jar_sha256": gate.sha256(runtime_jar),
                "scenarios": live_scenarios,
            },
        )
        auth_verifier = gate._load_tool(
            "verify_auth_readiness.py", "test_final_gate_auth_readiness"
        )
        live_summary = auth_verifier.validate_live_report(
            live_path,
            gate.sha256(auth_source),
            gate.sha256(auth_output),
            gate.sha256(runtime_jar),
        )
        auth_path = self.evidence / "auth.json"
        self.write_json(
            auth_path,
            {
                "schema": 1,
                "status": "READY_AUTH_CUTOVER",
                "exit_code": 0,
                "accounts": {"records": 1, "plaintext_stored": False},
                "idempotence": {
                    "passes": 2,
                    "hashes_equal": True,
                    "manifest_summaries_equal": True,
                    "output_matches_converter": True,
                },
                "live_login": live_summary,
                "source": {
                    "file": "staging/migration-input/EasyAuth/easyauth.db",
                    "bytes": auth_source.stat().st_size,
                    "sha256": gate.sha256(auth_source),
                    "read_only": True,
                    "unchanged_during_gate": True,
                },
                "output": {
                    "file": "world/xiyus_player_data.json",
                    "bytes": auth_output.stat().st_size,
                    "sha256": gate.sha256(auth_output),
                    "semantics_match_source": True,
                },
                "candidate_jar": {
                    "file": runtime_jar.name,
                    "bytes": runtime_jar.stat().st_size,
                    "sha256": gate.sha256(runtime_jar),
                },
            },
        )
        integration_path = self.evidence / "integration.json"
        self.integration_artifacts = {}
        integration_checks = []
        for name in sorted(gate.REQUIRED_INTEGRATION_CHECKS):
            artifact = self.evidence / "integration-evidence" / f"{name}.json"
            self.write_json(
                artifact,
                {"schema": 1, "status": "PASS", "scenario": name},
            )
            self.integration_artifacts[name] = artifact
            integration_checks.append(
                {
                    "name": name,
                    "status": "PASS",
                    "target_game_dir": str(self.target.resolve()),
                    "runtime_bundle_sha256": bundle,
                    "artifact": {
                        "path": str(artifact.resolve()),
                        "bytes": artifact.stat().st_size,
                        "sha256": gate.sha256(artifact),
                    },
                }
            )
        self.write_json(
            integration_path,
            {
                "schema": 1,
                "status": "PASS",
                "category": "integration",
                "target_game_dir": str(self.target.resolve()),
                "runtime_bundle_sha256": bundle,
                "blockers": [],
                "checks": integration_checks,
                "_fixture_bound": True,
            },
        )
        self.pass_reports = {
            "client": [client_path],
            "auth": [auth_path],
            "integration": [integration_path],
        }
        self.original_tool_loader = gate._load_tool

        def validate_bound_fixture(path, source, staging, target, expected_bundle):
            value = json.loads(Path(path).read_text(encoding="utf-8"))
            if value.get("_fixture_bound") is not True:
                raise RuntimeError("fixture integration report has no bound config")
            if (
                Path(source).resolve() != self.source.resolve()
                or Path(staging).resolve() != self.staging.resolve()
                or Path(target).resolve() != self.target.resolve()
                or expected_bundle != bundle
            ):
                raise RuntimeError("fixture integration binding differs from gate")
            summary = gate.stable_file_summary(
                Path(path), "fixture bound integration report"
            )
            return (
                {
                    "schema": 1,
                    "status": "VERIFIED_PASS",
                    "exit_code": 0,
                    "report": summary,
                    "target_game_dir": str(self.target.resolve()),
                    "runtime_bundle_sha256": bundle,
                    "blockers": [],
                    "checks": [
                        {"name": name, "status": "PASS"}
                        for name in sorted(gate.REQUIRED_INTEGRATION_CHECKS)
                    ],
                },
                0,
            )

        self.integration_bound_validator = mock.Mock(side_effect=validate_bound_fixture)
        fixture_tool = SimpleNamespace(
            validate_bound_report=self.integration_bound_validator
        )

        def load_fixture_tool(filename, module_name):
            if filename == "verify_integration_acceptance.py":
                return fixture_tool
            return self.original_tool_loader(filename, module_name)

        self.tool_loader_patch = mock.patch.object(
            gate, "_load_tool", side_effect=load_fixture_tool
        )
        self.tool_loader_patch.start()

    def tearDown(self) -> None:
        self.tool_loader_patch.stop()
        self.temp.cleanup()

    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def write_chunks(self, relative: str) -> None:
        path = self.source_world / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        nbtlib.File(
            {
                "DataVersion": nbtlib.Int(4671),
                "data": nbtlib.Compound({"tickets": nbtlib.List[nbtlib.Compound]()}),
            },
            gzipped=True,
        ).save(path, gzipped=True)

    def make_jar(self, path: Path, entries: list[str] | None = None) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("META-INF/neoforge.mods.toml", 'modId="example"\n')
            for name in entries or []:
                if name != "META-INF/neoforge.mods.toml":
                    archive.writestr(name, b"fixture")

    def make_client_report(self, server_bundle: str) -> Path:
        mods = self.evidence / "client-mods"
        evidence_root = self.evidence / "client-evidence"
        mods.mkdir()
        evidence_root.mkdir()
        rows = []
        for mod_id in sorted(client_verifier.REQUIRED_MOD_IDS):
            jar = mods / f"{mod_id}.jar"
            self.make_jar(jar, list(client_verifier.REQUIRED_BUNDLE_MARKERS[mod_id]))
            rows.append(
                {
                    "file": jar.name,
                    "bytes": jar.stat().st_size,
                    "sha256": gate.sha256(jar),
                    "mod_ids": [mod_id],
                }
            )
        manifest = self.evidence / "client-manifest.json"
        client_bundle = client_verifier.bundle_digest(rows)
        self.write_json(
            manifest,
            {
                "schema": 1,
                "side": "client",
                "file_count": len(rows),
                "bundle_sha256": client_bundle,
                "files": rows,
            },
        )
        suites = {}
        for suite, scenarios in client_verifier.REQUIRED_SCENARIOS.items():
            artifacts = []
            for kind in sorted(client_verifier.REQUIRED_ARTIFACT_KINDS[suite]):
                artifact = evidence_root / f"{suite}-{kind}.txt"
                artifact.write_text(
                    f"redacted {suite} {kind} evidence\n", encoding="utf-8"
                )
                artifacts.append(
                    {
                        "path": artifact.name,
                        "bytes": artifact.stat().st_size,
                        "sha256": gate.sha256(artifact),
                        "kind": kind,
                        "contains_secrets": False,
                    }
                )
            scenario_values = {name: "PASS" for name in scenarios}
            if suite == "xiyuslogin":
                scenario_values = {}
                for name in scenarios:
                    scenario_artifact = evidence_root / f"{suite}-{name}.txt"
                    scenario_artifact.write_text(
                        f"redacted {suite} {name} evidence\n", encoding="utf-8"
                    )
                    scenario_values[name] = {
                        "status": "PASS",
                        "artifacts": [
                            {
                                "path": scenario_artifact.name,
                                "sha256": gate.sha256(scenario_artifact),
                                "kind": "redacted-login-transcript",
                                "contains_secrets": False,
                            }
                        ],
                    }
            suites[suite] = {
                "status": "PASS",
                "client_bundle_sha256": client_bundle,
                "server_bundle_sha256": server_bundle,
                "tested_with_secrets": False,
                "scenarios": scenario_values,
                "artifacts": artifacts,
            }
        evidence = evidence_root / "client-evidence.json"
        self.write_json(
            evidence,
            {
                "schema": 1,
                "status": "PASS",
                "tested_at_utc": "2026-08-09T12:00:00Z",
                "operator": "fixture",
                "contains_secrets": False,
                "environment": {
                    "minecraft_version": "1.21.1",
                    "loader": "NeoForge",
                    "java_major": 21,
                    "address_redacted": True,
                },
                "client_bundle_sha256": client_bundle,
                "server_bundle_sha256": server_bundle,
                "suites": suites,
            },
        )
        report = self.evidence / "client.json"
        value, code = client_verifier.build_report(
            type(
                "ClientArgs",
                (),
                {
                    "evidence_root": evidence_root,
                    "expected_server_bundle_sha256": server_bundle,
                    "client_mods": mods,
                    "bundle_manifest": manifest,
                    "report": report,
                    "evidence": evidence,
                },
            )()
        )
        self.assertEqual(code, 0)
        self.write_json(report, value)
        self.client_evidence_artifact = next(evidence_root.glob("*.txt"))
        return report

    def args(self):
        return type(
            "Args",
            (),
            {
                "source_game_dir": self.source,
                "staging_game_dir": self.staging,
                "baseline_manifest": self.baseline_path,
                "conversion_marker": self.marker_path,
                "chunks_report": self.chunks_report,
                "target_game_dir": self.target,
                "target_mods_dir": self.target_mods,
                "assembly_report": self.assembly_report,
                "sanitizer_report": self.sanitizer_report,
                "expected_runtime_manifest": self.expected_manifest,
                "legacy_policy_marker": self.legacy_marker,
                "client_report": self.pass_reports["client"],
                "auth_report": self.pass_reports["auth"],
                "integration_report": self.pass_reports["integration"],
            },
        )()

    def protected_snapshot(self) -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        for root in (self.source, self.staging, self.target):
            for path in root.rglob("*"):
                if path.is_file():
                    result[str(path.relative_to(root)) + "@" + root.name] = (
                        path.read_bytes()
                    )
        return result

    def update_assembly_report(self, **updates) -> None:
        value = json.loads(self.assembly_report.read_text(encoding="utf-8"))
        value.update(updates)
        self.write_json(self.assembly_report, value)
        marker = json.loads(self.target_ready_marker.read_text(encoding="utf-8"))
        marker["assembly_report_sha256"] = gate.sha256(self.assembly_report)
        self.write_json(self.target_ready_marker, marker)

    def update_ready_marker(self, **updates) -> None:
        marker = json.loads(self.target_ready_marker.read_text(encoding="utf-8"))
        marker.update(updates)
        self.write_json(self.target_ready_marker, marker)

    def test_complete_evidence_is_ready_and_read_only(self) -> None:
        before = self.protected_snapshot()
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.READY)
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(
            all(value["status"] == "PASS" for value in result["gates"].values())
        )
        self.assertEqual(before, self.protected_snapshot())

    def test_prepared_or_not_ready_target_marker_blocks(self) -> None:
        self.update_ready_marker(status="ASSEMBLY_PREPARED")
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertEqual(result["gates"]["production_assembly"]["status"], "FAIL")
        self.assertIn("not ASSEMBLED_PRODUCTION_TARGET", result["blockers"][0])

        self.update_ready_marker(
            status="ASSEMBLED_PRODUCTION_TARGET", ready_to_start=False
        )
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertIn(
            "not ready_to_start", result["gates"]["production_assembly"]["error"]
        )

    def test_assembly_report_status_and_hash_drift_block(self) -> None:
        self.update_assembly_report(status="ASSEMBLY_PREPARED")
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertIn(
            "not ASSEMBLED_PRODUCTION_TARGET",
            result["gates"]["production_assembly"]["error"],
        )

        self.update_assembly_report(status="ASSEMBLED_PRODUCTION_TARGET")
        self.assembly_report.write_text(
            self.assembly_report.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertIn(
            "hash does not match", result["gates"]["production_assembly"]["error"]
        )

    def test_assembly_target_report_and_transaction_bindings_block(self) -> None:
        other_target = self.root / "other-target"
        self.update_assembly_report(target_game_dir=str(other_target.resolve()))
        self.update_ready_marker(target_game_dir=str(other_target.resolve()))
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertIn(
            "different target", result["gates"]["production_assembly"]["error"]
        )

        self.update_assembly_report(target_game_dir=str(self.target.resolve()))
        self.update_ready_marker(
            target_game_dir=str(self.target.resolve()),
            external_report=str((self.evidence / "other-assembly.json").resolve()),
        )
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertIn(
            "different report", result["gates"]["production_assembly"]["error"]
        )

        self.update_ready_marker(
            external_report=str(self.assembly_report.resolve()),
            transaction_id="fedcba9876543210fedcba9876543210",
        )
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertIn(
            "transaction IDs", result["gates"]["production_assembly"]["error"]
        )

    def test_assembly_report_inside_target_is_rejected(self) -> None:
        inside = self.target / "migration-reports" / "external-assembly.json"
        inside.write_bytes(self.assembly_report.read_bytes())
        marker = json.loads(self.target_ready_marker.read_text(encoding="utf-8"))
        marker["external_report"] = str(inside.resolve())
        marker["assembly_report_sha256"] = gate.sha256(inside)
        self.write_json(self.target_ready_marker, marker)
        args = self.args()
        args.assembly_report = inside
        result = gate.evaluate_release(args)
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertIn(
            "must be outside",
            result["gates"]["production_assembly"]["error"],
        )

    def test_external_sanitizer_report_is_rejected(self) -> None:
        external = self.evidence / "resource-sanitization.json"
        external.write_bytes(self.sanitizer_report.read_bytes())
        self.update_assembly_report(sanitizer_report=str(external.resolve()))
        self.update_ready_marker(sanitizer_report=str(external.resolve()))
        args = self.args()
        args.sanitizer_report = external
        result = gate.evaluate_release(args)
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertIn(
            "target-local",
            result["gates"]["production_assembly"]["error"],
        )

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_target_junction_alias_is_rejected(self) -> None:
        alias = self.root / "target-alias"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(self.target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode != 0:
            self.skipTest(f"cannot create test junction: {created.stderr.strip()}")
        try:
            args = self.args()
            args.target_game_dir = alias
            args.target_mods_dir = alias / "mods"
            args.sanitizer_report = (
                alias
                / gate.TARGET_READY_MARKER_RELATIVE.parent
                / ("resource-sanitization.json")
            )
            result = gate.evaluate_release(args)
            self.assertEqual(result["status"], gate.NO_GO)
            self.assertIn(
                "junction",
                result["gates"]["production_assembly"]["error"],
            )
        finally:
            alias.rmdir()

    def test_missing_auth_report_is_no_go(self) -> None:
        args = self.args()
        args.auth_report = []
        result = gate.evaluate_release(args)
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertEqual(result["gates"]["auth_reports"]["status"], "FAIL")
        self.assertIn("required", result["gates"]["auth_reports"]["error"])

    def test_portal_ticket_in_current_world_blocks_stale_report(self) -> None:
        path = self.source_world / "DIM-1/data/chunks.dat"
        nbt = nbtlib.load(path, gzipped=True)
        nbt["data"]["tickets"].append(
            nbtlib.Compound(
                {
                    "type": nbtlib.String("minecraft:portal"),
                    "chunk_pos": nbtlib.IntArray([1, 2]),
                    "level": nbtlib.Int(30),
                    "ticks_left": nbtlib.Long(3),
                }
            )
        )
        nbt.save(path, gzipped=True)
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertEqual(result["gates"]["canonical_chunks"]["status"], "FAIL")
        self.assertIn("portal", result["gates"]["canonical_chunks"]["error"].lower())

    def test_pending_saveddata_blocks_even_with_other_passes(self) -> None:
        baseline = json.loads(self.baseline_path.read_text(encoding="utf-8"))
        old_marker = json.loads(self.marker_path.read_text(encoding="utf-8"))
        marker = migration.make_conversion_marker(
            self.source,
            self.staging,
            baseline,
            Path(old_marker["conversion_report"]),
            self.staging,
            pending_saveddata=["chunks"],
        )
        migration.atomic_json(self.marker_path, marker)
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertEqual(result["gates"]["conversion_marker"]["status"], "FAIL")
        self.assertIn("pending", result["gates"]["conversion_marker"]["error"])

    def test_runtime_jar_drift_blocks(self) -> None:
        self.make_jar(self.target_mods / "drift.jar")
        result = gate.evaluate_release(self.args())
        runtime_gate = result["gates"]["target_sanitizer_and_runtime_mods"]
        self.assertEqual(result["status"], gate.NO_GO)
        self.assertEqual(runtime_gate["status"], "FAIL")
        self.assertIn("JARs", runtime_gate["error"])

    def test_client_evidence_hash_drift_blocks(self) -> None:
        self.client_evidence_artifact.write_text("tampered\n", encoding="ascii")
        result = gate.evaluate_release(self.args())
        client_gate = result["gates"]["client_reports"]
        self.assertEqual(client_gate["status"], "FAIL")
        self.assertIn("evidence", client_gate["error"].lower())

    def test_auth_target_output_hash_drift_blocks(self) -> None:
        (self.target / "world/xiyus_player_data.json").write_text(
            '{"tampered":true}\n', encoding="ascii"
        )
        result = gate.evaluate_release(self.args())
        auth_gate = result["gates"]["auth_reports"]
        self.assertEqual(auth_gate["status"], "FAIL")
        self.assertIn("XiyusLogin", auth_gate["error"])

    def test_auth_scenario_artifact_hash_drift_blocks(self) -> None:
        artifact = next((self.evidence / "auth-live-evidence").glob("*.json"))
        artifact.write_text('{"tampered":true}\n', encoding="ascii")
        result = gate.evaluate_release(self.args())
        auth_gate = result["gates"]["auth_reports"]
        self.assertEqual(auth_gate["status"], "FAIL")
        self.assertIn("evidence", auth_gate["error"].lower())

    def test_legacy_archive_hash_drift_blocks(self) -> None:
        marker = json.loads(self.legacy_marker.read_text(encoding="utf-8"))
        archive = Path(marker["archives"]["world_nether"]["path"])
        archive.write_bytes(b"changed")
        result = gate.evaluate_release(self.args())
        legacy_gate = result["gates"]["legacy_policy"]
        self.assertEqual(legacy_gate["status"], "FAIL")
        self.assertIn("archive", legacy_gate["error"].lower())

    def test_legacy_source_tree_drift_blocks_stale_archive(self) -> None:
        (self.source / "world_nether/region/r.0.0.mca").write_bytes(b"changed")
        result = gate.evaluate_release(self.args())
        legacy_gate = result["gates"]["legacy_policy"]
        self.assertEqual(legacy_gate["status"], "FAIL")
        self.assertIn("stale", legacy_gate["error"].lower())

    def test_legacy_policy_must_be_explicit_non_merge(self) -> None:
        marker = json.loads(self.legacy_marker.read_text(encoding="utf-8"))
        marker["merge_into_canonical"] = True
        self.write_json(self.legacy_marker, marker)
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["gates"]["legacy_policy"]["status"], "FAIL")

    def test_conditional_report_is_not_pass(self) -> None:
        path = self.pass_reports["client"][0]
        value = json.loads(path.read_text(encoding="utf-8"))
        value["status"] = "CONDITIONAL_PASS"
        self.write_json(path, value)
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["gates"]["client_reports"]["status"], "FAIL")

    def test_generic_one_line_client_pass_is_rejected(self) -> None:
        path = self.pass_reports["client"][0]
        runtime = sanitizer.runtime_mod_manifest(self.target_mods)
        self.write_json(
            path,
            {
                "schema": 1,
                "status": "PASS",
                "category": "client",
                "target_game_dir": str(self.target.resolve()),
                "runtime_bundle_sha256": runtime["bundle_sha256"],
                "blockers": [],
                "checks": [{"name": "smoke", "status": "PASS"}],
            },
        )
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["gates"]["client_reports"]["status"], "FAIL")
        self.assertIn(
            "PRODUCTION_CLIENT_GO", result["gates"]["client_reports"]["error"]
        )

    def test_handwritten_integration_aggregate_is_rejected(self) -> None:
        path = self.pass_reports["integration"][0]
        value = json.loads(path.read_text(encoding="utf-8"))
        value.pop("_fixture_bound")
        self.write_json(path, value)
        result = gate.evaluate_release(self.args())
        integration_gate = result["gates"]["integration_reports"]
        self.assertEqual(integration_gate["status"], "FAIL")
        self.assertIn("bound report revalidation", integration_gate["error"])

    def test_incomplete_integration_matrix_is_rejected(self) -> None:
        path = self.pass_reports["integration"][0]
        value = json.loads(path.read_text(encoding="utf-8"))
        value["checks"] = [{"name": "fullstack_cold_start", "status": "PASS"}]
        self.write_json(path, value)
        result = gate.evaluate_release(self.args())
        self.assertEqual(result["gates"]["integration_reports"]["status"], "FAIL")
        self.assertIn("incomplete", result["gates"]["integration_reports"]["error"])

    def test_integration_evidence_hash_drift_is_rejected(self) -> None:
        self.integration_artifacts["villager_poi_gate"].write_text(
            '{"status":"forged"}\n', encoding="ascii"
        )
        result = gate.evaluate_release(self.args())
        integration_gate = result["gates"]["integration_reports"]
        self.assertEqual(integration_gate["status"], "FAIL")
        self.assertIn("evidence", integration_gate["error"].lower())

    def test_integration_evidence_inside_target_is_rejected(self) -> None:
        path = self.pass_reports["integration"][0]
        value = json.loads(path.read_text(encoding="utf-8"))
        check = next(
            row for row in value["checks"] if row["name"] == "mineastr_data_gate"
        )
        artifact = self.target / "server.properties"
        check["artifact"] = {
            "path": str(artifact.resolve()),
            "bytes": artifact.stat().st_size,
            "sha256": gate.sha256(artifact),
        }
        self.write_json(path, value)
        result = gate.evaluate_release(self.args())
        integration_gate = result["gates"]["integration_reports"]
        self.assertEqual(integration_gate["status"], "FAIL")
        self.assertIn("protected", integration_gate["error"].lower())

    def test_held_source_lock_is_blocked(self) -> None:
        fake = type(
            "Migration",
            (),
            {
                "probe_session_lock": mock.Mock(
                    side_effect=RuntimeError("source world session.lock is held")
                )
            },
        )
        with (
            mock.patch.object(gate, "_load_tool", return_value=fake),
            self.assertRaises(gate.GateError),
        ):
            gate.validate_source_lock(self.source_world)

    def test_cli_missing_inputs_does_not_write_inside_source(self) -> None:
        destination = self.source / "release-gate.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "final_release_gate.py"),
                "--source-game-dir",
                str(self.source),
                "--report",
                str(destination),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(destination.exists())
        self.assertEqual(json.loads(completed.stdout)["status"], gate.NO_GO)


if __name__ == "__main__":
    unittest.main()
