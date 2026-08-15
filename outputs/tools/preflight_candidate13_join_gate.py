#!/usr/bin/env python3
"""Read-only preflight for the locked Candidate13 two-round join gate."""

from __future__ import annotations

import json
from pathlib import Path

import run_candidate13_join_gate as gate


def main() -> int:
    args = gate.build_parser().parse_args([])
    target = args.target.resolve()
    client_root = args.client_root.resolve()
    gate.validate_paths(target, client_root, args.report.resolve())
    ports = gate.check_ports_closed(args.server_port, args.rcon_port, args.voice_port)
    if not ports["all_closed"]:
        raise gate.GateError(f"locked ports are occupied: {ports}")
    win_args = gate.validate_prerequisites(
        target,
        client_root,
        args.java.resolve(),
        args.powershell.resolve(),
        args.private_helper.resolve(),
        args.client_launcher.resolve(),
        args.win_args,
    )
    prepare = gate.validate_prepare_report(
        args.prepare_report.resolve(),
        target,
        args.server_port,
        args.rcon_port,
        args.voice_port,
    )
    release = gate.validate_candidate13_release()
    server_bundle = gate.bundle_binding(target / "mods")
    client_bundle = gate.bundle_binding(client_root / "mods")
    runtime = gate.validate_candidate13_runtime_bundles(
        target, client_root, server_bundle, client_bundle
    )
    client_prepare = gate.validate_client_prepare_report(
        args.client_prepare_report.resolve(), client_root, client_bundle
    )
    properties = gate.read_properties(target / "server.properties")
    # This preflight is read-only, so accept the prepared target's original
    # whitelist values here; the runtime runner changes only the disposable
    # copy immediately before launch.
    for key, expected in {
        "server-ip": "127.0.0.1",
        "server-port": "12341",
        "enable-rcon": "true",
        "rcon.port": "12342",
        "online-mode": "false",
        "level-name": "world",
        "require-resource-pack": "false",
    }.items():
        if properties.get(key, "").lower() != expected.lower():
            raise gate.GateError(f"preflight server property mismatch: {key}")
    if not properties.get("rcon.password"):
        raise gate.GateError("preflight rcon.password is missing")
    local_pack = gate.validate_local_world_resource_pack(
        client_root,
        expected_sha256=gate.REQUIRED_LOCAL_RESOURCE_PACK_SHA256,
        expected_bytes=gate.REQUIRED_LOCAL_RESOURCE_PACK_BYTES,
    )
    expected_servers_dat = gate.candidate13_servers_dat_payload("127.0.0.1:12341")
    actual_servers_dat = (client_root / "servers.dat").read_bytes()
    if actual_servers_dat != expected_servers_dat:
        raise gate.GateError("preflight servers.dat does not prove acceptTextures=false")
    if (target / gate.ATTEMPT_MARKER_NAME).exists():
        raise gate.GateError("fresh runtime already has a Candidate13 gate-attempt marker")
    computer = gate.computer_11_on_evidence(target / "world", "preflight")
    result = {
        "schema": 1,
        "status": "PREFLIGHT_PASS",
        "category": "candidate13_join_gate_read_only_preflight",
        "target": str(target),
        "client_root": str(client_root),
        "ports": ports,
        "release": release,
        "prepare_report": prepare,
        "client_prepare_report": client_prepare,
        "runtime_bundles": runtime,
        "win_args": gate.file_artifact(win_args),
        "local_resource_pack": local_pack,
        "remote_resource_pack": {
            "accept_textures": False,
            "servers_dat": gate.file_artifact(client_root / "servers.dat"),
            "exact_payload_validated": True,
        },
        "computer_11": computer,
        "waypoint_op": {
            "username": gate.SYNTHETIC_USERNAME,
            "uuid": gate.SYNTHETIC_UUID,
            "permission_level": gate.SYNTHETIC_PERMISSION_LEVEL,
            "commands": [row["command"] for row in gate.command_plan()],
            "expected_persisted_colors": [65280, 16711850],
        },
        "strict_policy": {
            "unallowlisted_server_thread_error": True,
            "render_thread_error": True,
            "rounds": 2,
            "bootstrap_timeout_seconds": args.bootstrap_timeout_seconds,
            "dedicated_startup_timeout_seconds": args.startup_timeout_seconds,
            "join_timeout_seconds": args.join_timeout_seconds,
            "teleport_pause_seconds": args.teleport_pause_seconds,
            "settle_seconds": args.settle_seconds,
        },
        "writes_performed": 0,
        "java_started": False,
    }
    report = gate.OUTPUTS / "candidate13-join-gate-preflight-r2-20260812.json"
    digest = gate.atomic_json(report, result)
    print(json.dumps({"status": result["status"], "report": str(report), "report_sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
