from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parent


def load(name: str):
    path = TOOLS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = load("candidate14_release_gate_common")
gate = load("run_candidate14_release_gate")
prepare_client = load("prepare_candidate14_release_client_root")
prepare_runtime = load("prepare_candidate14_release_runtime")


class Candidate14ReleaseGateTest(unittest.TestCase):
    def test_parser_requires_explicit_release_identity(self) -> None:
        required = [
            "--release-root", "release",
            "--ready-sha256", "A" * 64,
            "--build-report", "build.json",
            "--build-report-sha256", "B" * 64,
            "--target", "runtime",
            "--client-root", "client",
            "--prepare-report", "prepare.json",
            "--client-prepare-report", "client-prepare.json",
            "--report", "gate.json",
        ]
        args = gate.build_parser().parse_args(required)
        self.assertEqual((args.server_port, args.rcon_port, args.voice_port), (12341, 12342, 26341))
        self.assertEqual(args.ledger_workers, 20)
        self.assertIsNone(args.artifact_root)

    def test_parser_accepts_d_drive_artifact_root(self) -> None:
        required = [
            "--release-root", "release", "--ready-sha256", "A" * 64,
            "--build-report", "build.json", "--build-report-sha256", "B" * 64,
            "--target", "runtime", "--client-root", "client",
            "--prepare-report", "prepare.json", "--client-prepare-report", "client.json",
            "--report", "gate.json",
            "--artifact-root", r"D:\Trans\migration-audit-work\candidate14-attempt3-artifacts",
        ]
        args = gate.build_parser().parse_args(required)
        self.assertEqual(
            args.artifact_root,
            Path(r"D:\Trans\migration-audit-work\candidate14-attempt3-artifacts"),
        )

    def test_release_digest_is_cardinality_agnostic(self) -> None:
        rows = [
            {"file": "a.jar", "sha256": "A" * 64},
            {"file": "b.jar", "sha256": "B" * 64},
            {"file": "future-addon.jar", "sha256": "C" * 64},
        ]
        self.assertEqual(len(common.bundle_digest(rows)), 64)
        self.assertNotIn("54", common.bundle_digest(rows))

    def test_runtime_bundle_exactness_is_release_scoped_not_a_permanent_cap(self) -> None:
        binding = {
            "runtime_server_identity": {
                "files": 91,
                "bytes": 1234,
                "bundle_sha256": "A" * 64,
                "sanitized_jars": list(common.SANITIZER_JARS),
            },
            "client_manifest": {
                "files": 92,
                "bytes": 5678,
                "bundle_sha256": "B" * 64,
            },
        }
        result = common.validate_runtime_bundles(
            binding,
            {"files": 91, "bytes": 1234, "bundle_sha256": "A" * 64},
            {"files": 92, "bytes": 5678, "bundle_sha256": "B" * 64},
        )
        self.assertTrue(result["release_scoped_exact_bundles"])
        self.assertTrue(result["current_file_counts_are_not_production_caps"])

    def test_strict_patterns_cover_new_candidate14_failures(self) -> None:
        args = gate.build_parser().parse_args(
            [
                "--release-root", "release", "--ready-sha256", "A" * 64,
                "--build-report", "build.json", "--build-report-sha256", "B" * 64,
                "--target", "runtime", "--client-root", "client",
                "--prepare-report", "prepare.json", "--client-prepare-report", "client.json",
                "--report", "gate.json",
            ]
        )
        gate.configure_legacy_engine(args)
        server = "\n".join(
            (
                "[Server thread/ERROR] [minecraft/TrialSpawnerBlockEntity]: Not a map: \"minecraft:trial_chamber/melee/husk/normal\"",
                "Caused by: java.lang.RuntimeException: Slot 1 not in valid range - [0,1)",
                "[Server thread/ERROR] Tried to load invalid item: minecraft:netherite_horse_armor",
            )
        )
        names = {row["marker"] for row in gate.legacy.strict_marker_hits(server)}
        self.assertIn("TRIAL_SPAWNER_NOT_A_MAP", names)
        self.assertIn("SCARECROW_SLOT_RANGE_FAILURE", names)
        self.assertIn("INVALID_ITEM_LOAD", names)
        client = gate.legacy.strict_marker_hits(
            "[Render thread/ERROR] broken texture", client=True
        )
        self.assertIn("CLIENT_RENDER_ERROR", {row["marker"] for row in client})

    def test_attempt_marker_records_no_permanent_count_cap(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw)
            artifact = gate.claim_attempt(
                path,
                {"ready": {"sha256": "C" * 64}},
            )
            value = json.loads(Path(artifact["path"]).read_text(encoding="utf-8"))
            self.assertEqual(value["candidate"], 14)
            self.assertFalse(value["permanent_mod_count_cap"])
            with self.assertRaises(gate.GateError):
                gate.claim_attempt(path, {"ready": {"sha256": "C" * 64}})

    def test_checkpoint_failure_is_fail_closed(self) -> None:
        original = gate.checkpoint_audit.audit
        gate.checkpoint_audit.audit = lambda *args, **kwargs: {
            "status": "BLOCKED_PARSE_ERRORS",
            "totals": {"matches": 0, "errors": 1},
        }
        try:
            with tempfile.TemporaryDirectory() as raw:
                with self.assertRaises(gate.GateError):
                    gate.run_checkpoint(Path(raw), "runtime_round_1_after_stop", 20, Path(raw))
        finally:
            gate.checkpoint_audit.audit = original

    def test_client_preparer_rejects_non_12341_address(self) -> None:
        args = prepare_client.build_parser().parse_args(
            [
                "--release-root", "release",
                "--ready-sha256", "A" * 64,
                "--build-report", "build.json",
                "--build-report-sha256", "B" * 64,
                "--source-minecraft-root", str(prepare_client.OUTPUTS / "template"),
                "--output-root", str(prepare_client.OUTPUTS / "client"),
                "--report", str(prepare_client.OUTPUTS / "client.json"),
                "--local-resource-pack", str(prepare_client.OUTPUTS / "pack.zip"),
                "--server-address", "mc.example.invalid:25565",
                "--preflight-only",
            ]
        )
        with self.assertRaisesRegex(prepare_client.PrepareError, "12341"):
            prepare_client.validate_args(args)

    def test_client_preparer_accepts_isolated_d_drive_output(self) -> None:
        args = prepare_client.build_parser().parse_args(
            [
                "--release-root", "release",
                "--ready-sha256", "A" * 64,
                "--build-report", "build.json",
                "--build-report-sha256", "B" * 64,
                "--source-minecraft-root", str(prepare_client.OUTPUTS / "template"),
                "--output-root", r"D:\Trans\migration-audit-work\client-gate-candidate14-r3-attempt2\.minecraft",
                "--report", str(prepare_client.OUTPUTS / "client.json"),
                "--local-resource-pack", str(prepare_client.OUTPUTS / "pack.zip"),
                "--server-address", "mc.example.invalid:12341",
                "--preflight-only",
            ]
        )
        source, output, _, _ = prepare_client.validate_args(args)
        self.assertTrue(str(output).startswith(r"D:\Trans\migration-audit-work"))
        self.assertTrue(str(source).endswith(r"outputs\template"))

    def test_runtime_preparer_overlap_helper_is_fail_closed(self) -> None:
        root = Path(r"D:\Trans\migration-audit-work")
        staging = root / "staging"
        self.assertTrue(prepare_runtime.overlaps(staging / "child", staging))
        self.assertTrue(prepare_runtime.overlaps(staging, staging / "child"))
        self.assertFalse(prepare_runtime.overlaps(root / "runtime", staging))

    def test_servers_dat_explicitly_rejects_remote_pack(self) -> None:
        payload = prepare_client.servers_dat_payload("mc.example.invalid:12341")
        self.assertIn(b"acceptTextures\x00", payload)
        self.assertNotIn(b"https://", payload)

    def test_private_gate_servers_dat_is_loopback(self) -> None:
        payload = gate.legacy.candidate13_servers_dat_payload("127.0.0.1:12341")
        self.assertIn(b"127.0.0.1:12341", payload)
        self.assertIn(b"acceptTextures\x00", payload)

    def test_private_desktop_helper_accepts_d_drive_migration_root(self) -> None:
        helper = TOOLS / "run_private_desktop_client_session.ps1"
        text = helper.read_text(encoding="utf-8")
        self.assertIn(r"D:\Trans\migration-audit-work", text)
        self.assertIn("MinecraftRoot itself may not be a junction/reparse point", text)
        self.assertIn("MinecraftRoot mutable directory may not be linked", text)

    def test_recipe_book_accepts_only_reviewed_exact_multiset(self) -> None:
        allow = gate._recipe_book_allowlist()
        sample = "\n".join(
            "[21:33:21] [Server thread/ERROR] [minecraft/ServerRecipeBook]: "
            "Tried to load unrecognized recipe: " + recipe + " removed now."
            for recipe in allow["recipe_ids"][:2]
        )
        result = gate.recipe_book_audit(sample, allow)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["accepted_count"], 2)
        self.assertEqual(result["malformed_or_unreviewed_count"], 0)

    def test_recipe_book_drift_fails_closed(self) -> None:
        allow = gate._recipe_book_allowlist()
        sample = (
            "[21:33:21] [Server thread/ERROR] [minecraft/ServerRecipeBook]: "
            "Tried to load unrecognized recipe: minecraft:future_removed removed now."
        )
        result = gate.recipe_book_audit(sample, allow)
        self.assertEqual(result["status"], "NO_GO")
        self.assertEqual(result["malformed_or_unreviewed_count"], 1)

    def test_recipe_book_other_error_is_not_accepted(self) -> None:
        allow = gate._recipe_book_allowlist()
        sample = "[21:33:21] [Server thread/ERROR] [minecraft/ServerRecipeBook]: codec exploded"
        result = gate.recipe_book_audit(sample, allow)
        self.assertEqual(result["status"], "NO_GO")
        self.assertEqual(result["malformed_or_unreviewed_count"], 1)

    def test_recipe_book_round_contract_requires_exact_first_and_zero_second(self) -> None:
        allow = gate._recipe_book_allowlist()
        first = "\n".join(
            "[21:33:21] [Server thread/ERROR] [minecraft/ServerRecipeBook]: "
            f"Tried to load unrecognized recipe: {recipe} removed now."
            for recipe, count in allow["expected_fresh_runtime_first_round_counts"].items()
            for _ in range(count)
        )
        with tempfile.TemporaryDirectory() as raw:
            latest = Path(raw) / "latest.log"
            latest.write_text(first + "\n", encoding="utf-8")
            round_one = gate.validate_round_recipe_book(1, latest, allow)
            self.assertEqual(round_one["accepted_count"], 62)
            latest.write_text("[Server thread/INFO] Done\n", encoding="utf-8")
            round_two = gate.validate_round_recipe_book(2, latest, allow)
            self.assertEqual(round_two["accepted_count"], 0)

    def test_recipe_book_round_contract_rejects_second_round_recurrence(self) -> None:
        allow = gate._recipe_book_allowlist()
        recipe = allow["recipe_ids"][0]
        with tempfile.TemporaryDirectory() as raw:
            latest = Path(raw) / "latest.log"
            latest.write_text(
                "[21:34:21] [Server thread/ERROR] [minecraft/ServerRecipeBook]: "
                f"Tried to load unrecognized recipe: {recipe} removed now.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(gate.GateError, "round 2.*multiset mismatch"):
                gate.validate_round_recipe_book(2, latest, allow)


if __name__ == "__main__":
    unittest.main()
