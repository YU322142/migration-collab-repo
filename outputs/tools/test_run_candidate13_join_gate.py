from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("run_candidate13_join_gate.py")
SPEC = importlib.util.spec_from_file_location("candidate13_join_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class Candidate13JoinGateTest(unittest.TestCase):
    def test_locked_candidate13_contract_and_delays(self) -> None:
        args = gate.build_parser().parse_args([])
        self.assertEqual(args.target, gate.PIPELINE_PREPARED_TARGET)
        self.assertEqual(args.client_root, gate.CANDIDATE13_CLIENT_ROOT)
        self.assertEqual(args.server_port, 12341)
        self.assertEqual(args.rcon_port, 12342)
        self.assertEqual(args.voice_port, 26341)
        self.assertEqual(args.teleport_pause_seconds, 10.0)
        self.assertEqual(args.settle_seconds, 15.0)
        self.assertEqual(args.bootstrap_timeout_seconds, 120)
        self.assertEqual(args.startup_timeout_seconds, 20)
        self.assertEqual(gate.SYNTHETIC_PERMISSION_LEVEL, 4)

    def test_release_lock_and_bundle_contract_are_exact(self) -> None:
        value = gate.validate_candidate13_release()
        self.assertEqual(value["ready"]["sha256"], gate.CANDIDATE13_READY_SHA256)
        self.assertEqual(value["expected_runtime_server_bundle"], gate.CANDIDATE13_RUNTIME_SERVER_BUNDLE)
        self.assertEqual(value["client_bundle"], gate.CANDIDATE13_CLIENT_BUNDLE)

    def test_remote_resource_pack_is_explicitly_declined(self) -> None:
        payload = gate.candidate13_servers_dat_payload("127.0.0.1:12341")
        self.assertIn(b"acceptTextures\x00", payload)
        self.assertNotIn(b"https://", payload)

    def test_local_derived_resource_pack_is_frozen(self) -> None:
        self.assertEqual(gate.REQUIRED_LOCAL_RESOURCE_PACK_BYTES, 110377999)
        self.assertEqual(
            gate.REQUIRED_LOCAL_RESOURCE_PACK_SHA256,
            "614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364",
        )
        evidence = gate.resource_pack_zip_evidence(
            gate.REQUIRED_LOCAL_RESOURCE_PACK_SOURCE,
            gate.REQUIRED_LOCAL_RESOURCE_PACK_ZIP_ENTRIES,
        )
        self.assertEqual(evidence["pack_format"], 34)

    def test_command_plan_keeps_risk_sites_and_level4_waypoint_hex(self) -> None:
        rows = gate.command_plan()
        commands = [row["command"] for row in rows]
        teleports = [row for row in rows if row["kind"] == "teleport"]
        hex_rows = [row for row in rows if row["kind"] == "waypoint_hex"]
        probes = [row for row in rows if row["kind"] == "waypoint_color_probe"]
        self.assertEqual(len(teleports), 4)
        self.assertEqual([row["hex"] for row in hex_rows], ["0F0", "FF00AA"])
        self.assertEqual([row["expected_color"] for row in probes], [65280, 16711850])
        self.assertEqual(commands[-1], "save-all flush")

    def test_waypoint_evidence_requires_both_persisted_colors(self) -> None:
        rows = []
        for row in gate.command_plan():
            response = "ok"
            if row.get("expected_color") == 65280:
                response = "locator_bar_icon: {color: 65280}"
            elif row.get("expected_color") == 16711850:
                response = "locator_bar_icon: {color: 16711850}"
            rows.append({**row, "response": response})
        value = gate.validate_waypoint_command_evidence(rows)
        self.assertTrue(value["validated"])
        probe_index = next(
            index
            for index, row in enumerate(rows)
            if row.get("kind") == "waypoint_color_probe"
        )
        rows[probe_index]["response"] = "missing"
        with self.assertRaisesRegex(gate.GateError, "not persisted"):
            gate.validate_waypoint_command_evidence(rows)

    def test_strict_server_and_render_errors_are_blockers(self) -> None:
        server = gate.strict_marker_hits("[Server thread/ERROR] boom")
        client = gate.strict_marker_hits("[Render thread/ERROR] broken texture", client=True)
        self.assertIn("UNALLOWLISTED_SERVER_THREAD_ERROR", {row["marker"] for row in server})
        self.assertIn("CLIENT_RENDER_ERROR", {row["marker"] for row in client})

    def test_runtime_guard_hashes_are_locked(self) -> None:
        self.assertEqual(gate.WAYPOINT_SHA256, "86A85C0447315AC17D373E3708425CEB8450D9D0CB1FD9C7ABDC82CE8D8E5B92")
        self.assertEqual(gate.CC_GUARD_SHA256, "6744626E2B43643E9F28C9159FABD7A6A53CDCDEB83AE8252C266F7E987F84F7")
        self.assertEqual(gate.CREATE_GUARD_SHA256, "AC51AEFDDA8437D777B5C8B3E285E9036676D854F7958C6B882807C15BE0910A")
        self.assertEqual(gate.RESOURCE_OVERLAY_SHA256, "BCCB7D7CF8019D8895A081D563E578712D7CDF93DA0AD9EAFB31067439C62862")

    def test_attempt_marker_is_candidate13_and_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            gate.claim_fresh_gate_attempt(target)
            value = gate.read_json_object(target / gate.ATTEMPT_MARKER_NAME, "marker")
            self.assertEqual(value["candidate"], 13)
            with self.assertRaisesRegex(gate.GateError, "must never be reused"):
                gate.claim_fresh_gate_attempt(target)


if __name__ == "__main__":
    unittest.main()
