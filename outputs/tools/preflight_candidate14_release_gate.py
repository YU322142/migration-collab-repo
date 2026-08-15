#!/usr/bin/env python3
"""Read-only preflight for the dynamic Candidate14 release runtime gate."""

from __future__ import annotations

import json
from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import candidate14_release_gate_common as release_common
import run_candidate14_release_gate as gate
import verify_deferred_item_ledger as ledger_verify


def main() -> int:
    parser = gate.build_parser()
    parser.description = "Read-only preflight for Candidate14 release gate"
    parser.add_argument("--preflight-report", type=Path, required=True)
    args = parser.parse_args()
    gate.validate_paths(args)
    release = release_common.validate_release(
        args.release_root,
        args.ready_sha256,
        args.build_report,
        args.build_report_sha256,
    )
    gate.configure_legacy_engine(args)
    ports = gate.legacy.check_ports_closed(12341, 12342, 26341)
    if not ports["all_closed"]:
        raise gate.GateError(f"private gate ports are occupied: {ports}")
    win_args = gate.legacy.validate_prerequisites(
        args.target.resolve(),
        args.client_root.resolve(),
        args.java.resolve(),
        args.powershell.resolve(),
        args.private_helper.resolve(),
        args.client_launcher.resolve(),
        args.win_args,
    )
    prepare = gate.validate_prepare_report(
        args.prepare_report.resolve(),
        args.target.resolve(),
        12341,
        12342,
        26341,
        release,
    )
    server_bundle = gate.legacy.bundle_binding(args.target.resolve() / "mods")
    client_bundle = gate.legacy.bundle_binding(args.client_root.resolve() / "mods")
    runtime = release_common.validate_runtime_bundles(
        release, server_bundle, client_bundle
    )
    client_prepare = gate.validate_client_prepare_report(
        args.client_prepare_report.resolve(),
        args.client_root.resolve(),
        client_bundle,
        release,
    )
    properties = gate.legacy.read_properties(args.target.resolve() / "server.properties")
    expected_properties = {
        "server-ip": "127.0.0.1",
        "server-port": "12341",
        "online-mode": "false",
        "enable-rcon": "true",
        "rcon.port": "12342",
        "level-name": "world",
        "require-resource-pack": "false",
    }
    for name, expected in expected_properties.items():
        if properties.get(name, "").lower() != expected:
            raise gate.GateError(f"prepared server property mismatch: {name}")
    if not properties.get("rcon.password"):
        raise gate.GateError("prepared server has no RCON password")
    local_pack = gate.legacy.validate_local_world_resource_pack(
        args.client_root.resolve(),
        expected_sha256=gate.legacy.REQUIRED_LOCAL_RESOURCE_PACK_SHA256,
        expected_bytes=gate.legacy.REQUIRED_LOCAL_RESOURCE_PACK_BYTES,
    )
    client_report = gate._read_json(
        args.client_prepare_report.resolve(), "Candidate14 client prepare report"
    )
    configured_server_address = str(
        client_report.get("server", {}).get("address", "")
    )
    if not configured_server_address or not configured_server_address.endswith(":12341"):
        raise gate.GateError("prepared client server address is missing or not bound to port 12341")
    # A fresh client preparer intentionally keeps the requested server hostname
    # (for manual testing).  The executable gate rewrites this disposable
    # client's servers.dat to loopback immediately before each private round;
    # preflight therefore validates the exact pre-rewrite payload here rather
    # than incorrectly requiring the post-rewrite value.
    gate_server_address = "127.0.0.1:12341"
    expected_servers_dat = gate.legacy.candidate13_servers_dat_payload(
        configured_server_address
    )
    if (args.client_root.resolve() / "servers.dat").read_bytes() != expected_servers_dat:
        raise gate.GateError("servers.dat does not prove acceptTextures=false")
    if (args.target.resolve() / gate.ATTEMPT_MARKER).exists():
        raise gate.GateError("fresh runtime already has a Candidate14 attempt marker")
    baseline = ledger_verify.verify(args.baseline_ledger.resolve(), [])
    if (
        baseline.get("status") != "BASELINE_LOCKED_RUNTIME_PENDING"
        or set(baseline.get("blockers", []))
        != {"runtime_round_1_after_stop", "runtime_round_2_after_stop"}
    ):
        raise gate.GateError("deferred-item source/staging baseline is not locked")
    computer = gate.legacy.computer_11_on_evidence(
        args.target.resolve() / "world", "preflight"
    )
    result = {
        "schema": 1,
        "status": "PREFLIGHT_PASS",
        "category": "candidate14_dynamic_release_gate_read_only_preflight",
        "release": release,
        "target": str(args.target.resolve()),
        "client_root": str(args.client_root.resolve()),
        "ports": ports,
        "runtime_prepare": prepare,
        "client_prepare": client_prepare,
        "runtime_bundles": runtime,
        "win_args": gate.legacy.file_artifact(win_args),
        "local_resource_pack": local_pack,
        "remote_resource_pack": {
            "configured_server_address": configured_server_address,
            "gate_server_address": gate_server_address,
            "accept_textures": False,
            "preflight_payload_address": configured_server_address,
            "gate_rewrite_pending": True,
            "exact_payload_validated": True,
        },
        "deferred_item_ledger": {
            "status": baseline["status"],
            "blockers": baseline["blockers"],
            "protected_owner_uuid": baseline.get("protected_owner_uuid"),
        },
        "computer_11": computer,
        "strict_policy": {
            "invalid_item": True,
            "scarecrow_codec_or_slot": True,
            "trial_spawner_not_a_map": True,
            "unallowlisted_server_thread_error": True,
            "client_render_error": True,
            "rounds": 2,
            "ledger_workers": args.ledger_workers,
        },
        "extension_policy": {
            "release_snapshot_exact": True,
            "permanent_mod_count_cap": False,
            "new_release_manifest_required_after_mod_changes": True,
        },
        "writes_performed_on_runtime_or_release": 0,
        "production_server_properties_modified": False,
        "java_started": False,
        "client_started": False,
    }
    if not gate._is_within(args.preflight_report.resolve(), gate.OUTPUTS):
        raise gate.GateError("preflight report must stay under workspace outputs")
    digest = gate._atomic_json(args.preflight_report.resolve(), result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": str(args.preflight_report.resolve()),
                "report_sha256": digest,
                "java_started": False,
                "permanent_mod_count_cap": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
