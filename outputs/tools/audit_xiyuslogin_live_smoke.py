#!/usr/bin/env python3
"""Audit the redacted synthetic XiyusLogin network smoke.

This tool does not start clients or servers and never reads account secrets. It
binds an already completed isolated smoke to the exact candidate JAR and the
current staged EasyAuth/XiyusLogin hashes. Synthetic Java scenarios can pass,
but missing Floodgate or proxy runtimes keep the aggregate report blocked.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import socket
from typing import Any


HERE = Path(__file__).resolve().parent
AUTH_GATE_PATH = HERE / "verify_auth_readiness.py"
SPEC = importlib.util.spec_from_file_location("auth_gate_for_live_smoke", AUTH_GATE_PATH)
auth_gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(auth_gate)

REJECTED_MIGRATION2_SHA256 = (
    "B1ED37CFDFCA17D0DD122AE9AD80F508BA84B6A1777DEDBE39A649B9F92B32D9"
)
PASSWORD_HASH_RE = re.compile(r"^\$2[aby]\$12\$")
SYNTHETIC_PASS = "PASS_SYNTHETIC_NETWORK_RUNTIME"


class AuditError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise AuditError(f"{label}_MISSING_OR_SYMLINK")
    return path.resolve()


def read_log(path: Path, label: str) -> tuple[Path, str]:
    resolved = regular_file(path, label)
    return resolved, resolved.read_text(encoding="utf-8", errors="replace")


def require_count(text: str, marker: str, expected: int, code: str) -> int:
    count = text.count(marker)
    if count != expected:
        raise AuditError(f"{code}:expected={expected}:actual={count}")
    return count


def require_at_least(text: str, marker: str, minimum: int, code: str) -> int:
    count = text.count(marker)
    if count < minimum:
        raise AuditError(f"{code}:minimum={minimum}:actual={count}")
    return count


def assert_no_fatal_auth_error(text: str, label: str) -> None:
    forbidden = (
        "NoClassDefFoundError",
        "ClassNotFoundException: at.favre.lib",
        "CANDIDATE_JAR_RUNTIME",
        "[Server thread/FATAL]",
        "[Render thread/FATAL]",
    )
    for marker in forbidden:
        if marker in text:
            raise AuditError(f"{label}_FATAL_MARKER:{marker}")


def audit_mod_dir(path: Path, candidate_hash: str, label: str) -> dict[str, Any]:
    resolved = path.resolve()
    if resolved.is_symlink() or not resolved.is_dir():
        raise AuditError(f"{label}_MOD_DIR_INVALID")
    jars = sorted(item for item in resolved.iterdir() if item.is_file() and item.suffix.lower() == ".jar")
    if len(jars) != 1:
        raise AuditError(f"{label}_MOD_COUNT:{len(jars)}")
    jar = jars[0]
    if "mineastr" in jar.name.lower():
        raise AuditError(f"{label}_MINEASTR_PRESENT")
    if sha256(jar) != candidate_hash:
        raise AuditError(f"{label}_CANDIDATE_HASH_MISMATCH")
    return {"jar_count": 1, "mineastr_present": False, "candidate_hash_matches": True}


def audit_synthetic_output(path: Path) -> dict[str, Any]:
    resolved = regular_file(path, "SYNTHETIC_OUTPUT")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError("SYNTHETIC_OUTPUT_INVALID") from exc
    if not isinstance(value, dict) or len(value) != 1:
        raise AuditError("SYNTHETIC_OUTPUT_RECORD_COUNT")
    record = next(iter(value.values()))
    if not isinstance(record, dict) or set(record) != auth_gate.EXPECTED_FIELDS:
        raise AuditError("SYNTHETIC_OUTPUT_SCHEMA")
    password_hash = record.get("passwordHash")
    if not isinstance(password_hash, str) or not PASSWORD_HASH_RE.match(password_hash):
        raise AuditError("SYNTHETIC_OUTPUT_BCRYPT_COST")
    if record.get("passwordScheme") != "bcrypt":
        raise AuditError("SYNTHETIC_OUTPUT_PASSWORD_SCHEME")
    if int(record.get("loginCount", -1)) != 2:
        raise AuditError("SYNTHETIC_OUTPUT_LOGIN_COUNT")
    if "password" in record or "newPassword" in record:
        raise AuditError("SYNTHETIC_OUTPUT_PLAINTEXT_FIELD")
    return {
        "records": 1,
        "bcrypt_cost_12": 1,
        "password_scheme": "bcrypt",
        "login_count_after_two_successful_reauthentications": 2,
        "plaintext_fields_present": False,
        "bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


def tcp_closed(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) != 0


def artifact_summary(path: Path) -> dict[str, Any]:
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def audit(args: argparse.Namespace) -> dict[str, Any]:
    candidate = regular_file(args.candidate_jar, "CANDIDATE")
    candidate_summary = auth_gate.validate_jar(
        candidate,
        args.expected_candidate_sha256,
        args.expected_candidate_bytes,
        args.expected_candidate_version,
    )
    source = regular_file(args.source_db, "SOURCE_DB")
    converted = regular_file(args.converted_output, "CONVERTED_OUTPUT")
    if sha256(source) != args.expected_source_sha256.upper():
        raise AuditError("SOURCE_HASH_MISMATCH")
    if sha256(converted) != args.expected_output_sha256.upper():
        raise AuditError("OUTPUT_HASH_MISMATCH")

    rejected_jar = regular_file(args.rejected_candidate_jar, "REJECTED_CANDIDATE")
    if sha256(rejected_jar) != REJECTED_MIGRATION2_SHA256:
        raise AuditError("REJECTED_CANDIDATE_HASH_MISMATCH")

    rejected_log_path, rejected_log = read_log(args.rejected_server_log, "REJECTED_LOG")
    if "NoClassDefFoundError: at/favre/lib/bytes/Bytes" not in rejected_log:
        raise AuditError("REJECTED_LOG_MISSING_BYTES_FAILURE")

    run1_path, run1 = read_log(args.server_run1_log, "SERVER_RUN1_LOG")
    run2_path, run2 = read_log(args.server_run2_log, "SERVER_RUN2_LOG")
    register_client_path, register_client = read_log(args.register_client_log, "REGISTER_CLIENT_LOG")
    login_client_path, login_client = read_log(args.login_client_log, "LOGIN_CLIENT_LOG")
    restart_client_path, restart_client = read_log(args.restart_client_log, "RESTART_CLIENT_LOG")
    wrong_probe_path = regular_file(args.wrong_password_probe, "WRONG_PASSWORD_PROBE")
    try:
        wrong_probe = json.loads(wrong_probe_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError("WRONG_PASSWORD_PROBE_INVALID") from exc
    expected_wrong_probe = {
        "status": "PASS_WRONG_PASSWORD_REJECTED_NO_MUTATION",
        "contains_secrets": False,
        "tested_with_secrets": False,
        "synthetic_player_online": True,
        "record_file_sha256_unchanged": True,
        "password_hash_sha256_unchanged": True,
        "login_count_unchanged": True,
    }
    if not isinstance(wrong_probe, dict) or any(
        wrong_probe.get(key) != value for key, value in expected_wrong_probe.items()
    ):
        raise AuditError("WRONG_PASSWORD_PROBE_NOT_PASS")

    for label, text in (
        ("SERVER_RUN1", run1),
        ("SERVER_RUN2", run2),
        ("REGISTER_CLIENT", register_client),
        ("LOGIN_CLIENT", login_client),
        ("RESTART_CLIENT", restart_client),
    ):
        assert_no_fatal_auth_error(text, label)
        require_at_least(text, candidate.name, 1, label + "_CANDIDATE")
        require_at_least(text, "bcrypt-0.10.2.jar", 1, label + "_BCRYPT_RUNTIME")
        require_at_least(text, "bytes-1.5.0.jar", 1, label + "_BYTES_RUNTIME")

    run1_markers = {
        "loaded_initial_records": require_count(
            run1,
            f"Loaded {args.expected_run1_records} player records from data file",
            1,
            "RUN1_LOAD",
        ),
        "registered": require_count(run1, "registered successfully", 1, "RUN1_REGISTER"),
        "logged_in": require_count(run1, "logged in successfully", 1, "RUN1_LOGIN"),
        "graceful_auth_shutdown": require_count(
            run1, "XiyusLogin data saved and systems shutdown", 1, "RUN1_AUTH_SHUTDOWN"
        ),
        "rcon_stopped": require_count(run1, "Thread RCON Listener stopped", 1, "RUN1_RCON_STOP"),
    }
    run2_markers = {
        "loaded_one_record": require_count(run2, "Loaded 1 player records from data file", 1, "RUN2_LOAD"),
        "logged_in": require_count(run2, "logged in successfully", 1, "RUN2_LOGIN"),
        "graceful_auth_shutdown": require_count(
            run2, "XiyusLogin data saved and systems shutdown", 1, "RUN2_AUTH_SHUTDOWN"
        ),
        "rcon_stopped": require_count(run2, "Thread RCON Listener stopped", 1, "RUN2_RCON_STOP"),
    }
    client_markers = {
        "registration_command_prompt": require_at_least(
            register_client, "/register", 1, "REGISTER_CLIENT_PROMPT"
        ),
        "registration_chat_events": require_at_least(
            register_client,
            "[CHAT]",
            args.expected_registration_chat_events,
            "REGISTER_CLIENT_CHAT",
        ),
        "login_command_prompt": require_at_least(login_client, "/login", 1, "LOGIN_CLIENT_PROMPT"),
        "wrong_then_correct_chat_events": require_at_least(
            login_client,
            "[CHAT]",
            args.expected_login_chat_events,
            "LOGIN_CLIENT_CHAT",
        ),
        "restart_login_command_prompt": require_at_least(
            restart_client, "/login", 1, "RESTART_CLIENT_PROMPT"
        ),
        "restart_login_chat_events": require_at_least(
            restart_client,
            "[CHAT]",
            args.expected_restart_chat_events,
            "RESTART_CLIENT_CHAT",
        ),
    }

    synthetic_output = audit_synthetic_output(args.synthetic_output)
    runtime = {
        "server": audit_mod_dir(args.server_mods, candidate_summary["sha256"], "SERVER"),
        "client": audit_mod_dir(args.client_mods, candidate_summary["sha256"], "CLIENT"),
        "mineastr_disabled_by_absence": True,
        "synthetic_accounts_only": True,
        "production_accounts_loaded": False,
    }
    ports = {
        str(args.server_port): {"closed": tcp_closed("127.0.0.1", args.server_port)},
        str(args.rcon_port): {"closed": tcp_closed("127.0.0.1", args.rcon_port)},
    }
    if not all(item["closed"] for item in ports.values()):
        raise AuditError("ISOLATED_PORT_STILL_OPEN")

    artifact_inputs = {
        "rejected_migration2_server_log": artifact_summary(rejected_log_path),
        "candidate_server_run1": artifact_summary(run1_path),
        "candidate_server_run2": artifact_summary(run2_path),
        "registration_client": artifact_summary(register_client_path),
        "wrong_correct_client": artifact_summary(login_client_path),
        "restart_client": artifact_summary(restart_client_path),
        "wrong_password_no_mutation_probe": artifact_summary(wrong_probe_path),
    }
    scenarios = {
        "java_existing_bcrypt_correct": {
            "status": SYNTHETIC_PASS,
            "basis": "known synthetic BCrypt record accepted by the exact runtime JAR over a real NeoForge client connection",
        },
        "java_existing_bcrypt_wrong_rejected": {
            "status": SYNTHETIC_PASS,
            "basis": "wrong attempt produced a distinct client feedback event; stored hash/count remained unchanged before the following successful login",
        },
        "java_empty_record_registration_policy": {
            "status": SYNTHETIC_PASS,
            "basis": "unregistered synthetic offline player registered, persisted BCrypt cost 12, and no plaintext field exists",
        },
        "java_restart_reauthentication": {
            "status": SYNTHETIC_PASS,
            "basis": "restart loaded one record, prompted for /login again, and incremented loginCount only after correct authentication",
        },
        "bedrock_floodgate_uuid_mapping": {
            "status": "BLOCKED_FLOODGATE_RUNTIME_AND_BEDROCK_CLIENT_MISSING",
            "basis": "no Floodgate/Geyser runtime or controlled Bedrock client was in the isolated topology",
        },
        "proxy_ip_session_policy": {
            "status": "BLOCKED_PROXY_RUNTIME_MISSING_DIRECT_IP_SESSION_POLICY_PASS",
            "basis": "direct loopback reconnect required /login with enableIpSession=false, but no supported proxy path was available",
        },
    }
    return {
        "schema": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "BLOCKED_LIVE_LOGIN_INCOMPLETE",
        "contains_secrets": False,
        "tested_with_secrets": False,
        "source_sha256": sha256(source),
        "output_sha256": sha256(converted),
        "candidate_jar_sha256": candidate_summary["sha256"],
        "candidate": candidate_summary,
        "rejected_candidate": {
            "version": "1.4-migration2",
            "sha256": REJECTED_MIGRATION2_SHA256,
            "status": "REJECTED_RUNTIME_DEPENDENCY_MISSING",
            "failure": "at.favre.lib.bytes.Bytes missing during live synthetic registration",
        },
        "fixture_scope": {
            "base_data_hashes_bound": True,
            "synthetic_one_record_runtime_clone": True,
            "initial_record_count": args.expected_run1_records,
            "production_account_credentials_used": False,
            "production_accounts_exercised": False,
        },
        "runtime": runtime,
        "synthetic_output": synthetic_output,
        "run1_markers": run1_markers,
        "run2_markers": run2_markers,
        "client_markers": client_markers,
        "ports": ports,
        "artifacts": artifact_inputs,
        "scenarios": scenarios,
        "synthetic_scenarios_passed": 4,
        "required_scenarios": 6,
        "strict_verifier_eligible": False,
        "remaining_blockers": [
            "controlled Bedrock client plus supported Geyser/Floodgate runtime and UUID mapping evidence",
            "supported production proxy topology and forwarding/session-bypass evidence",
            "rerun all evidence against the final stopped-source refresh and final assembled target",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    scenarios = report["scenarios"]
    lines = [
        f"# XiyusLogin {report['candidate']['version']} synthetic live-login evidence (2026-08-10)",
        "",
        "## Verdict",
        "",
        "- Aggregate status: **BLOCKED** (`BLOCKED_LIVE_LOGIN_INCOMPLETE`).",
        "- Synthetic Java network scenarios: **4/4 passed** with real NeoForge client connections.",
        "- Strict six-scenario gate: **4/6 covered; 2/6 blocked**.",
        "- Production accounts or credentials used: **no**.",
        "- MineAstr loaded: **no**.",
        "- Isolated server/RCON ports closed after the smoke: **yes**.",
        "",
        f"`migration2` is rejected: its locked JAR omitted bcrypt's `bytes` runtime dependency and failed live registration. `{report['candidate']['version']}` embeds both nested JARs and passed registration/wrong-password/correct-password/restart flows.",
        "",
        "## Candidate",
        "",
        f"- File: `{report['candidate']['file']}`",
        f"- Bytes: `{report['candidate']['bytes']}`",
        f"- SHA-256: `{report['candidate']['sha256']}`",
        "- Runtime dependencies: `bcrypt 0.10.2`, `bytes 1.5.0` (required classes present).",
        "",
        "## Scenario matrix",
        "",
        "| Scenario | Status |",
        "| --- | --- |",
    ]
    for name in auth_gate.REQUIRED_LIVE_SCENARIOS:
        lines.append(f"| `{name}` | `{scenarios[name]['status']}` |")
    lines.extend(
        [
            "",
            "The four Java results use a one-record synthetic runtime clone. They validate the exact candidate code/JAR and network lifecycle without exposing a migrated account. They do not convert the aggregate report into the verifier's all-six `PASS` report.",
            "",
            "## Remaining blockers",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["remaining_blockers"])
    lines.extend(["", "The strict verifier must continue to return non-zero until all six final-target scenarios have bound redacted artifacts.", ""])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-jar", type=Path, required=True)
    parser.add_argument("--expected-candidate-sha256", default=auth_gate.DEFAULT_EXPECTED_JAR_SHA256)
    parser.add_argument("--expected-candidate-bytes", type=int, default=auth_gate.DEFAULT_EXPECTED_JAR_BYTES)
    parser.add_argument("--expected-candidate-version", default=auth_gate.EXPECTED_JAR_VERSION)
    parser.add_argument("--rejected-candidate-jar", type=Path, required=True)
    parser.add_argument("--rejected-server-log", type=Path, required=True)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--converted-output", type=Path, required=True)
    parser.add_argument("--expected-output-sha256", required=True)
    parser.add_argument("--server-run1-log", type=Path, required=True)
    parser.add_argument("--server-run2-log", type=Path, required=True)
    parser.add_argument("--register-client-log", type=Path, required=True)
    parser.add_argument("--login-client-log", type=Path, required=True)
    parser.add_argument("--restart-client-log", type=Path, required=True)
    parser.add_argument("--wrong-password-probe", type=Path, required=True)
    parser.add_argument("--synthetic-output", type=Path, required=True)
    parser.add_argument("--server-mods", type=Path, required=True)
    parser.add_argument("--client-mods", type=Path, required=True)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--rcon-port", type=int, required=True)
    parser.add_argument("--expected-run1-records", type=int, default=0)
    parser.add_argument("--expected-registration-chat-events", type=int, default=2)
    parser.add_argument("--expected-login-chat-events", type=int, default=4)
    parser.add_argument("--expected-restart-chat-events", type=int, default=3)
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--markdown-report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = audit(args)
    except (AuditError, auth_gate.GateError) as exc:
        print(json.dumps({"status": "AUDIT_FAILED", "error": str(exc)}, sort_keys=True))
        return 1
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_report.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "synthetic_passed": 4, "required": 6}, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
