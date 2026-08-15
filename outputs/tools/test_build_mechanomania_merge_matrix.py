from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import build_mechanomania_merge_matrix as builder


FIXED_TIME = "2026-08-13T09:00:00+00:00"


def default_inputs(**overrides: Path | str) -> builder.Inputs:
    values: dict[str, Path | str] = {
        "merge_audit": builder.WORKSPACE
        / "outputs/mechanomania-mod-merge-audit-20260813.json",
        "pack_input": builder.WORKSPACE
        / "outputs/mechanomania-pack-audit-input-20260813.json",
        "ui_release": builder.DEFAULT_UI_RELEASE,
        "map_report": builder.DEFAULT_MAP_REPORT,
        "terrain_plan": builder.WORKSPACE
        / "outputs/vanilla-terrain-protection-plan-20260813.json",
        "terrain_empty_audit": builder.WORKSPACE
        / "outputs/vanilla-terrain-protection-empty-audit-20260813.json",
        "pack_data_root": builder.DEFAULT_PACK_DATA,
        "vanilla_client_jar": builder.DEFAULT_VANILLA_CLIENT,
        "generated_at_utc": FIXED_TIME,
    }
    values.update(overrides)
    return builder.Inputs(**values)  # type: ignore[arg-type]


class MergeMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = builder.build_report(default_inputs())

    def matrix_row(self, mod_id: str) -> dict:
        return next(row for row in self.report["matrix"] if row["mod_id"] == mod_id)

    def test_static_pass_is_not_release_pass(self) -> None:
        self.assertEqual(self.report["static_audit_status"], "PASS")
        self.assertEqual(self.report["release_decision"], "BLOCKED_FAIL_CLOSED")
        blocker_ids = {row["id"] for row in self.report["release_blockers"]}
        self.assertIn("TECTONIC_BOUNDARY_CONTINUITY_NOT_PROVEN", blocker_ids)
        self.assertIn("FULL_RUNTIME_AND_JOIN_GATES_NOT_RUN", blocker_ids)

    def test_old_world_and_server_configuration_are_immutable(self) -> None:
        invariants = self.report["invariants"]
        self.assertIn("Every already-existing server chunk", invariants["old_world_terrain"])
        self.assertIn("Do not change production server.properties", invariants["server_configuration"])
        area = invariants["protected_area"]
        self.assertEqual((area["center_x"], area["center_z"]), (10192, -1574))
        self.assertEqual(area["core_radius_blocks"], 1000)
        self.assertEqual(area["planned_vanilla_freeze_radius_blocks"], 1536)

    def test_map_stack_replaces_journeymap(self) -> None:
        journey = self.matrix_row("journeymap")
        self.assertEqual(journey["selected_source"], "EXCLUDED")
        self.assertFalse(journey["selected_server_files"])
        self.assertFalse(journey["selected_client_files"])
        self.assertTrue(any("journeymap" in name.lower() for name in journey["excluded_files"]))
        for mod_id in ("xaerominimap", "xaeroworldmap"):
            row = self.matrix_row(mod_id)
            self.assertTrue(row["selected_server_files"])
            self.assertTrue(row["selected_client_files"])
        selected = self.report["artifact_selection"]
        selected_names = {
            row["file"] for row in selected["server"] + selected["client"]
        }
        self.assertFalse(any("journeymap" in name.lower() for name in selected_names))
        self.assertEqual(selected["remove_paths"], ["overrides/config/journeymap-server.toml"])

    def test_duplicate_and_ui_choices_are_explicit(self) -> None:
        byepregen = self.matrix_row("byepregen")
        self.assertEqual(byepregen["selected_server_files"], ["byepregen-1.0.7.jar"])
        self.assertEqual(byepregen["excluded_files"], ["byepregen-1.0.0.jar"])
        c6c = self.matrix_row("c6c")
        self.assertEqual(c6c["selected_source"], "UI_SANITIZED")
        self.assertEqual(c6c["selected_server_files"], ["c6c-1.2.5.1-purified.jar"])
        self.assertEqual(
            self.report["ui_sanitization"]["selected_c6c_sha256"],
            "2666383E0E2C4C6F49494051FC2C3723D6B851DABD42D511F05712BAD2A529C4",
        )

    def test_overlap_policy_keeps_migration_baseline(self) -> None:
        self.assertEqual(self.report["counts"]["overlap_mod_ids"], 19)
        computercraft = self.matrix_row("computercraft")
        self.assertEqual(
            computercraft["selected_server_files"],
            ["cc-tweaked-1.21.1-forge-1.120.0.jar"],
        )
        self.assertEqual(
            computercraft["excluded_files"],
            ["cc-tweaked-1.21.1-forge-1.118.0.jar"],
        )
        connector = self.matrix_row("loader:connector")
        self.assertIn("beta.16", connector["selected_server_files"][0])
        self.assertIn("beta.14", connector["excluded_files"][0])

    def test_extensibility_is_not_a_hard_allowlist(self) -> None:
        extension = self.report["selection_policy"]["extension_model"]
        self.assertFalse(extension["hard_mod_allowlist"])
        self.assertFalse(extension["registry_stripping"])
        self.assertTrue(extension["future_mods_allowed"])
        self.assertTrue(extension["future_datapacks_allowed"])
        self.assertTrue(extension["mcmodsync_ota_layers_allowed"])

    def test_worldgen_difference_is_recorded(self) -> None:
        evidence = self.report["terrain_and_worldgen"]["worldgen_evidence"]
        self.assertTrue(evidence["material_generator_difference"])
        self.assertEqual(evidence["vanilla_1_21_1"]["noise"]["height"], 384)
        self.assertEqual(evidence["mechanomania"]["noise"]["height"], 544)
        self.assertGreater(
            len(evidence["mechanomania"]["tectonic_density_references"]), 0
        )
        self.assertFalse(evidence["mechanomania"]["surface_rule_equal_to_vanilla"])

    def test_scope_records_no_mutation(self) -> None:
        execution = self.report["execution"]
        self.assertFalse(execution["java_started"])
        self.assertFalse(execution["minecraft_started"])
        self.assertFalse(execution["source_modified"])
        self.assertFalse(execution["staging_modified"])
        self.assertFalse(execution["release_modified"])
        self.assertFalse(execution["artifacts_copied"])

    def test_invalid_map_source_binding_fails_closed(self) -> None:
        original = json.loads(
            (builder.WORKSPACE / "outputs/mechanomania-pack-audit-input-20260813.json")
            .read_text(encoding="utf-8-sig")
        )
        original["map_policy"]["journeymap_export_sha256"] = "00" * 32
        with tempfile.TemporaryDirectory(
            dir=builder.WORKSPACE / "outputs/tmp"
        ) as temporary:
            modified = Path(temporary) / "bad-pack-input.json"
            modified.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(builder.AuditError, "JourneyMap source hash"):
                builder.build_report(default_inputs(pack_input=modified))

    def test_manifest_only_package_and_checksums(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=builder.WORKSPACE / "outputs/tmp"
        ) as temporary:
            root = Path(temporary) / "matrix"
            package = builder.write_package(root, self.report)
            self.assertEqual(
                sorted(path.name for path in root.iterdir()),
                ["README.md", "SHA256SUMS.txt", "merge-matrix.json", "merge-matrix.md"],
            )
            loaded = json.loads((root / "merge-matrix.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded["release_decision"], "BLOCKED_FAIL_CLOSED")
            sums = (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(sums), 3)
            self.assertIn("merge-matrix.json", package["files"])

    def test_review_document_uses_unambiguous_status_language(self) -> None:
        text = builder.markdown_report(self.report)
        self.assertIn("这个 `PASS` 只代表合并矩阵自洽", text)
        self.assertIn("BLOCKED_FAIL_CLOSED", text)
        self.assertIn("不会锁死", text)
        self.assertIn("JourneyMap", text)
        self.assertIn("Xaero", text)
        self.assertIn("Tectonic", text)


if __name__ == "__main__":
    unittest.main()
