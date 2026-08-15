from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import assemble_production_target as assembly


class AssembleProductionTargetTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.staging = self.root / "staging"
        self.runtime = self.root / "runtime"
        self.mods = self.root / "mods"
        for path in (self.source, self.staging, self.runtime, self.mods):
            path.mkdir()
        (self.runtime / "libraries").mkdir()
        (self.runtime / "libraries" / "lib.jar").write_bytes(b"library")
        (self.runtime / "run.bat").write_text("java\n", encoding="ascii")
        (self.staging / "world").mkdir()
        (self.staging / "world" / "level.dat").write_bytes(b"world")
        (self.staging / "config").mkdir()
        (self.staging / "config" / "server.toml").write_text("x=1\n", encoding="ascii")
        (self.staging / "server.properties").write_text(
            "online-mode=false\nserver-port=25565\n", encoding="ascii"
        )
        (self.mods / "example.jar").write_bytes(b"jar")
        self.mods_manifest = self.root / "mods-manifest.json"
        row = {
            "file": "example.jar",
            "bytes": 3,
            "sha256": assembly.sha256(self.mods / "example.jar"),
        }
        self.mods_manifest.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "side": "server",
                    "file_count": 1,
                    "bundle_sha256": assembly._bundle_digest([row]),
                    "files": [row],
                }
            ),
            encoding="utf-8",
        )
        self.baseline = self.root / "baseline.json"
        self.marker = self.staging / "migration-reports" / "conversion-complete.json"
        self.marker.parent.mkdir(parents=True)
        conversion_report = self.staging / "migration-reports" / "convert.json"
        conversion_report.write_text("{}\n", encoding="ascii")
        self.baseline.write_text("{}", encoding="ascii")
        self.marker.write_text(
            json.dumps(
                {
                    "schema": assembly.FINAL_CONVERSION_MARKER_SCHEMA,
                    "status": "CONVERTED_STAGING",
                    "source_root": str(self.source.resolve()),
                    "staging_root": str(self.staging.resolve()),
                    "conversion_report": str(conversion_report.resolve()),
                    "conversion_report_sha256": assembly.sha256(conversion_report),
                    "pending_saveddata": [],
                    "outputs": {},
                }
            ),
            encoding="ascii",
        )
        self.output = self.root / "production"
        self.report = self.root / "assembly-report.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def sanitizer(_source, _staging, target, mods, hash_all=False):
        jar = Path(mods) / "example.jar"
        row = {
            "file": jar.name,
            "bytes": jar.stat().st_size,
            "sha256": assembly.sha256(jar),
            "mod_ids": [],
        }
        return {
            "schema": 1,
            "status": "SANITIZED_TARGET_COPY",
            "target_game_dir": str(target),
            "target_mods_dir": str(mods),
            "protected_tree_unchanged": True,
            "resource_sanitization": {
                "schema": 1,
                "status": "ALREADY_CLEAN",
                "changed_files": 0,
                "world": str(target / "world"),
                "server_properties": str(target / "server.properties"),
                "mods": str(mods),
                "changes": [],
                "runtime_mod_manifest": {
                    "file_count": 1,
                    "bytes": row["bytes"],
                    "bundle_sha256": assembly._bundle_digest(
                        [
                            {
                                "file": row["file"],
                                "bytes": row["bytes"],
                                "sha256": row["sha256"],
                            }
                        ]
                    ),
                    "files": [row],
                },
            },
        }

    def assemble(self, **overrides):
        values = {
            "source": self.source,
            "staging": self.staging,
            "runtime_template": self.runtime,
            "mods": self.mods,
            "mods_manifest": self.mods_manifest,
            "baseline": self.baseline,
            "conversion_marker": self.marker,
            "output": self.output,
            "report": self.report,
            "conversion_validator": lambda *_args: ({}, {}),
            "sanitizer": self.sanitizer,
        }
        values.update(overrides)
        return assembly.assemble(**values)

    def test_success_is_atomic_and_preserves_production_properties(self) -> None:
        result = self.assemble()
        self.assertEqual(result["status"], "ASSEMBLED_PRODUCTION_TARGET")
        self.assertTrue(result["ready_to_start"])
        self.assertEqual(
            (self.output / "server.properties").read_text(encoding="ascii"),
            "online-mode=false\nserver-port=25565\n",
        )
        self.assertEqual((self.output / "mods" / "example.jar").read_bytes(), b"jar")
        sanitizer = json.loads(
            (
                self.output / "migration-reports" / "resource-sanitization.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(sanitizer["target_game_dir"], str(self.output.resolve()))
        self.assertEqual(
            sanitizer["target_mods_dir"], str((self.output / "mods").resolve())
        )
        self.assertTrue(self.report.is_file())
        self.assertFalse(any(self.root.glob(".production.assembling-*")))
        ready_marker = self.output / assembly.TARGET_READY_MARKER_RELATIVE
        self.assertEqual(
            json.loads(ready_marker.read_text(encoding="utf-8"))["status"],
            "ASSEMBLED_PRODUCTION_TARGET",
        )
        self.assertTrue(
            (self.output / assembly.FINAL_CONVERSION_MARKER_RELATIVE).is_file()
        )
        self.assertTrue((self.output / assembly.RUNTIME_MANIFEST_RELATIVE).is_file())
        self.assertTrue((self.output / assembly.INPUT_MODS_MANIFEST_RELATIVE).is_file())
        self.assertEqual(json.loads(self.report.read_text(encoding="utf-8")), result)

    def test_existing_output_and_tampered_mods_fail_closed(self) -> None:
        self.output.mkdir()
        with self.assertRaisesRegex(assembly.AssemblyError, "refusing to overwrite"):
            self.assemble()
        self.output.rmdir()
        (self.mods / "example.jar").write_bytes(b"tampered")
        with self.assertRaisesRegex(assembly.AssemblyError, "differs from locked"):
            self.assemble()
        self.assertFalse(self.output.exists())

    def test_sanitizer_failure_does_not_publish_target(self) -> None:
        def fail(*_args, **_kwargs):
            raise RuntimeError("sanitizer failed")

        with self.assertRaisesRegex(RuntimeError, "sanitizer failed"):
            self.assemble(sanitizer=fail)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())
        self.assertFalse(any(self.root.glob(".production.assembling-*")))

    def test_report_commit_failure_withdraws_published_target(self) -> None:
        real_rename = assembly._rename_no_replace
        observed_status = []

        def fail_report(source, destination, label):
            if label == "assembly report publication":
                marker = self.output / assembly.TARGET_READY_MARKER_RELATIVE
                observed_status.append(
                    json.loads(marker.read_text(encoding="utf-8"))["status"]
                )
                raise OSError("report commit failed")
            return real_rename(source, destination, label)

        with (
            mock.patch.object(assembly, "_rename_no_replace", side_effect=fail_report),
            self.assertRaisesRegex(OSError, "report commit failed"),
        ):
            self.assemble()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())
        self.assertFalse(any(self.root.glob(".production.assembling-*")))
        self.assertEqual(observed_status, ["ASSEMBLY_PREPARED"])

    def test_report_appearing_at_commit_is_preserved_and_target_rolls_back(
        self,
    ) -> None:
        real_rename = assembly._rename_no_replace

        def race_report(source, destination, label):
            if label == "assembly report publication":
                Path(destination).write_text("external\n", encoding="ascii")
            return real_rename(source, destination, label)

        with (
            mock.patch.object(assembly, "_rename_no_replace", side_effect=race_report),
            self.assertRaisesRegex(assembly.AssemblyError, "already exists"),
        ):
            self.assemble()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.report.read_text(encoding="ascii"), "external\n")
        self.assertFalse(any(self.root.glob(".production.assembling-*")))

    def test_target_marker_commit_failure_rolls_back_report_and_target(self) -> None:
        real_atomic_json = assembly._atomic_json

        def fail_ready_marker(path, value):
            if (
                Path(path).name == assembly.TARGET_READY_MARKER_RELATIVE.name
                and value.get("status") == "ASSEMBLED_PRODUCTION_TARGET"
            ):
                raise OSError("ready marker commit failed")
            return real_atomic_json(path, value)

        with (
            mock.patch.object(assembly, "_atomic_json", side_effect=fail_ready_marker),
            self.assertRaisesRegex(OSError, "ready marker commit failed"),
        ):
            self.assemble()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())
        self.assertFalse(any(self.root.glob(".production.assembling-*")))

    def test_interrupt_immediately_after_target_rename_still_rolls_back(self) -> None:
        real_rename = assembly._rename_no_replace

        def interrupt_after_rename(source, destination, label):
            result = real_rename(source, destination, label)
            if label == "production target publication":
                raise KeyboardInterrupt("interrupt after target rename")
            return result

        with (
            mock.patch.object(
                assembly, "_rename_no_replace", side_effect=interrupt_after_rename
            ),
            self.assertRaisesRegex(KeyboardInterrupt, "after target rename"),
        ):
            self.assemble()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())
        self.assertFalse(any(self.root.glob(".production.assembling-*")))

    def test_interrupt_immediately_after_report_rename_still_rolls_back(self) -> None:
        real_rename = assembly._rename_no_replace

        def interrupt_after_rename(source, destination, label):
            result = real_rename(source, destination, label)
            if label == "assembly report publication":
                raise KeyboardInterrupt("interrupt after report rename")
            return result

        with (
            mock.patch.object(
                assembly, "_rename_no_replace", side_effect=interrupt_after_rename
            ),
            self.assertRaisesRegex(KeyboardInterrupt, "after report rename"),
        ):
            self.assemble()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())
        self.assertFalse(any(self.root.glob(".production.assembling-*")))

    def test_replaced_target_is_preserved_during_failed_rollback(self) -> None:
        real_atomic_json = assembly._atomic_json
        moved_target = self.root / "transaction-owned-target"

        def replace_target_then_fail(path, value):
            if (
                Path(path).name == assembly.TARGET_READY_MARKER_RELATIVE.name
                and value.get("status") == "ASSEMBLED_PRODUCTION_TARGET"
            ):
                self.output.rename(moved_target)
                self.output.mkdir()
                (self.output / "external.txt").write_text(
                    "external\n", encoding="ascii"
                )
                raise OSError("ready marker commit failed after target replacement")
            return real_atomic_json(path, value)

        with (
            mock.patch.object(
                assembly, "_atomic_json", side_effect=replace_target_then_fail
            ),
            self.assertRaisesRegex(assembly.AssemblyError, "rollback was incomplete"),
        ):
            self.assemble()
        self.assertEqual(
            (self.output / "external.txt").read_text(encoding="ascii"), "external\n"
        )
        self.assertTrue(moved_target.is_dir())
        self.assertFalse(self.report.exists())

    def test_replaced_report_is_preserved_during_failed_rollback(self) -> None:
        real_atomic_json = assembly._atomic_json
        moved_report = self.root / "transaction-owned-report.json"

        def replace_report_then_fail(path, value):
            if (
                Path(path).name == assembly.TARGET_READY_MARKER_RELATIVE.name
                and value.get("status") == "ASSEMBLED_PRODUCTION_TARGET"
            ):
                self.report.rename(moved_report)
                self.report.write_text("external\n", encoding="ascii")
                raise OSError("ready marker commit failed after report replacement")
            return real_atomic_json(path, value)

        with (
            mock.patch.object(
                assembly, "_atomic_json", side_effect=replace_report_then_fail
            ),
            self.assertRaisesRegex(assembly.AssemblyError, "rollback was incomplete"),
        ):
            self.assemble()
        self.assertEqual(self.report.read_text(encoding="ascii"), "external\n")
        self.assertTrue(moved_report.is_file())
        self.assertFalse(self.output.exists())

    def test_output_appearing_at_publish_is_not_overwritten(self) -> None:
        real_rename = assembly._rename_no_replace

        def race(source, destination, label):
            if label == "production target publication":
                Path(destination).mkdir()
                (Path(destination) / "owner.txt").write_text(
                    "external\n", encoding="ascii"
                )
            return real_rename(source, destination, label)

        with (
            mock.patch.object(assembly, "_rename_no_replace", side_effect=race),
            self.assertRaisesRegex(assembly.AssemblyError, "already exists"),
        ):
            self.assemble()
        self.assertEqual(
            (self.output / "owner.txt").read_text(encoding="ascii"), "external\n"
        )
        self.assertFalse(self.report.exists())
        self.assertFalse(any(self.root.glob(".production.assembling-*")))

    def test_preheated_or_external_conversion_marker_is_rejected(self) -> None:
        value = json.loads(self.marker.read_text(encoding="utf-8"))
        value["pending_saveddata"] = ["chunks"]
        self.marker.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(assembly.AssemblyError, "preheated"):
            self.assemble()
        self.assertFalse(self.output.exists())

        value["pending_saveddata"] = []
        external = self.root / "external-marker.json"
        external.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(
            assembly.AssemblyError, "conversion-marker must be"
        ):
            self.assemble(conversion_marker=external)

    def test_legacy_conversion_marker_schema_is_rejected_before_assembly(self) -> None:
        value = json.loads(self.marker.read_text(encoding="utf-8"))
        value["schema"] = 1
        self.marker.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(
            assembly.AssemblyError, "not a successful final marker"
        ):
            self.assemble()
        self.assertFalse(self.output.exists())

    def test_protected_path_overlap_and_existing_report_are_rejected(self) -> None:
        with self.assertRaisesRegex(assembly.AssemblyError, "overlap"):
            self.assemble(output=self.staging / "production")
        with self.assertRaisesRegex(assembly.AssemblyError, "overlap protected"):
            self.assemble(report=self.source / "assembly.json")
        self.report.write_text("operator-owned\n", encoding="ascii")
        with self.assertRaisesRegex(
            assembly.AssemblyError, "overwrite assembly report"
        ):
            self.assemble()
        self.assertEqual(self.report.read_text(encoding="ascii"), "operator-owned\n")

    def test_manifest_rejects_traversal_and_casefold_duplicates(self) -> None:
        value = json.loads(self.mods_manifest.read_text(encoding="utf-8"))
        value["files"][0]["file"] = "..\\example.jar"
        self.mods_manifest.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(assembly.AssemblyError, "unsafe"):
            assembly.validate_mod_bundle(self.mods, self.mods_manifest)

        row = {
            "file": "example.jar",
            "bytes": 3,
            "sha256": assembly.sha256(self.mods / "example.jar"),
        }
        duplicate = dict(row, file="EXAMPLE.JAR")
        value["files"] = [row, duplicate]
        value["file_count"] = 2
        value["bundle_sha256"] = assembly._bundle_digest([row, duplicate])
        self.mods_manifest.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(assembly.AssemblyError, "duplicate"):
            assembly.validate_mod_bundle(self.mods, self.mods_manifest)

    def test_posix_sanitizer_paths_are_rewritten_without_temp_leaks(self) -> None:
        def posix_paths(source, staging, target, mods, hash_all=False):
            result = self.sanitizer(source, staging, target, mods, hash_all)
            result["target_game_dir"] = target.as_posix()
            result["target_mods_dir"] = mods.as_posix()
            nested = result["resource_sanitization"]
            nested["world"] = (target / "world").as_posix()
            nested["server_properties"] = (target / "server.properties").as_posix()
            nested["mods"] = mods.as_posix()
            nested["status"] = "SANITIZED"
            nested["changed_files"] = 1
            nested["changes"] = [
                {"path": (target / "server.properties").as_posix(), "kind": "fixture"}
            ]
            return result

        self.assemble(sanitizer=posix_paths)
        value = json.loads(
            (self.output / assembly.SANITIZER_REPORT_RELATIVE).read_text(
                encoding="utf-8"
            )
        )
        serialized = json.dumps(value)
        self.assertNotIn(".assembling-", serialized)
        self.assertEqual(
            value["target_game_dir"].replace("\\", "/"), self.output.as_posix()
        )
        self.assertEqual(
            value["resource_sanitization"]["changes"][0]["path"].replace("\\", "/"),
            (self.output / "server.properties").as_posix(),
        )

    def test_sanitizer_runtime_drift_fails_before_publication(self) -> None:
        def drift(source, staging, target, mods, hash_all=False):
            result = self.sanitizer(source, staging, target, mods, hash_all)
            (mods / "example.jar").write_bytes(b"changed after manifest")
            return result

        with self.assertRaisesRegex(
            assembly.AssemblyError, "differs from post-sanitizer"
        ):
            self.assemble(sanitizer=drift)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())

    def test_source_change_during_copy_is_detected(self) -> None:
        real_copytree = assembly.shutil.copytree

        def change_source(source, destination, **kwargs):
            result = real_copytree(source, destination, **kwargs)
            if Path(source) == self.staging / "world":
                (self.staging / "world" / "level.dat").write_bytes(
                    b"changed during copy"
                )
            return result

        with (
            mock.patch.object(assembly.shutil, "copytree", side_effect=change_source),
            self.assertRaisesRegex(assembly.AssemblyError, "changed while"),
        ):
            self.assemble()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())

    def test_final_validator_marker_mutation_is_detected_before_publish(self) -> None:
        def mutate_marker(marker, *_args):
            marker.write_text(
                marker.read_text(encoding="utf-8") + " ", encoding="utf-8"
            )

        with self.assertRaisesRegex(assembly.AssemblyError, "changed during"):
            self.assemble(conversion_validator=mutate_marker)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())
        self.assertFalse(any(self.root.glob(".production.assembling-*")))

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_windows_junction_in_runtime_tree_is_rejected(self) -> None:
        junction = self.runtime / "libraries" / "escape"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(self.source)],
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode != 0:
            self.skipTest(f"cannot create test junction: {created.stderr.strip()}")
        try:
            with self.assertRaisesRegex(assembly.AssemblyError, "junction"):
                self.assemble()
        finally:
            junction.rmdir()
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_sanitizer_inserted_junction_is_unlinked_not_followed_on_rollback(
        self,
    ) -> None:
        source_sentinel = self.source / "must-survive.txt"
        source_sentinel.write_text("source\n", encoding="ascii")

        def insert_junction(source, staging, target, mods, hash_all=False):
            result = self.sanitizer(source, staging, target, mods, hash_all)
            junction = target / "escape"
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(source)],
                capture_output=True,
                text=True,
                check=False,
            )
            if created.returncode != 0:
                raise unittest.SkipTest(
                    f"cannot create test junction: {created.stderr.strip()}"
                )
            return result

        with self.assertRaisesRegex(assembly.AssemblyError, "junction"):
            self.assemble(sanitizer=insert_junction)
        self.assertEqual(source_sentinel.read_text(encoding="ascii"), "source\n")
        self.assertFalse(self.output.exists())
        self.assertFalse(any(self.root.glob(".production.assembling-*")))


if __name__ == "__main__":
    unittest.main()
