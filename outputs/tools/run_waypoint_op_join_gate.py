#!/usr/bin/env python3
"""High-permission join gate for the Waypoint Fire command-tree fix.

The original Candidate11 gate used a non-operator account, so its client never
received the permission-level-2 ``/waypoint`` branch.  This gate deliberately
uses the existing level-4 offline OP identity, joins the disposable converted
server, and executes the hex-color command through that player context.  It
does not edit ``server.properties``; the target and client are already isolated
runtime copies.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "outputs" / "tools"
OUTPUTS = ROOT / "outputs"
TARGET = Path(r"D:\Trans\migration-audit-work\manual-test-candidate8n-20260811")
CLIENT_ROOT = ROOT / "outputs" / "tmp" / "client-gate-candidate11" / ".minecraft"
SERVER_PORT = 12341
RCON_PORT = 12342
VOICE_PORT = 26341
JAVA = Path(r"C:\Program Files\Java\jdk-21.0.10\bin\java.exe")
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
PRIVATE_HELPER = TOOLS / "run_private_desktop_client_session.ps1"
CLIENT_LAUNCHER = TOOLS / "launch_neoforge_client_isolated.ps1"
OP_USERNAME = "SyntheticOperator"
OP_UUID = "00000000-0000-4000-8000-000000000001"
NEW_JAR_SHA256 = "86A85C0447315AC17D373E3708425CEB8450D9D0CB1FD9C7ABDC82CE8D8E5B92"
FAILURE_RE = re.compile(
    r"Unrecognized argument type|Invalid player data|Couldn't place player in world|"
    r"lost connection: (?!Disconnected|Server closed)",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def atomic_json(path: Path, value: object) -> str:
    import hashlib

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{__import__('os').getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    # Import the existing, audited private-desktop harness rather than creating
    # a second launcher implementation.  Its constants are overridden only for
    # this gate's explicitly OP identity.
    sys.path.insert(0, str(TOOLS))
    import run_candidate11_join_gate as base

    base.SYNTHETIC_USERNAME = OP_USERNAME
    base.SYNTHETIC_UUID = OP_UUID

    report_path = OUTPUTS / "waypoint-op-join-gate-20260811.json"
    artifact_dir = OUTPUTS / (
        "waypoint-op-join-gate-artifacts-"
        + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    artifact_dir.mkdir(parents=True, exist_ok=False)
    report: dict[str, object] = {
        "schema": 1,
        "status": "NO_GO",
        "category": "waypoint_fire_level4_op_join_gate",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target": str(TARGET),
        "client_root": str(CLIENT_ROOT),
        "identity": {"username": OP_USERNAME, "uuid": OP_UUID, "permission_level": 4},
        "ports": {"server": SERVER_PORT, "rcon": RCON_PORT, "voice": VOICE_PORT},
        "jar": {"expected_sha256": NEW_JAR_SHA256},
        "commands": [],
        "blockers": [],
        "artifacts": {"directory": str(artifact_dir)},
    }

    server = None
    client = None
    try:
        if not TARGET.is_dir() or not CLIENT_ROOT.is_dir():
            raise RuntimeError("isolated target/client root is missing")
        server_jars = sorted(TARGET.joinpath("mods").glob("waypoint-fire-equivalence-*.jar"))
        client_jars = sorted(CLIENT_ROOT.joinpath("mods").glob("waypoint-fire-equivalence-*.jar"))
        if len(server_jars) != 1 or len(client_jars) != 1:
            raise RuntimeError(f"expected one Waypoint JAR per side, got {server_jars} / {client_jars}")
        server_hash = sha256(server_jars[0])
        client_hash = sha256(client_jars[0])
        report["jar"] = {
            "server": {"path": str(server_jars[0]), "sha256": server_hash},
            "client": {"path": str(client_jars[0]), "sha256": client_hash},
            "expected_sha256": NEW_JAR_SHA256,
            "same": server_hash == client_hash == NEW_JAR_SHA256,
        }
        if server_hash != client_hash or server_hash != NEW_JAR_SHA256:
            raise RuntimeError("server/client Waypoint JAR hash is not the fixed build")

        # Use a fresh artifact directory but the already disposable converted
        # world.  No server.properties mutation is performed by this script.
        server = base.ServerSession(
            TARGET,
            artifact_dir,
            1,
            JAVA,
            "@libraries/net/neoforged/neoforge/21.1.241/win_args.txt",
            RCON_PORT,
            "migration-final-smoke",
            4096,
        )
        # This converted world has pre-existing recipe-book ERROR lines that
        # are unrelated to the command-tree regression.  Keep the gate strict
        # for the actual join failure while deliberately not inheriting the
        # broad Candidate11 marker policy here.
        def server_health() -> None:
            if server.process.poll() is not None:
                raise RuntimeError(f"server exited early with {server.process.returncode}")
            current = server.current_log()
            if FAILURE_RE.search(current):
                raise RuntimeError("server emitted command-tree/player-data failure")

        server.assert_alive = server_health
        server.wait_ready(300)
        ready_log = server.current_log()
        baseline_join = base.joined_count(ready_log, OP_USERNAME)
        baseline_lost = base.lost_count(ready_log, OP_USERNAME)
        client = base.PrivateClientSession(
            CLIENT_ROOT,
            artifact_dir,
            1,
            SERVER_PORT,
            POWERSHELL,
            PRIVATE_HELPER,
            CLIENT_LAUNCHER,
            JAVA,
            2048,
            180,
            300,
        )

        def health() -> None:
            server.assert_alive()
            client.assert_running()

        base.wait_until(
            lambda: base.joined_count(server.current_log(), OP_USERNAME) == baseline_join + 1,
            180,
            "level-4 OP join",
            health=health,
        )
        time.sleep(3)
        joined_log = server.current_log()
        if base.lost_count(joined_log, OP_USERNAME) != baseline_lost:
            raise RuntimeError("OP disconnected before command test")
        if FAILURE_RE.search(joined_log):
            raise RuntimeError("join log contains command-tree/player-data failure")

        commands = [
            'summon minecraft:armor_stand 0 80 0 {Tags:["waypoint_op_fixture"],NoGravity:1b,Invisible:1b}',
            'attribute @e[tag=waypoint_op_fixture,limit=1] minecraft:waypoint_transmit_range base set 64',
            f'execute as {OP_USERNAME} run waypoint modify @e[tag=waypoint_op_fixture,limit=1] color hex 0F0',
            'data get entity @e[tag=waypoint_op_fixture,limit=1] locator_bar_icon',
            f'execute as {OP_USERNAME} run waypoint modify @e[tag=waypoint_op_fixture,limit=1] color hex FF00AA',
            'data get entity @e[tag=waypoint_op_fixture,limit=1] locator_bar_icon',
            'kill @e[tag=waypoint_op_fixture]',
            'save-all flush',
        ]
        responses: list[dict[str, object]] = []
        for command in commands:
            response = server.command(command)
            responses.append({"command": command, "response": response})
            if "Unknown or incomplete command" in response or "Incorrect argument" in response:
                raise RuntimeError(f"command failed: {command}: {response}")
        report["commands"] = responses
        if not any("65280" in str(item["response"]) for item in responses if "locator_bar_icon" in str(item["command"])):
            raise RuntimeError("three-digit hex command did not persist color 65280")
        if not any("16711850" in str(item["response"]) for item in responses if "locator_bar_icon" in str(item["command"])):
            raise RuntimeError("six-digit hex command did not persist color 16711850")

        client.assert_running()
        pre_controlled_stop_log = server.current_log()
        lost_before_controlled_stop = (
            base.lost_count(pre_controlled_stop_log, OP_USERNAME) - baseline_lost
        )
        if lost_before_controlled_stop != 0:
            raise RuntimeError("OP disconnected before the controlled client stop")
        if FAILURE_RE.search(pre_controlled_stop_log):
            raise RuntimeError("server emitted a command-tree/player-data failure during OP command test")
        client_state = client.stop()
        stop_response = server.stop()
        final_log = read_text(TARGET / "logs" / "latest.log")
        if FAILURE_RE.search(final_log):
            raise RuntimeError("final server log contains command-tree/player-data failure")
        report["join"] = {
            "new_join_lines": base.joined_count(final_log, OP_USERNAME) - baseline_join,
            "lost_before_controlled_stop": lost_before_controlled_stop,
            "lost_after_controlled_stop": (
                base.lost_count(final_log, OP_USERNAME)
                - base.lost_count(pre_controlled_stop_log, OP_USERNAME)
            ),
        }
        report["client_state"] = {
            "status": client_state.get("status"),
            "exit_code": client_state.get("exit_code"),
            "processes_closed": client_state.get("processes_closed"),
        }
        report["server_stop_response"] = stop_response
        report["status"] = "PASS"
    except Exception as exc:
        report["blockers"] = [{"type": type(exc).__name__, "message": str(exc)}]
    finally:
        if client is not None:
            client.abort()
        if server is not None:
            server.abort()
        report["cleanup"] = {
            "ports_closed": all(
                base.tcp_closed(port) for port in (SERVER_PORT, RCON_PORT)
            ) and base.udp_free(VOICE_PORT),
        }
        report["generated_at_utc_completed"] = dt.datetime.now(dt.timezone.utc).isoformat()
        report_digest = atomic_json(report_path, report)
        report_path.with_suffix(report_path.suffix + ".sha256").write_text(
            f"{report_digest}  {report_path.name}\n",
            encoding="ascii",
        )
    print(json.dumps({"status": report["status"], "report": str(report_path), "report_sha256": report_digest}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
