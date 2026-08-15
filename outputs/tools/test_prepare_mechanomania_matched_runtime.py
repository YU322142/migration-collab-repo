from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from outputs.tools import prepare_mechanomania_matched_runtime as subject


class RuntimeSafetyTest(unittest.TestCase):
    def arguments(self, root: Path) -> argparse.Namespace:
        return argparse.Namespace(
            release_root=subject.LOCKED_RELEASE_ROOT,
            ready_sha256=subject.LOCKED_READY_SHA256,
            build_report=subject.LOCKED_BUILD_REPORT,
            build_report_sha256=subject.LOCKED_BUILD_REPORT_SHA256,
            runtime_template=subject.ALLOWED_TEMPLATE,
            staging=subject.AUTHORITATIVE_STAGING,
            conversion_marker=subject.AUTHORITATIVE_STAGING
            / "migration-reports"
            / "conversion-complete.json",
            conversion_marker_sha256="A" * 64,
            datafix_closure=root / "closure.json",
            datafix_closure_sha256="B" * 64,
            output=root / "runtime",
            report=root / "runtime.json",
            server_port=12341,
            rcon_port=12342,
            voice_port=26341,
        )

    def test_locked_inputs_are_not_a_permanent_mod_count_cap(self) -> None:
        self.assertNotIn("235", subject.__dict__)
        self.assertFalse(hasattr(subject, "EXPECTED_MOD_COUNT"))
        self.assertEqual(subject.EXPECTED_PORTS, (12341, 12342, 26341))

    def test_rejects_non_authoritative_template_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args = self.arguments(Path(temporary))
            args.runtime_template = Path(temporary) / "lookalike"
            with mock.patch.object(subject.smoke, "prepare") as copy:
                with self.assertRaisesRegex(subject.PrepareError, "runtime template must"):
                    subject.prepare(args)
                copy.assert_not_called()

    def test_rejects_report_inside_release_before_copy(self) -> None:
        args = self.arguments(subject.ALLOWED_ROOT / "test-static-safety")
        args.report = subject.LOCKED_RELEASE_ROOT / "runtime-report.json"
        with mock.patch.object(subject, "_assert_regular_template"), mock.patch.object(
            subject.smoke, "prepare"
        ) as copy:
            with self.assertRaisesRegex(subject.PrepareError, "overlaps a protected input"):
                subject.prepare(args)
            copy.assert_not_called()

    def test_rejects_output_report_overlap_before_copy(self) -> None:
        args = self.arguments(subject.ALLOWED_ROOT / "test-static-safety")
        args.report = args.output / "report.json"
        with mock.patch.object(subject, "_assert_regular_template"), mock.patch.object(
            subject.smoke, "prepare"
        ) as copy:
            with self.assertRaisesRegex(subject.PrepareError, "output and report overlap"):
                subject.prepare(args)
            copy.assert_not_called()

    def test_rejects_wrong_locked_release_before_copy(self) -> None:
        args = self.arguments(subject.ALLOWED_ROOT / "test-static-safety")
        args.release_root = subject.ALLOWED_ROOT / "different-release"
        with mock.patch.object(subject.smoke, "prepare") as copy:
            with self.assertRaisesRegex(subject.PrepareError, "selected locked release"):
                subject.prepare(args)
            copy.assert_not_called()

    def test_heap_file_is_exactly_capped_at_four_gib(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "user_jvm_args.txt"
            subject._write_heap_cap(path)
            self.assertEqual(
                path.read_text(encoding="ascii"),
                "# Isolated migration validation heap.\n-Xms2G\n-Xmx4G\n",
            )

    def test_sanitizer_rejects_any_unapproved_jar(self) -> None:
        value = {
            "resource_sanitization": {
                "changes": [
                    {
                        "kind": "jar-resource-sanitize",
                        "path": "D:/runtime/mods/unapproved.jar",
                    }
                ],
                "runtime_mod_manifest": {
                    "file_count": 7,
                    "bytes": 1,
                    "bundle_sha256": "C" * 64,
                },
            }
        }
        with self.assertRaisesRegex(subject.PrepareError, "unexpected JARs"):
            subject._strict_sanitization(value, 7)

    def test_native_and_posix_temporary_paths_are_rewritten(self) -> None:
        temporary = Path("D:/Trans/migration-audit-work/runtime.tmp")
        output = Path("D:/Trans/migration-audit-work/runtime")
        value = {
            "native": str(temporary / "server.properties"),
            "posix": (temporary / "world" / "level.dat").as_posix(),
            "nested": [{"path": str(temporary / "mods" / "x.jar")}],
        }
        rewritten = subject._rewrite_published_paths(value, temporary, output)
        self.assertNotIn("runtime.tmp", rewritten["native"])
        self.assertNotIn("runtime.tmp", rewritten["posix"])
        self.assertNotIn("runtime.tmp", rewritten["nested"][0]["path"])

    def test_journeymap_cleanup_is_exact_and_zero_gated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_file = root / "config" / "journeymap-server.json"
            legacy_dir = root / "config" / "hydraulic" / "storage" / "journeymap"
            api_dir = root / "config" / "hydraulic" / "storage" / "journeymap-api-fabric"
            unrelated = root / "config" / "xaero" / "kept.txt"
            legacy_file.parent.mkdir(parents=True)
            legacy_file.write_text("{}", encoding="ascii")
            legacy_dir.mkdir(parents=True)
            (legacy_dir / "journeymap.mcpack").write_bytes(b"map")
            api_dir.mkdir(parents=True)
            (api_dir / "materials.json").write_text("{}", encoding="ascii")
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("keep", encoding="ascii")
            report = subject._remove_legacy_journeymap_paths(root)
            self.assertEqual(report["status"], "PASS_ZERO_MATCH")
            self.assertEqual(report["removed_files"], 3)
            self.assertEqual(report["remaining_path_matches"], 0)
            self.assertEqual(report["remaining_text_matches"], 0)
            self.assertEqual(unrelated.read_text(encoding="ascii"), "keep")

    def test_journeymap_gate_rejects_unreviewed_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unknown = root / "config" / "unknown-journeymap-cache"
            unknown.mkdir(parents=True)
            with self.assertRaisesRegex(subject.PrepareError, "unreviewed JourneyMap"):
                subject._remove_legacy_journeymap_paths(root)

    def test_journeymap_gate_rejects_unreviewed_text_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config" / "other.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"map_provider":"JourneyMap"}', encoding="utf-8")
            with self.assertRaisesRegex(subject.PrepareError, "text references"):
                subject._remove_legacy_journeymap_paths(root)


if __name__ == "__main__":
    unittest.main()
