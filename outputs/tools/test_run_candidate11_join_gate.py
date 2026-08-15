from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("run_candidate11_join_gate.py")
SPEC = importlib.util.spec_from_file_location("candidate11_join_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class Candidate11JoinGateTest(unittest.TestCase):
    def test_identity_bundles_and_fast_teleport_defaults_are_frozen(self) -> None:
        self.assertEqual(gate.SYNTHETIC_USERNAME, "Candidate11Gate")
        self.assertEqual(
            gate.SYNTHETIC_UUID, "00000000-0000-0000-0000-000000001101"
        )
        self.assertEqual(gate.CANDIDATE11_CLIENT_BUNDLE["files"], 52)
        self.assertEqual(gate.CANDIDATE11_RUNTIME_SERVER_BUNDLE["files"], 52)
        args = gate.build_parser().parse_args(
            [
                "--target", "target",
                "--client-root", "client",
                "--prepare-report", "prepare.json",
                "--client-prepare-report", "client-prepare.json",
                "--report", "report.json",
                "--server-port", "12341",
                "--rcon-port", "12342",
            ]
        )
        self.assertEqual(args.teleport_pause_seconds, 0.25)
        self.assertEqual(args.settle_seconds, 15.0)

    def test_candidate11_release_and_runtime_audit_are_exact(self) -> None:
        value = gate.validate_candidate11_release()
        self.assertEqual(
            value["ready"]["sha256"], gate.CANDIDATE11_READY_SHA256
        )
        self.assertEqual(
            value["expected_runtime_server_bundle"],
            gate.CANDIDATE11_RUNTIME_SERVER_BUNDLE,
        )
        self.assertEqual(value["client_bundle"], gate.CANDIDATE11_CLIENT_BUNDLE)

    def test_command_plan_loads_all_four_sites_and_saves_last(self) -> None:
        commands = [row["command"] for row in gate.command_plan()]
        self.assertEqual(
            commands,
            [
                "forceload add -159 -42",
                "forceload add -165 -92",
                "forceload add 1414 -5102",
                "forceload add 27319 -12919",
                "tp Candidate11Gate -159 65 -42",
                "tp Candidate11Gate -165 65 -92",
                "tp Candidate11Gate 1414 66 -5102",
                "tp Candidate11Gate 27319 70 -12919",
                "save-all flush",
            ],
        )

    def test_cc_timeout_and_stop_deadline_are_strict_blockers(self) -> None:
        text = (
            "Terminating computer #11 due to timeout (ran over by 3 seconds)\n"
            "Enqueued command: ABORT_WITH_TIMEOUT\n"
            "[Server thread/ERROR] Failed to stop computers under deadline\n"
        )
        names = {row["marker"] for row in gate.strict_marker_hits(text)}
        self.assertIn("CC_COMPUTER_STARTUP_TIMEOUT", names)
        self.assertIn("CC_COMPUTER_STOP_DEADLINE", names)
        self.assertIn("UNALLOWLISTED_SERVER_THREAD_ERROR", names)

    def test_computer_11_on_contract_rejects_off_and_duplicates(self) -> None:
        valid = {
            "id": "computercraft:computer_normal",
            "ComputerId": 11,
            "On": 1,
            "x": 1403,
            "y": 67,
            "z": -5088,
        }
        observed, expected = gate.validate_computer_11_records([valid], "unit")
        self.assertEqual(observed, expected)
        with self.assertRaisesRegex(gate.GateError, "offline NBT mismatch"):
            gate.validate_computer_11_records([{**valid, "On": 0}], "unit")
        with self.assertRaisesRegex(gate.GateError, "exactly one"):
            gate.validate_computer_11_records([valid, dict(valid)], "unit")

    def test_immutable_e4_baseline_computer_is_on_without_writes(self) -> None:
        world = Path(
            r"D:\Trans\migration-audit-work\cutover-staging-candidate8e4-20260811\world"
        )
        evidence = gate.computer_11_on_evidence(world, "test_baseline")
        self.assertTrue(evidence["on_preserved"])
        self.assertEqual(evidence["observed"]["ComputerId"], 11)
        self.assertEqual(evidence["observed"]["On"], 1)
        self.assertEqual(evidence["slot"], 87)

    def test_world_attempt_marker_is_exclusive_and_never_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            artifact = gate.claim_fresh_gate_attempt(target)
            self.assertEqual(artifact["sha256"], gate.sha256_file(target / gate.ATTEMPT_MARKER_NAME))
            with self.assertRaisesRegex(gate.GateError, "must never be reused"):
                gate.claim_fresh_gate_attempt(target)

    def test_remote_pack_payload_is_declined(self) -> None:
        payload = gate.candidate11_servers_dat_payload("127.0.0.1:12341")
        self.assertIn(b"acceptTextures\x00", payload)
        self.assertNotIn(b"https://", payload)

    def test_exact_bundle_contract_fails_closed(self) -> None:
        actual = dict(gate.CANDIDATE11_CLIENT_BUNDLE)
        gate.require_exact_bundle(actual, gate.CANDIDATE11_CLIENT_BUNDLE, "client")
        actual["files"] = 51
        with self.assertRaisesRegex(gate.GateError, "bundle mismatch"):
            gate.require_exact_bundle(actual, gate.CANDIDATE11_CLIENT_BUNDLE, "client")

    def test_locked_pipeline_target_is_allowed_without_renaming(self) -> None:
        self.assertEqual(
            gate.PIPELINE_PREPARED_TARGET,
            Path(r"D:\Trans\migration-audit-work\manual-test-candidate8n-20260811"),
        )
        self.assertNotIn("candidate11", gate.PIPELINE_PREPARED_TARGET.name.lower())


if __name__ == "__main__":
    unittest.main()
